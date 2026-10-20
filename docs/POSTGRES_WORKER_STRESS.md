# PostgreSQL multi-worker queue stress test

FlowForge's PostgreSQL worker claim path uses a single ordered `SELECT ... FOR UPDATE SKIP LOCKED` to choose a ready queued job and marks it `running` before committing the same transaction. Other database dialects use a simple compatibility path and are **not** covered by the multi-worker claim guarantee.

## Safe setup on Windows

Use a dedicated database whose name contains `test`. Do not point the harness at a real development or production database.

In pgAdmin Query Tool connected as a PostgreSQL administrator:

```sql
CREATE ROLE flowforge_stress WITH LOGIN PASSWORD 'replace-with-a-strong-local-password';
CREATE DATABASE flowforge_stress_test OWNER flowforge_stress;
```

From the repository root, activate the project virtual environment and configure the database URL. Run in PowerShell:

```powershell
$env:PYTHONPATH = "backend"
$env:FLOWFORGE_TEST_POSTGRES_URL = "postgresql+psycopg://flowforge_stress:replace-with-a-strong-local-password@localhost:5432/flowforge_stress_test"
$env:FLOWFORGE_STRESS_WORKERS = "8"
$env:FLOWFORGE_STRESS_JOBS = "200"
python backend\benchmarks\postgres_worker_stress.py
```

Expected success requires all jobs to be claimed, each ID claimed exactly once, zero jobs left queued, and every claimed job persisted as `running`. The harness prints the actual counts and throughput. It creates a unique temporary workflow plus queue jobs and deletes those rows at the end. A dedicated database is still required because the harness applies the FlowForge schema migrations.

To increase load, raise `FLOWFORGE_STRESS_JOBS` and `FLOWFORGE_STRESS_WORKERS` gradually. The script uses concurrent threads with independent SQLAlchemy sessions; it is a claim-correctness stress test, not a benchmark of full workflow execution throughput.
