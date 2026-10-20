# FlowForge Community Architecture (`v0.3.0`)

## 1. High-Level Component Diagram

```
+-----------------------------------------------------------------------------------+
|                        React + TypeScript + React Flow UI                         |
|  [Overview] [DAG Canvas Editor] [Trace Inspector] [Vault] [Skills/AI] [Governance]|
+-----------------------------------------+-----------------------------------------+
                                          | REST JSON API (CORS, Rate-Limited, RBAC)
                                          v
+-----------------------------------------------------------------------------------+
|                         FastAPI Control Plane (`main.py`)                         |
|  - Workflow CRUD, Versioning, Diffs, Promotion (dev -> staging -> prod)           |
|  - Webhook Ingress (HMAC-SHA256 + Delivery ID Replay Guard)                       |
|  - Scoped API Tokens (`viewer`, `editor`, `admin`) & Immutable Audit Logger       |
+-----------------+-------------------------------+---------------------------------+
                  |                               |
                  v                               v
+-----------------------------------+   +-------------------------------------------+
|   Deterministic Workflow Engine   |   |   Durable Worker & Scheduler (`worker.py`)|
|           (`engine.py`)           |   |  - Claims `execution_jobs` with leases    |
|  - Topological sort & validation  |   |  - Worker heartbeats & stale recovery     |
|  - `{{ expression }}` evaluator   |   |  - Exponential backoff & dead-lettering   |
|  - Conditional branch pruning     |   |  - Periodic `schedule_triggers` ticker    |
|  - Per-node retries & checkpoints |   +---------------------+---------------------+
+-----------------+-----------------+                         |
                  |                                           |
                  +---------------------+---------------------+
                                        |
                                        v
+-----------------------------------------------------------------------------------+
|                Security & Isolation Layer (`security.py` / `sdk.py`)              |
|  - `CredentialVault`: Fernet (AES-128-CBC + HMAC-SHA256) + PBKDF2-SHA256          |
|  - `validate_outbound_url`: SSRF IP/DNS/Redirect guard (blocks 169.254.169.254)   |
|  - `execute_isolated_python`: Subprocess `python -I` sandbox with timeout         |
|  - `resolve_permitted_path`: Sandbox directory confinement                        |
+-----------------------------------------+-----------------------------------------+
                                          |
                                          v
+-----------------------------------------------------------------------------------+
|               PostgreSQL 15+ (Primary JSONB Store) / SQLite Test Store            |
|  Tables: workflows, workflow_versions, executions, execution_jobs, credentials,   |
|          webhook_endpoints, schedule_triggers, api_tokens, audit_logs,            |
|          installed_skills, schema_migrations                                      |
+-----------------------------------------------------------------------------------+
```

## 2. Workflow Execution State Machine

```
                  +----------+
                  |  queued  | (in `execution_jobs`)
                  +----+-----+
                       | Worker claims lease & sets heartbeat
                       v
                  +----------+
         +------->| running  |<-------+
         |        +----+-----+        |
         |             |              | Resume (`/approve`) or
  Retry  |             |              | Replay (`/replay`)
 (backoff|             +--------------+---------------+
  < max) |             |                              |
         |             v                              v
         |   +-------------------+          +------------------+
         |   | waiting_approval  |          |    succeeded     |
         |   +-------------------+          +------------------+
         |             |
         |             | Rejected or `/cancel`
         |             v
         |   +-------------------+          +------------------+
         +---|      failed       |--------->|   dead_letter    |
             +-------------------+ (max     +------------------+
                                   attempts)
```

## 3. Delivery Guarantees, Retry Semantics & Idempotency

- **At-Least-Once Queue Semantics**: Jobs in `execution_jobs` are persisted before execution begins. If a worker process crashes mid-run, `recover_stale_jobs()` re-queues the job after `lease_timeout_seconds` up to `max_attempts`, after which it moves to `dead_letter`.
- **Idempotency**: Callers may supply `idempotency_key` on `/api/workflows/{id}/execute` or `/api/queue/jobs`, and `X-FlowForge-Delivery` on `/api/webhooks/ingest/{slug}`. Duplicate keys return the existing job/delivery record without re-executing external side effects.
- **External Side Effects**: FlowForge does not claim magic "exactly-once" delivery over arbitrary third-party HTTP APIs. Nodes performing external mutations should pass idempotency headers downstream.
