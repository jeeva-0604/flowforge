"""Multi-worker PostgreSQL claim stress test for FlowForge Community.

Safety: this harness refuses to run unless FLOWFORGE_TEST_POSTGRES_URL points
at a dedicated database whose name contains ``test``. It creates temporary
workflow/job rows with a unique marker and deletes those rows on completion.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Barrier
from time import perf_counter, sleep
from typing import Any
from uuid import uuid4
import os
import sys

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from flowforge.db import HAS_SQLALCHEMY  # noqa: E402
from flowforge.migrations import run_migrations  # noqa: E402
from flowforge.models import ExecutionJob, Workflow, utc_now  # noqa: E402
from flowforge.worker import claim_next_job  # noqa: E402


def _target_database_name(url: str) -> str:
    from sqlalchemy.engine import make_url

    return str(make_url(url).database or "")


def run_stress() -> dict[str, Any]:
    if not HAS_SQLALCHEMY:
        raise RuntimeError("PostgreSQL stress requires SQLAlchemy; install backend/requirements.txt first.")

    database_url = os.environ.get("FLOWFORGE_TEST_POSTGRES_URL", "").strip()
    if not database_url:
        raise RuntimeError(
            "Set FLOWFORGE_TEST_POSTGRES_URL to a dedicated PostgreSQL test database, "
            "for example postgresql+psycopg://flowforge:...@localhost:5432/flowforge_stress_test."
        )
    if not database_url.startswith(("postgresql://", "postgresql+psycopg://", "postgresql+psycopg2://")):
        raise RuntimeError("FLOWFORGE_TEST_POSTGRES_URL must be a PostgreSQL URL.")
    database_name = _target_database_name(database_url)
    if "test" not in database_name.lower():
        raise RuntimeError(
            f"Refusing to run against database {database_name!r}: its name must include 'test' "
            "so this stress harness cannot accidentally write into a normal development/production DB."
        )

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(database_url, pool_pre_ping=True, pool_size=12, max_overflow=8)
    LocalSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    run_migrations(engine)

    workers = max(2, int(os.environ.get("FLOWFORGE_STRESS_WORKERS", "8")))
    job_count = max(workers * 2, int(os.environ.get("FLOWFORGE_STRESS_JOBS", "200")))
    marker = f"ff-stress-{uuid4()}"
    workflow_id = str(uuid4())
    claimed_ids: list[str] = []
    started = perf_counter()

    try:
        with LocalSession() as session:
            workflow = Workflow(
                id=workflow_id,
                name=marker,
                description="Temporary workflow created by the PostgreSQL worker stress harness",
                definition={
                    "schema_version": "1.0",
                    "nodes": [{"id": "trigger", "type": "trigger"}, {"id": "output", "type": "output"}],
                    "edges": [{"source": "trigger", "target": "output"}],
                },
            )
            session.add(workflow)
            session.flush()
            jobs = [
                ExecutionJob(
                    id=str(uuid4()),
                    workflow_id=workflow_id,
                    execution_id=None,
                    trigger_type="postgres-stress",
                    idempotency_key=f"{marker}-{index}",
                    status="queued",
                    input_data={"stress_marker": marker, "index": index},
                    attempts=0,
                    max_attempts=1,
                    worker_id=None,
                    heartbeat_at=None,
                    available_at=utc_now(),
                    last_error=None,
                )
                for index in range(job_count)
            ]
            session.add_all(jobs)
            session.commit()

        gate = Barrier(workers)

        def claim_until_idle(worker_index: int) -> tuple[str, list[str]]:
            worker_id = f"postgres-stress-{worker_index}"
            local_claims: list[str] = []
            idle_polls = 0
            with LocalSession() as session:
                gate.wait(timeout=20)
                while idle_polls < 40:
                    job = claim_next_job(session, worker_id, now=datetime.now(timezone.utc))
                    if job is not None:
                        local_claims.append(job.id)
                        idle_polls = 0
                        # Give peers an opportunity to contend for subsequent rows.
                        sleep(0.001)
                    else:
                        # A transient empty selection can happen while other
                        # workers have candidate rows locked; retry before exit.
                        idle_polls += 1
                        sleep(0.005)
            return worker_id, local_claims

        worker_claim_counts: dict[str, int] = {}
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(claim_until_idle, index) for index in range(workers)]
            for future in futures:
                worker_id, claims = future.result()
                worker_claim_counts[worker_id] = len(claims)
                claimed_ids.extend(claims)

        elapsed = perf_counter() - started
        unique_ids = set(claimed_ids)
        with LocalSession() as session:
            running_count = (
                session.query(ExecutionJob)
                .filter(ExecutionJob.workflow_id == workflow_id, ExecutionJob.status == "running")
                .count()
            )
            queued_count = (
                session.query(ExecutionJob)
                .filter(ExecutionJob.workflow_id == workflow_id, ExecutionJob.status == "queued")
                .count()
            )

        result = {
            "database": database_name,
            "workers": workers,
            "jobs_enqueued": job_count,
            "jobs_claimed": len(claimed_ids),
            "unique_jobs_claimed": len(unique_ids),
            "duplicate_claims": len(claimed_ids) - len(unique_ids),
            "persisted_running_jobs": running_count,
            "remaining_queued_jobs": queued_count,
            "workers_that_claimed_jobs": sum(1 for count in worker_claim_counts.values() if count),
            "claims_per_worker": worker_claim_counts,
            "elapsed_seconds": round(elapsed, 3),
            "claims_per_second": round(len(claimed_ids) / elapsed, 1) if elapsed else 0.0,
        }
        print(result)

        if len(claimed_ids) != job_count or len(unique_ids) != job_count or queued_count != 0:
            raise AssertionError(
                "PostgreSQL claim stress failed: expected every enqueued job to be claimed exactly once. "
                f"Observed {result}"
            )
        if running_count != job_count:
            raise AssertionError(f"Claimed jobs were not persisted in running state: {result}")
        return result
    finally:
        # Only remove rows belonging to this unique marker/workflow.
        with LocalSession() as session:
            session.query(ExecutionJob).filter(ExecutionJob.workflow_id == workflow_id).delete(synchronize_session=False)
            session.query(Workflow).filter(Workflow.id == workflow_id).delete(synchronize_session=False)
            session.commit()
        engine.dispose()


if __name__ == "__main__":
    run_stress()
