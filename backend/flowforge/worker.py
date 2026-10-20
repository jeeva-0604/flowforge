"""Durable Database-Backed Queue, Worker Runtime & Scheduler for FlowForge Community."""
from __future__ import annotations

from datetime import timedelta, timezone
from typing import Any
from uuid import uuid4

from .db import HAS_SQLALCHEMY
from .engine import execute_workflow_detailed
from .models import Credential, Execution, ExecutionJob, ScheduleTrigger, Workflow, utc_now
from .schemas import WorkflowDefinition
from .security import CredentialVault


def load_decrypted_credentials(session: Any) -> tuple[dict[str, dict[str, Any]], list[str]]:
    vault = CredentialVault()
    creds_map: dict[str, dict[str, Any]] = {}
    secret_vals: list[str] = []
    for cred in session.query(Credential).all():
        try:
            decrypted = vault.decrypt_dict(cred.encrypted_payload)
            creds_map[cred.name] = decrypted
            for v in decrypted.values():
                if isinstance(v, str) and len(v) >= 4:
                    secret_vals.append(v)
        except Exception:
            continue
    return creds_map, secret_vals


def enqueue_execution_job(
    session: Any,
    workflow_id: str,
    input_data: dict[str, Any],
    *,
    trigger_type: str = "queued",
    idempotency_key: str | None = None,
    max_attempts: int = 3,
) -> ExecutionJob:
    if idempotency_key:
        existing = (
            session.query(ExecutionJob)
            .filter(
                ExecutionJob.workflow_id == workflow_id,
                ExecutionJob.idempotency_key == idempotency_key,
            )
            .first()
        )
        if existing is not None:
            return existing

    job = ExecutionJob(
        id=str(uuid4()),
        workflow_id=workflow_id,
        execution_id=None,
        trigger_type=trigger_type,
        idempotency_key=idempotency_key,
        status="queued",
        input_data=dict(input_data),
        attempts=0,
        max_attempts=max_attempts,
        worker_id=None,
        heartbeat_at=None,
        available_at=utc_now(),
        last_error=None,
    )
    session.add(job)
    session.commit()
    session.refresh(job)
    return job


def recover_stale_jobs(session: Any, lease_timeout_seconds: int = 60) -> int:
    now = utc_now()
    cutoff = now - timedelta(seconds=lease_timeout_seconds)
    running_jobs = session.query(ExecutionJob).filter(ExecutionJob.status == "running").all()
    recovered = 0
    for job in running_jobs:
        hb = job.heartbeat_at
        if hb is not None and hb.tzinfo is None:
            hb = hb.replace(tzinfo=timezone.utc)
        if hb is None or hb < cutoff:
            if job.attempts >= job.max_attempts:
                job.status = "dead_letter"
                job.last_error = f"Worker {job.worker_id!r} heartbeat timed out after max attempts"
            else:
                job.status = "queued"
                job.worker_id = None
                job.available_at = now
                job.last_error = "Recovered from stale worker lease"
            session.add(job)
            recovered += 1
    if recovered:
        session.commit()
    return recovered


def _postgres_claim_statement(now: Any):
    """Build the PostgreSQL row-locking statement for a single ready job."""
    from sqlalchemy import or_, select

    return (
        select(ExecutionJob)
        .where(ExecutionJob.status == "queued")
        .where(or_(ExecutionJob.available_at.is_(None), ExecutionJob.available_at <= now))
        .order_by(ExecutionJob.created_at.asc(), ExecutionJob.id.asc())
        .limit(1)
        .with_for_update(skip_locked=True)
    )


def claim_next_job(
    session: Any,
    worker_id: str = "worker-local-1",
    *,
    now: Any | None = None,
) -> ExecutionJob | None:
    """Atomically claim one ready queue job.

    PostgreSQL uses ``FOR UPDATE SKIP LOCKED`` so concurrent workers claim
    distinct queue rows without blocking each other. The status transition
    and attempt increment are committed before this function returns, while
    the row lock is held. Other dialects retain a deterministic compatibility
    path intended for single-worker development and test environments only.
    """
    now = now or utc_now()
    target_job: ExecutionJob | None = None

    use_postgres_locking = False
    if HAS_SQLALCHEMY:
        try:
            use_postgres_locking = session.get_bind().dialect.name == "postgresql"
        except (AttributeError, TypeError):
            use_postgres_locking = False

    if use_postgres_locking:
        # The statement helper imports SQLAlchemy lazily, preserving the
        # dependency-free compatibility runner in restricted/offline setups.
        target_job = session.execute(_postgres_claim_statement(now)).scalars().first()
    else:
        # SQLite does not implement PostgreSQL row-locking semantics. Keep the
        # simple path for local development but do not claim it is multi-worker
        # safe. Production concurrent workers should use PostgreSQL.
        queued_jobs = (
            session.query(ExecutionJob)
            .filter(ExecutionJob.status == "queued")
            .order_by(ExecutionJob.created_at)
            .all()
        )
        for candidate in queued_jobs:
            avail = candidate.available_at
            if avail is not None and avail.tzinfo is None:
                avail = avail.replace(tzinfo=timezone.utc)
            if avail is None or avail <= now:
                target_job = candidate
                break

    if target_job is None:
        return None

    target_job.status = "running"
    target_job.worker_id = worker_id
    target_job.heartbeat_at = now
    target_job.attempts = (target_job.attempts or 0) + 1
    session.add(target_job)
    session.commit()
    session.refresh(target_job)
    return target_job


def process_next_job(session: Any, worker_id: str = "worker-local-1") -> ExecutionJob | None:
    target_job = claim_next_job(session, worker_id)
    if target_job is None:
        return None

    workflow = session.get(Workflow, target_job.workflow_id)
    if workflow is None:
        target_job.status = "dead_letter"
        target_job.last_error = "Target workflow no longer exists"
        session.add(target_job)
        session.commit()
        session.refresh(target_job)
        return target_job

    execution = Execution(
        id=str(uuid4()),
        workflow_id=workflow.id,
        workflow_version=getattr(workflow, "version", 1) or 1,
        trigger_type=target_job.trigger_type,
        status="running",
        input_data=target_job.input_data,
        node_runs=[],
    )
    session.add(execution)
    session.commit()

    creds_map, secret_vals = load_decrypted_credentials(session)

    def _load_sub(sub_id: str) -> WorkflowDefinition | None:
        sub_wf = session.get(Workflow, sub_id)
        return WorkflowDefinition.model_validate(sub_wf.definition) if sub_wf else None

    try:
        definition = WorkflowDefinition.model_validate(workflow.definition)
        detailed = execute_workflow_detailed(
            definition,
            target_job.input_data,
            credentials_map=creds_map,
            secret_values=secret_vals,
            subworkflow_loader=_load_sub,
        )
        execution.status = detailed["status"]
        execution.result_data = detailed["result_data"]
        execution.node_runs = detailed["node_runs"]
        execution.checkpoint_state = detailed["checkpoint_state"]
        execution.error = detailed["error"]
    except Exception as exc:
        execution.status = "failed"
        execution.result_data = None
        execution.error = str(exc)[:4000]

    execution.finished_at = utc_now()
    session.add(execution)

    target_job.execution_id = execution.id
    target_job.heartbeat_at = utc_now()
    if execution.status in ("succeeded", "waiting_approval"):
        target_job.status = "completed"
        target_job.last_error = None
    else:
        target_job.last_error = execution.error
        if target_job.attempts < target_job.max_attempts:
            backoff_seconds = 2 ** (target_job.attempts - 1)
            target_job.status = "queued"
            target_job.available_at = utc_now() + timedelta(seconds=backoff_seconds)
        else:
            target_job.status = "dead_letter"

    session.add(target_job)
    session.commit()
    session.refresh(target_job)
    return target_job


def tick_schedules(session: Any) -> list[ExecutionJob]:
    now = utc_now()
    schedules = session.query(ScheduleTrigger).filter(ScheduleTrigger.is_active == True).all()  # noqa: E712
    enqueued: list[ExecutionJob] = []
    for sched in schedules:
        nxt = sched.next_run_at
        if nxt is not None and nxt.tzinfo is None:
            nxt = nxt.replace(tzinfo=timezone.utc)
        if nxt is None or nxt <= now:
            payload = {
                **(sched.input_template or {}),
                "_schedule": {"schedule_id": sched.id, "fired_at": now.isoformat()},
            }
            job = enqueue_execution_job(
                session,
                sched.workflow_id,
                payload,
                trigger_type="schedule",
            )
            sched.last_run_at = now
            sched.next_run_at = now + timedelta(seconds=max(int(sched.interval_seconds or 300), 10))
            session.add(sched)
            session.commit()
            enqueued.append(job)
    return enqueued


def get_queue_metrics(session: Any) -> dict[str, int]:
    jobs = session.query(ExecutionJob).all()
    counts = {"queued": 0, "running": 0, "completed": 0, "dead_letter": 0, "total": len(jobs)}
    for j in jobs:
        st = getattr(j, "status", "queued")
        counts[st] = counts.get(st, 0) + 1
    return counts
