# ADR 0004: PostgreSQL queue claims use SKIP LOCKED

- **Status:** Accepted for PostgreSQL deployments; live multi-worker stress verification pending.
- **Date:** 2026-10-20

## Context

The original worker path selected all queued jobs and then set the chosen row to `running`. Multiple PostgreSQL workers could select the same row before either worker committed its update.

## Decision

PostgreSQL worker claims use one ordered SQLAlchemy statement selecting a single ready job with `FOR UPDATE SKIP LOCKED`. While the row is locked, the worker updates `status`, `worker_id`, `heartbeat_at`, and `attempts`, then commits before starting execution. Stable ordering uses `created_at` and `id`.

`claim_next_job()` is shared by direct unit tests and `process_next_job()`. The non-PostgreSQL compatibility path remains for local development and unit tests, but SQLite does not receive the same multi-worker claim guarantee.

## Consequences

- Concurrent PostgreSQL workers do not wait on a candidate row already locked by another worker; they can claim different ready rows.
- Delivery remains **at least once**. If a worker crashes after claiming a job, stale-lease recovery can requeue the job; workflow side effects still need idempotency controls.
- A PostgreSQL-dialect compile test verifies generated SQL includes `FOR UPDATE SKIP LOCKED`. A dedicated live database stress harness is provided in `backend/benchmarks/postgres_worker_stress.py`; production rollout should wait until this passes against the target PostgreSQL version.
- The database-backed queue remains a modular-monolith choice and does not introduce a mandatory Redis service.

## Verification

Unit coverage: `test_postgres_worker_claim_statement_compiles_skip_locked` and `test_claim_next_job_marks_job_running_before_returning`. Live concurrency coverage: see `docs/POSTGRES_WORKER_STRESS.md`.
