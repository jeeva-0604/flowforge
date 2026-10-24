# FlowForge Community (`v0.5.0`)

An independent, self-hosted, open-source workflow automation platform targeting **Apache-2.0**. FlowForge Community provides a deterministic and extensible DAG execution engine, a 32-node integration SDK, 10 SHA-256 verified automation skills, a durable PostgreSQL-backed worker queue, Fernet credential encryption, SSRF and subprocess isolation guards, optional provider-independent AI workflow drafting, and a multi-view React Flow visual workspace.

---

## Key Capabilities Implemented in `v0.3.0`

- **Visual DAG Editor & Workspace UI**: Drag-and-drop 32 node types across 5 categories (`Triggers`, `Core Flow`, `Data & Storage`, `Code & Files`, `AI & Governance`), conditional branch handles (`true`/`false`), Undo/Redo, topological Auto-Layout, live validation panel, JSON import/export, Light/Dark themes, and zero fake placeholder buttons.
- **Deterministic & Branching Engine**: Supports `{{ $input.key }}`, `{{ $nodes.id.key }}`, `{{ $item }}`, and `{{ $credentials.name.key }}` expressions, `IF` / `Switch` branch pruning, `Merge`, `Filter`, bounded `Loop`, per-node retry policies with exponential backoff, per-node input/output traces (`node_runs`), Human Approval pause/resume checkpoints, and step-level replay.
- **Durable Worker Queue & Triggers**: Database-backed `execution_jobs` queue with idempotency keys, worker heartbeats, stale lease recovery after restarts, dead-letter handling, HMAC-SHA256 verified Webhooks with replay protection, and recurring Schedule triggers.
- **Security by Default**: Fernet (AES-128-CBC + HMAC-SHA256) credential vault with PBKDF2-SHA256 key derivation and rotation, automatic secret masking in traces/logs, SSRF protection blocking loopback/private/cloud-metadata (`169.254.169.254`) and unsafe redirects, sandboxed File I/O, parameterized SQL queries, isolated `python -I` subprocess code execution, scoped API tokens, and immutable audit logs.

---

## Windows + PostgreSQL Setup Guide (PowerShell & pgAdmin)

### Prerequisites
- Windows 10/11 (64-bit)
- Python 3.11+
- Node.js 20+ or 22+
- PostgreSQL 15+ (with pgAdmin 4 or `psql`)

### 1. Create the PostgreSQL Role and Database (pgAdmin or `psql`)
Open pgAdmin 4 -> Query Tool (connected as `postgres` administrator) and run:

```sql
CREATE ROLE flowforge WITH LOGIN PASSWORD 'replace-with-strong-local-password';
CREATE DATABASE flowforge_dev OWNER flowforge;
```

*(Optional Docker alternative: run `docker compose up -d postgres` from the repository root.)*

### 2. Backend Setup & Database Migrations (PowerShell)
From the repository root in PowerShell:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r backend
equirements.txt
Copy-Item .env.example .env
```

Edit `.env` and set `DATABASE_URL` and a freshly generated `FLOWFORGE_MASTER_KEY`:

```powershell
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Run database migrations, verify diagnostics, and start the FastAPI server:

```powershell
$env:PYTHONPATH = "backend"
python -m flowforge.init_db
python -m flowforge.cli doctor
uvicorn flowforge.main:app --reload --app-dir backend --host 127.0.0.1 --port 8000
```

- API OpenAPI Docs: `http://127.0.0.1:8000/docs`
- Health & Readiness: `http://127.0.0.1:8000/health/ready`

### 3. Optional Background Worker Process (PowerShell)
In a separate PowerShell terminal with `.venv` active:

```powershell
$env:PYTHONPATH = "backend"
python -m flowforge.cli worker --once
```

### 4. Frontend Setup (PowerShell)
Open a new PowerShell window in the project root:

```powershell
cd frontend
npm install
npm run dev
```

Open `http://127.0.0.1:5173`.

### 5. Running Tests & Benchmarks (PowerShell)

```powershell
# Backend unit, API, security, worker, and 12-step E2E acceptance tests (34 tests):
$env:PYTHONPATH = "backend"
python backend
un_tests.py
# Or directly via pytest:
python -m pytest backend	ests -q

# Reproducible performance benchmarks:
python backendenchmarks
un_benchmarks.py

# Frontend contract verification & production build:
cd frontend
node verify_frontend.mjs
npm run build
```

---

## Documentation Index

- [`docs/PROJECT_AUDIT.md`](docs/PROJECT_AUDIT.md) — Baseline audit of Milestone 2 (`v0.2.0`) and remediated defects.
- [`docs/FEATURE_STATUS.md`](docs/FEATURE_STATUS.md) — Honest feature matrix (`Implemented`, `Experimental`, `Planned`, `Blocked`).
- [`docs/architecture.md`](docs/architecture.md) & [`docs/adr/`](docs/adr/) — System architecture, state machine, delivery guarantees, and ADRs.
- [`docs/SECURITY.md`](docs/SECURITY.md) — Threat model, credential encryption, SSRF rules, subprocess isolation, and limitations.
- [`docs/INTEGRATIONS.md`](docs/INTEGRATIONS.md) & [`docs/SKILLS.md`](docs/SKILLS.md) — First-party 32-node SDK and 6 verified Skills catalog.
- [`docs/BENCHMARKS.md`](docs/BENCHMARKS.md) — Measured validation, execution, queue, and memory benchmarks.
- [`docs/SBOM_AND_LICENSES.md`](docs/SBOM_AND_LICENSES.md) — Software Bill of Materials and license compatibility report.
