"""FlowForge Community Developer CLI."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import platform
import sys

from .ai import run_ai_benchmarks
from .config import database_url, is_default_master_key
from .db import HAS_SQLALCHEMY, SessionLocal, engine
from .engine import validate_workflow_graph
from .migrations import run_migrations
from .observability import export_workspace_backup, generate_cyclonedx_sbom
from .schemas import WorkflowDefinition
from .sdk import list_node_specs
from .skills import list_skills, validate_skill_manifest
from .worker import process_next_job, recover_stale_jobs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="flowforge", description="FlowForge Community CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("doctor", help="Run installation and environment diagnostics")
    sub.add_parser("migrate", help="Apply pending database schema migrations")
    sub.add_parser("skills-list", help="List registered FlowForge skills and integrity hashes")
    sub.add_parser("sbom", help="Generate CycloneDX 1.5 JSON Software Bill of Materials")
    sub.add_parser("backup", help="Export portable workspace backup JSON bundle")

    val_p = sub.add_parser("validate", help="Validate a workflow JSON file")
    val_p.add_argument("file", help="Path to workflow JSON file")

    wk_p = sub.add_parser("worker", help="Run background queue worker")
    wk_p.add_argument("--once", action="store_true", help="Process one available job and exit")

    args = parser.parse_args(argv)

    if args.command == "doctor":
        skills = list_skills()
        for s in skills:
            validate_skill_manifest(s, verify_hash=True)
        info = {
            "python_version": platform.python_version(),
            "platform": platform.platform(),
            "sqlalchemy_installed": HAS_SQLALCHEMY,
            "database_url_configured": bool(database_url()),
            "using_default_dev_master_key": is_default_master_key(),
            "registered_integrations": len(list_node_specs()),
            "verified_skills": len(skills),
            "ai_benchmark": run_ai_benchmarks(),
        }
        print(json.dumps(info, indent=2))
        return 0

    if args.command == "migrate":
        applied = run_migrations(engine)
        print(json.dumps({"status": "migrated", "applied_revisions": applied}, indent=2))
        return 0

    if args.command == "skills-list":
        print(json.dumps(list_skills(), indent=2))
        return 0

    if args.command == "sbom":
        print(json.dumps(generate_cyclonedx_sbom(), indent=2))
        return 0

    if args.command == "backup":
        with SessionLocal() as session:
            print(json.dumps(export_workspace_backup(session), indent=2))
        return 0

    if args.command == "validate":
        raw = json.loads(Path(args.file).read_text(encoding="utf-8"))
        wf_def = WorkflowDefinition.model_validate(raw.get("definition", raw))
        report = validate_workflow_graph(wf_def)
        print(json.dumps(report.model_dump(mode="json"), indent=2))
        return 0 if report.valid else 1

    if args.command == "worker":
        with SessionLocal() as session:
            recovered = recover_stale_jobs(session)
            job = process_next_job(session, worker_id="cli-worker")
            print(
                json.dumps(
                    {
                        "recovered_stale_jobs": recovered,
                        "processed_job_id": job.id if job else None,
                        "status": job.status if job else "idle",
                    },
                    indent=2,
                )
            )
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
