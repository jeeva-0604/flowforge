# Browser end-to-end tests

The Playwright suite drives the actual React Flow workspace and real FastAPI endpoints. It currently exercises a pointer-based branch connection, save/reload persistence, workflow execution, execution trace rendering, node-library interactions and undo. It uses the starter HTTP node's deterministic `mock://` transport and does not need an external service API key.

## Prerequisites

- Node.js supported by the project (Node 22 recommended).
- Python backend dependencies installed in `.venv`.
- PostgreSQL running with the local FlowForge development database migrated, or another isolated test database configured through `DATABASE_URL`.
- FastAPI running at `http://127.0.0.1:8000`.

Start FastAPI in one PowerShell terminal from the repository root:

```powershell
.\.venv\Scripts\Activate.ps1
$env:PYTHONPATH = "backend"
$env:DATABASE_URL = "postgresql+psycopg://flowforge:YOUR_PASSWORD@localhost:5432/flowforge_dev"
python -m flowforge.init_db
uvicorn flowforge.main:app --reload --app-dir backend
```

In a second PowerShell terminal:

```powershell
cd frontend
npm install
npx playwright install chromium
npm run test:e2e
```

The Playwright config starts Vite automatically but deliberately does not start FastAPI or select a database for you. This avoids silently running browser acceptance tests against an unexpected database. Use a dedicated database for CI and test environments. Override endpoints if necessary:

```powershell
$env:FLOWFORGE_E2E_BASE_URL = "http://127.0.0.1:5173"
$env:FLOWFORGE_E2E_API_URL = "http://127.0.0.1:8000"
npm run test:e2e
```

On failure, Playwright captures a screenshot, video and trace under `frontend/test-results/`; `npm run test:e2e:report` opens the HTML report when one was generated. The tests create an acceptance-test workflow in the configured database and delete it in cleanup. Still, use a development/test database, not production.
