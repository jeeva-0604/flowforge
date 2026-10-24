# FlowForge Community — Honest Feature Matrix (`v0.5.0`)

States:
- **Implemented**: Built, wired end-to-end (API + Engine + UI), and verified by automated tests.
- **Experimental**: Functional in local/self-hosted mode with documented boundaries; further hardening planned.
- **Planned**: Designed in architecture roadmap; not yet implemented.
- **Blocked**: Requires external environment access or third-party credentials to verify live.

| Capability Area | Feature | Status | Verification & Notes |
|---|---|---|---|
| **Workflow Engine** | Directed acyclic graph (DAG) validation & topological sort | **Implemented** | `test_engine.py`, `test_engine_advanced.py` |
| **Workflow Engine** | Safe `{{ expression }}` interpolation (`$input`, `$nodes`, `$item`, `$env`, `$credentials`) | **Implemented** | `test_engine_advanced.py` |
| **Workflow Engine** | Conditional routing (`if_condition` true/false, `switch` cases) with dead-branch skipping | **Implemented** | `test_engine_advanced.py`, `test_e2e_acceptance.py` |
| **Workflow Engine** | Branch merging (`shallow_merge`, `deep_merge`, `collect_branches`), `filter`, bounded `loop` | **Implemented** | `test_engine_advanced.py` |
| **Workflow Engine** | Per-node execution trace (`input_data`, `output_data`, `duration_ms`, `attempts`, `status`) | **Implemented** | `test_e2e_acceptance.py` |
| **Workflow Engine** | Per-node retry policies with exponential backoff & `on_error` fallback modes | **Implemented** | `engine.py`, `test_e2e_acceptance.py` |
| **Workflow Engine** | Human Approval pause (`waiting_approval`) & checkpoint resume (`/approve`) | **Implemented** | `test_e2e_acceptance.py` |
| **Workflow Engine** | Step-level execution replay (`/api/executions/{id}/replay`) | **Implemented** | `main.py`, `engine.py` |
| **Triggers & Runtime** | Manual Trigger, Webhook Trigger (HMAC-SHA256 + replay deduplication), Schedule Trigger | **Implemented** | `test_security_and_worker.py` |
| **Triggers & Runtime** | Durable database-backed worker queue (`execution_jobs`), heartbeats, stale lease recovery & dead-letter queue | **Implemented** | `worker.py`, `test_security_and_worker.py` |
| **Security** | Encrypted Credential Vault (`Fernet` AES-128-CBC + HMAC-SHA256, PBKDF2-SHA256, key rotation) | **Implemented** | `security.py`, `test_security_and_worker.py` |
| **Security** | Automatic recursive secret redaction in node traces and error logs | **Implemented** | `security.py`, `test_security_and_worker.py` |
| **Security** | SSRF protection blocking loopback, RFC1918 private IPs, link-local/cloud metadata (`169.254.169.254`), and unsafe redirects | **Implemented** | `security.py`, `test_security_and_worker.py` |
| **Security** | Isolated Python subprocess execution (`python -I`, stripped env, restricted builtins, CPU/wall timeout) | **Implemented** | `security.py`, `test_engine_advanced.py` |
| **Security** | Scoped API tokens (`viewer`, `editor`, `admin`), token revocation, rate limiting & immutable Audit Log | **Implemented** | `main.py`, `test_security_and_worker.py` |
| **Integration SDK** | 32 first-party node specifications with schemas, contracts & provenance (`/api/integrations`) | **Implemented** | `sdk.py`, `docs/INTEGRATIONS.md` |
| **Skills System** | Versioned Skill manifests, SHA-256 integrity verification, prompt-injection scanner & 10 first-party skills + Custom Skill Installer | **Implemented** | `skills.py`, `test_security_and_worker.py` |
| **AI Automation** | Provider-independent workflow drafting, explanation, failure diagnosis diff & evaluation benchmark | **Implemented** | `ai.py` (local deterministic engine active; Ollama/OpenAI/Gemini adapters experimental) |
| **Developer & Ops** | Workflow versioning, structural diffs, one-click restore, environment promotion (`dev`/`staging`/`prod`), import/export | **Implemented** | `main.py`, `test_e2e_acceptance.py` |
| **Frontend UI** | Multi-view workspace (Overview, Editor, Executions, Credentials, SDK/Skills, Templates/AI, Governance), Undo/Redo, Auto-Layout, Light/Dark theme | **Implemented** | `App.tsx`, `verify_frontend.mjs` |
| **Frontend Build** | Live Vite production bundle (`npm run build`) & Playwright browser E2E | **Blocked** (in offline VM) | Verified via `node frontend/verify_frontend.mjs`; run `npm install && npm run build` locally on Windows. |
| **Enterprise SSO** | Multi-user OIDC/SAML SSO & distributed Redis cluster workers | **Planned** | Scheduled for Milestone 4+. |
| **Testing & Pinning** | Workflow Test Suites (`workflow_test_cases`), assertions & Node Output Pinning (`pinned_node_outputs`) | **Implemented** | `testing_harness.py`, `test_milestone4_enterprise.py` |
| **Variables & Ops** | Workspace Environment Variables (`{{ $vars.KEY }}`), OpenMetrics (`/metrics`), CycloneDX 1.5 SBOM (`/api/system/sbom`) & Backup/Restore (`/api/system/backup`) | **Implemented** | `observability.py`, `test_milestone4_enterprise.py` |
| **Streaming & Workers** | Real-Time SSE Execution Streaming (`/execute-stream`), Distributed Worker Pool (`/api/workers`) & Dead-Letter Replay | **Implemented** | `engine.py`, `worker.py`, `test_milestone5_streaming_and_interop.py` |
| **Interoperability** | Clean-Room External Workflow JSON Importer (`/api/workflows/import-interoperable`) & Security Posture Scanner (`/security-scan`) | **Implemented** | `interop.py`, `test_milestone5_streaming_and_interop.py` |
