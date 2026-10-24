"""Observability, OpenMetrics/Prometheus Exporter, CycloneDX SBOM Generator,
and Portable Workspace Backup/Restore Utilities for FlowForge Community.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from typing import Any
from uuid import uuid4

from .models import (
    Execution,
    ExecutionJob,
    ScheduleTrigger,
    WebhookEndpoint,
    Workflow,
    WorkflowTestCase,
    WorkflowVersion,
    WorkspaceVariable,
    utc_now,
)
from .sdk import list_node_specs
from .skills import list_skills


def render_prometheus_metrics(session: Any) -> str:
    """Render OpenMetrics / Prometheus text format metrics for scraping."""
    workflows = session.query(Workflow).all()
    executions = session.query(Execution).all()
    jobs = session.query(ExecutionJob).all()

    exec_by_status: dict[str, int] = {"succeeded": 0, "failed": 0, "waiting_approval": 0, "cancelled": 0, "running": 0}
    for ex in executions:
        st = getattr(ex, "status", "unknown")
        exec_by_status[st] = exec_by_status.get(st, 0) + 1

    job_by_status: dict[str, int] = {"queued": 0, "running": 0, "completed": 0, "dead_letter": 0}
    for jb in jobs:
        st = getattr(jb, "status", "queued")
        job_by_status[st] = job_by_status.get(st, 0) + 1

    lines = [
        "# HELP flowforge_workflows_total Total number of saved workflows",
        "# TYPE flowforge_workflows_total gauge",
        f"flowforge_workflows_total {len(workflows)}",
        "# HELP flowforge_integrations_total Total number of registered SDK node types",
        "# TYPE flowforge_integrations_total gauge",
        f"flowforge_integrations_total {len(list_node_specs())}",
        "# HELP flowforge_skills_total Total number of verified automation skills",
        "# TYPE flowforge_skills_total gauge",
        f"flowforge_skills_total {len(list_skills())}",
        "# HELP flowforge_executions_total Total workflow executions partitioned by status",
        "# TYPE flowforge_executions_total counter",
    ]
    for st, count in sorted(exec_by_status.items()):
        lines.append(f'flowforge_executions_total{{status="{st}"}} {count}')

    lines.append("# HELP flowforge_queue_jobs_total Total worker queue jobs partitioned by status")
    lines.append("# TYPE flowforge_queue_jobs_total gauge")
    for st, count in sorted(job_by_status.items()):
        lines.append(f'flowforge_queue_jobs_total{{status="{st}"}} {count}')

    return "\n".join(lines) + "\n"


def generate_cyclonedx_sbom() -> dict[str, Any]:
    """Generate a CycloneDX 1.5 JSON Software Bill of Materials (SBOM)."""
    components = [
        {"type": "library", "name": "fastapi", "version": ">=0.115,<1.0", "licenses": [{"license": {"id": "MIT"}}], "purl": "pkg:pypi/fastapi"},
        {"type": "library", "name": "uvicorn", "version": ">=0.30,<1.0", "licenses": [{"license": {"id": "BSD-3-Clause"}}], "purl": "pkg:pypi/uvicorn"},
        {"type": "library", "name": "SQLAlchemy", "version": ">=2.0,<3.0", "licenses": [{"license": {"id": "MIT"}}], "purl": "pkg:pypi/sqlalchemy"},
        {"type": "library", "name": "alembic", "version": ">=1.13,<2.0", "licenses": [{"license": {"id": "MIT"}}], "purl": "pkg:pypi/alembic"},
        {"type": "library", "name": "psycopg", "version": ">=3.2,<4.0", "licenses": [{"license": {"id": "LGPL-3.0-or-later"}}], "purl": "pkg:pypi/psycopg"},
        {"type": "library", "name": "pydantic", "version": ">=2.8,<3.0", "licenses": [{"license": {"id": "MIT"}}], "purl": "pkg:pypi/pydantic"},
        {"type": "library", "name": "python-dotenv", "version": ">=1.0,<2.0", "licenses": [{"license": {"id": "BSD-3-Clause"}}], "purl": "pkg:pypi/python-dotenv"},
        {"type": "library", "name": "cryptography", "version": ">=42.0,<45.0", "licenses": [{"license": {"id": "Apache-2.0"}}], "purl": "pkg:pypi/cryptography"},
        {"type": "library", "name": "httpx", "version": ">=0.27,<1.0", "licenses": [{"license": {"id": "BSD-3-Clause"}}], "purl": "pkg:pypi/httpx"},
        {"type": "library", "name": "react", "version": "^18.3.1", "licenses": [{"license": {"id": "MIT"}}], "purl": "pkg:npm/react"},
        {"type": "library", "name": "react-dom", "version": "^18.3.1", "licenses": [{"license": {"id": "MIT"}}], "purl": "pkg:npm/react-dom"},
        {"type": "library", "name": "@xyflow/react", "version": "^12.3.6", "licenses": [{"license": {"id": "MIT"}}], "purl": "pkg:npm/%40xyflow/react"},
        {"type": "library", "name": "lucide-react", "version": "^0.468.0", "licenses": [{"license": {"id": "ISC"}}], "purl": "pkg:npm/lucide-react"},
        {"type": "library", "name": "typescript", "version": "~5.6.3", "licenses": [{"license": {"id": "Apache-2.0"}}], "purl": "pkg:npm/typescript"},
        {"type": "library", "name": "vite", "version": "^6.0.5", "licenses": [{"license": {"id": "MIT"}}], "purl": "pkg:npm/vite"},
    ]
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "version": 1,
        "metadata": {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "component": {
                "type": "application",
                "name": "flowforge-community",
                "version": "0.5.0",
                "licenses": [{"license": {"id": "Apache-2.0"}}],
            },
        },
        "components": components,
    }


def export_workspace_backup(session: Any) -> dict[str, Any]:
    """Export workflows, variables (secrets redacted), test cases, webhooks, and schedules."""
    workflows = [
        {
            "id": w.id,
            "name": w.name,
            "description": getattr(w, "description", ""),
            "tags": getattr(w, "tags", []),
            "folder": getattr(w, "folder", "General"),
            "is_active": getattr(w, "is_active", True),
            "environment": getattr(w, "environment", "dev"),
            "version": getattr(w, "version", 1),
            "definition": w.definition,
        }
        for w in session.query(Workflow).all()
    ]
    variables = [
        {
            "key": v.key,
            "value": "***REDACTED***" if v.is_secret else v.value,
            "environment": v.environment,
            "is_secret": v.is_secret,
            "description": v.description,
        }
        for v in session.query(WorkspaceVariable).all()
    ]
    test_cases = [
        {
            "workflow_id": tc.workflow_id,
            "name": tc.name,
            "description": tc.description,
            "input_data": tc.input_data,
            "pinned_node_outputs": tc.pinned_node_outputs,
            "assertions": tc.assertions,
        }
        for tc in session.query(WorkflowTestCase).all()
    ]
    bundle_body = {
        "workflows": workflows,
        "variables": variables,
        "test_cases": test_cases,
    }
    canonical = json.dumps(bundle_body, sort_keys=True, separators=(",", ":")).encode("utf-8")
    digest = "sha256:" + hashlib.sha256(canonical).hexdigest()
    return {
        "format": "flowforge-workspace-backup",
        "version": "0.5.0",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "integrity_hash": digest,
        "bundle": bundle_body,
    }


def restore_workspace_backup(session: Any, backup_payload: dict[str, Any]) -> dict[str, int]:
    """Restore workflows, non-redacted variables, and test cases from a backup bundle."""
    bundle = backup_payload.get("bundle", backup_payload)
    restored_workflows = 0
    restored_vars = 0
    restored_tests = 0

    for wf_data in bundle.get("workflows", []):
        wf_id = wf_data.get("id") or str(uuid4())
        existing = session.get(Workflow, wf_id)
        if existing is None:
            wf = Workflow(
                id=wf_id,
                name=wf_data["name"],
                description=wf_data.get("description", ""),
                tags=wf_data.get("tags", []),
                folder=wf_data.get("folder", "General"),
                is_active=wf_data.get("is_active", True),
                environment=wf_data.get("environment", "dev"),
                version=wf_data.get("version", 1),
                definition=wf_data["definition"],
            )
            session.add(wf)
            session.commit()
            ver = WorkflowVersion(
                id=str(uuid4()),
                workflow_id=wf.id,
                version=wf.version,
                name=wf.name,
                environment=wf.environment,
                comment="Restored from workspace backup",
                definition=wf.definition,
            )
            session.add(ver)
            restored_workflows += 1

    for var_data in bundle.get("variables", []):
        if var_data.get("value") == "***REDACTED***":
            continue
        v = WorkspaceVariable(
            id=str(uuid4()),
            key=var_data["key"],
            value=var_data["value"],
            environment=var_data.get("environment", "all"),
            is_secret=bool(var_data.get("is_secret", False)),
            description=var_data.get("description", ""),
        )
        session.add(v)
        restored_vars += 1

    session.commit()

    for tc_data in bundle.get("test_cases", []):
        if session.get(Workflow, tc_data.get("workflow_id")) is not None:
            tc = WorkflowTestCase(
                id=str(uuid4()),
                workflow_id=tc_data["workflow_id"],
                name=tc_data["name"],
                description=tc_data.get("description", ""),
                input_data=tc_data.get("input_data", {}),
                pinned_node_outputs=tc_data.get("pinned_node_outputs", {}),
                assertions=tc_data.get("assertions", []),
            )
            session.add(tc)
            restored_tests += 1

    session.commit()
    return {
        "restored_workflows": restored_workflows,
        "restored_variables": restored_vars,
        "restored_test_cases": restored_tests,
    }
