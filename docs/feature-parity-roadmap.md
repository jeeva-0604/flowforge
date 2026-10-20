# FlowForge Community: feature parity roadmap

**Project promise:** an independently implemented, self-hosted, open-source workflow automation platform. The roadmap aims to make the core product and advanced capabilities available without an artificial feature paywall. “Parity target” is not a claim that these features have shipped or that n8n compatibility is already established.

## Clean-room and licensing rules

- Use public product documentation, public APIs, independently written tests, and lawful observations of software we are authorized to examine.
- Do not copy n8n source, paid code, internal implementation details, names/logos, screenshots, templates, or proprietary UI assets. Do not bypass license checks or access controls.
- Do not use REA against a service or binary unless we have authority to analyze it and the relevant vendor terms permit that activity. REA is an optional research tool, never a runtime requirement.
- Keep an evidence ledger per feature: public references, our own specification, implementation PR, tests, and license review.
- Apache-2.0 is the target for FlowForge-authored code, subject to dependency compatibility, notices, attribution, generated artifacts and contribution review. Do not label the whole dependency tree Apache-2.0 without review.

## Reference feature areas to independently implement

| Area | Target capabilities | Current status |
|---|---|---|
| Workflow editor | Node canvas, connections, node settings, keyboard actions, search, undo/redo, zoom/minimap, auto-layout, import/export | First editor slice: canvas, add/connect/edit nodes, save/load, run result. Undo/redo, layout, import/export pending. |
| Workflow engine | DAG validation, expressions, branching, merge, loops, subworkflows, item/batch processing, typed data, cancellation, timeouts | Prototype: trigger → set → output; DAG validation. |
| Triggers | Manual, webhook, schedule/cron, polling, app-event triggers, event streams | Manual only. |
| Integration SDK | HTTP/API, pagination, OAuth2/API-key/basic auth, webhook subscriptions, retry/backoff, rate limits, typed schemas | Not implemented. Build an SDK and start with HTTP, PostgreSQL and webhook adapters. |
| Credentials & secrets | Encrypted at rest, scoped references, rotation, external secret managers, audit events | Not implemented. Required before real production integrations. |
| Runs & debugging | Per-node input/output, step status, retry from step, replay with saved data, logs, diffs, pin/mock data | Current aggregate execution record only. |
| Reliability & scale | Durable queue, worker pools, concurrency/rate controls, idempotency, retries, pause/resume, restart recovery, dead-letter handling | Synchronous in-process execution only. |
| Collaboration | Users, organizations/projects, RBAC, ownership, shared credentials, audit trail, SSO/OIDC/SAML | Not implemented. |
| Deployment lifecycle | Draft/publish, revisions, rollback, dev/staging/prod promotion, Git integration, migration/import/export | Not implemented. |
| AI & agents | Provider abstraction, AI node builder, tools, memory connectors, structured outputs, evaluations, HITL approvals, MCP client/server | Not implemented. Must be optional and securely scoped. |
| Admin & governance | Security audit, execution retention, usage insights, alerting, health checks, backups, policy guardrails | Not implemented. |
| Ecosystem | Node package SDK, signed community nodes, catalog, templates, test harness, compatibility matrix | Not implemented. |
| Developer experience | REST API, OpenAPI client generation, CLI, local dev mode, metrics/traces, extensions, versioned workflow schema | FastAPI OpenAPI available; CLI and schema versions pending. |

## Build milestones and release gates

### M1 — deterministic core (prototype started)

- [x] FastAPI API, PostgreSQL persistence, three node types, basic DAG validation, execution history record.
- [x] Tests for basic graph execution and validation.
- [ ] Production database migrations and API/auth boundaries.

### M2 — usable visual editor (in progress)

- [x] React + TypeScript + React Flow canvas.
- [x] Add/connect/edit trigger, set and output nodes.
- [x] Save/load workflows, preserve canvas coordinates, execute saved workflow, view result/history.
- [ ] Automated frontend build and browser E2E test on supported Node.js.
- [ ] Validation feedback on the exact graph edge/node that failed.

### M3 — first useful automations

- HTTP Request node with redirect controls, private-IP protections, timeouts, response size limits, retry policy and credential references.
- Webhook trigger using a dedicated ingress endpoint with authentication/signatures, payload caps and replay protection.
- Schedule trigger with timezone-aware cron, misfire rules, persistent scheduler storage and job locking.
- PostgreSQL node with parameterized SQL by default, read-only/least-privilege guidance, query timeouts and cancellation.
- Conditional/merge/loop nodes with explicit item semantics and exhaustive unit tests.

### M4 — production runtime

- Worker process and durable queue; execution state machine; transactionally persisted scheduling/claims; at-least-once semantics with idempotency contracts.
- Per-node trace, structured logs, bounded output storage, execution retries and restart recovery.
- Credential encryption using a generated instance secret, rotation and key-management documentation; never store raw secrets in workflow JSON.
- Authentication, project-level access control, CSRF/session strategy if cookies are used, rate limiting, audit events and backup/restore drills.

### M5 — integration ecosystem

- Versioned node SDK, JSON Schema-based input/output definitions, credentials descriptors, tests and docs conventions.
- Start integrations based on community demand. HTTP Request is the universal fallback; integration count alone is not the product goal.
- Community publishing pipeline with dependency/license scanning, provenance, signing, permissions and compatibility checks.

### M6 — AI and advanced automation

- LLM adapters with user-supplied keys or local models; no vendor key required by the platform.
- Agent/tool scopes, secrets isolation, human approval for high-impact actions, prompt-injection defenses and deterministic validation around agent decisions.
- Optional REA/MCP assistant that can draft a feature spec from authorized evidence; every generated implementation still requires tests and human review.

### M7 — parity/compliance track

- Public compatibility matrix for every claimed capability.
- Independently author workflow fixtures where permitted; verify import/export mappings rather than promise one-click perfect compatibility.
- Conformance tests for retries, error semantics, item handling, expressions, webhook verification, schedule edge cases, secrets, access control and migration.
- Security review, threat model, dependency license scan, SPDX inventory, SBOM, CI, release process and contributor policy before 1.0.

## Quality gates

A feature is only “done” when it includes API and UI behavior, automated tests for success and failure, security/resource-limit tests where relevant, docs, migration/backward-compatibility notes, accessibility review for major UI paths, and license review. “Works on my machine” is not the parity standard.

## Frontend improvement goals

- Responsive canvas with fast search, command palette, keyboard-first editing, minimap, tidy auto-layout, undo/redo and visible validation.
- Per-node run status and inline input/output inspector; re-run from a selected node without re-triggering external side effects.
- Secrets represented only as references, never displayed back in full.
- Workflow diff/revisions, environment promotion, searchable execution timeline and accessible contrast/keyboard operation.
- Clear free/self-hosted status, exportable projects, no forced cloud dependency, optional AI rather than mandatory AI.
