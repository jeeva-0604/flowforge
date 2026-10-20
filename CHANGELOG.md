## [0.4.0] - 2026-10-20

### Added
- Atomic PostgreSQL queue claims using ordered `SELECT ... FOR UPDATE SKIP LOCKED`; job status and attempt count are persisted before the worker begins execution.
- `claim_next_job()` unit coverage for claim state and worker attribution.
- Playwright browser acceptance tests covering actual React Flow pointer connections, persisted save/reload, execution success, execution trace rendering, palette insertion, and undo.
- Windows-oriented Playwright runbook and a guarded PostgreSQL multi-worker stress harness.
- CI workflow to build the frontend and run Playwright against a real FastAPI process on an isolated SQLite CI database.

### Notes
- Multi-worker locking guarantees apply to PostgreSQL. The SQLite compatibility path remains for single-worker local development/testing only.
- Browser tests require the API to point at a development/test database; do not run them against production.

# Changelog

## [0.3.0] — 2026-10-20
### Added
- **Workflow Engine (`engine.py`)**: Added safe `{{ expression }}` evaluation (`$input`, `$nodes`, `$item`, `$env`, `$credentials`), conditional branching (`if_condition`, `switch`) with dead-branch skipping, `merge`, `filter`, `loop`, `wait`, `http_request`, `sql_query` (parameterized), `csv_json`, `file_io` (sandboxed), `code` (isolated subprocess), `skill`, `ai_agent`, `human_approval` (pause/resume checkpoints), `subworkflow`, and per-node execution traces (`node_runs`).
- **Durable Worker & Scheduler (`worker.py`)**: Added database-backed `execution_jobs` queue with idempotency keys, worker heartbeats, stale lease recovery, exponential backoff retries, dead-letter handling, and recurring `schedule_triggers`.
- **Enterprise Security (`security.py`)**: Added `CredentialVault` (Fernet AES-128-CBC + HMAC-SHA256 with PBKDF2-SHA256 key derivation and rotation), recursive secret redaction, SSRF protection (blocking loopback, RFC1918 private IPs, `169.254.169.254` metadata, and unsafe redirect hops), path traversal guards, scoped RBAC API tokens (`ffk_...`), rate limiting, and `audit_logs`.
- **Ecosystem (`sdk.py`, `skills.py`, `templates.py`, `ai.py`)**: Published 21 first-party node specifications, 6 SHA-256 integrity-verified Skills, 3 verified workflow templates, and a provider-independent AI workflow drafter, explainer, and failure diagnosis engine.
- **Database Migrations (`migrations.py`, `backend/migrations/`)**: Added idempotent PostgreSQL/SQLite schema migration runner and Alembic revisions `0001` and `0002`.
- **Frontend (`frontend/src/App.tsx`, `styles.css`)**: Replaced all placeholder toasts with functional views (Overview, Editor, Executions, Credentials Vault, SDK & Skills, Templates & AI Studio, Webhooks/Schedules/Audit), added Undo/Redo, Auto-Layout, per-node status badges, step trace inspector, version diffs & restore, and Light/Dark themes. Fixed invalid npm versions in `frontend/package.json`.
