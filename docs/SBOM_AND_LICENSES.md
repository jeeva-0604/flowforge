# Software Bill of Materials (SBOM) & Dependency License Report (`v0.4.0`)

**Project License Target:** Apache License 2.0 (provisional pending final human legal review of all transitive packages prior to public binary distribution).  
**Clean-Room Attestation:** All FlowForge Community code, schemas, engine logic, SDK contracts, and UI components are independently authored. No proprietary source code, assets, or restricted APIs from n8n or any commercial vendor were used.

## 1. Direct Backend Dependencies (`backend/requirements.txt`)

| Package | Version Range | License | Source / Provenance | Compatibility with Apache-2.0 |
|---|---|---|---|---|
| `fastapi` | `>=0.115,<1.0` | MIT | https://github.com/fastapi/fastapi | Compatible (Permissive) |
| `uvicorn[standard]` | `>=0.30,<1.0` | BSD-3-Clause | https://github.com/encode/uvicorn | Compatible (Permissive) |
| `SQLAlchemy` | `>=2.0,<3.0` | MIT | https://github.com/sqlalchemy/sqlalchemy | Compatible (Permissive) |
| `alembic` | `>=1.13,<2.0` | MIT | https://github.com/sqlalchemy/alembic | Compatible (Permissive) |
| `psycopg[binary]` | `>=3.2,<4.0` | LGPL-3.0-or-later | https://github.com/psycopg/psycopg | **Review Note:** `psycopg[binary]` bundles `libpq` under LGPL-3.0. For strict Apache-2.0 binary redistribution, prefer `psycopg` (pure Python/C with system `libpq`) or document LGPL-3.0 dynamic linking notices. |
| `pydantic` | `>=2.8,<3.0` | MIT | https://github.com/pydantic/pydantic | Compatible (Permissive) |
| `python-dotenv` | `>=1.0,<2.0` | BSD-3-Clause | https://github.com/theskumar/python-dotenv | Compatible (Permissive) |
| `cryptography` | `>=42.0,<45.0` | Apache-2.0 OR BSD-3-Clause | https://github.com/pyca/cryptography | Compatible (Dual Apache-2.0 / BSD-3) |
| `httpx` | `>=0.27,<1.0` | BSD-3-Clause | https://github.com/encode/httpx | Compatible (Permissive) |
| `pytest` | `>=8.0,<9.0` | MIT | https://github.com/pytest-dev/pytest | Compatible (Dev/Test only) |

## 2. Direct Frontend Dependencies (`frontend/package.json`)

| Package | Version Range | License | Source / Provenance | Obligation |
|---|---|---|---|---|
| `react` | `^18.3.1` | MIT | https://github.com/facebook/react | Retain MIT copyright notice |
| `react-dom` | `^18.3.1` | MIT | https://github.com/facebook/react | Retain MIT copyright notice |
| `@xyflow/react` | `^12.3.6` | MIT | https://github.com/xyflow/xyflow | Retain MIT notice & visible attribution (`hideAttribution: false`) |
| `lucide-react` | `^0.468.0` | ISC | https://github.com/lucide-icons/lucide | Retain ISC notice |
| `typescript` | `~5.6.3` | Apache-2.0 | https://github.com/microsoft/TypeScript | Dev/Build dependency |
| `vite` | `^6.0.5` | MIT | https://github.com/vitejs/vite | Dev/Build dependency |
| `@vitejs/plugin-react` | `^4.3.4` | MIT | https://github.com/vitejs/vite-plugin-react | Dev/Build dependency |
| `@playwright/test` | `^1.63.0` | Apache-2.0 | https://github.com/microsoft/playwright | Dev/Test only; browser binaries are installed separately and are not bundled with FlowForge |
