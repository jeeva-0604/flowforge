# FlowForge Skills Registry & Developer Guide (`v0.5.0`)

## 1. First-Party Shipped Skills (`backend/flowforge/skills.py`)

| Skill ID | Version | Category | Permissions | Integrity Verified | Description |
|---|---|---|---|---|---|
| `rest-api-workflow-builder` | `1.0.0` | Workflow Authoring | `workflow:draft` | Yes (SHA-256) | Generates a 5-node resilient Trigger -> HTTP -> IF -> Output workflow |
| `postgres-query-quality-helper` | `1.0.0` | Data & SQL | `sql:analyze` | Yes (SHA-256) | Audits SQL queries for `:param` bindings and blocks unsafe DDL/concatenation |
| `csv-json-transformation-helper` | `1.0.0` | Data & SQL | `data:transform` | Yes (SHA-256) | Normalizes CSV/JSON records, trims strings, and infers numeric types |
| `workflow-test-generator` | `1.0.0` | Testing & QA | `workflow:analyze` | Yes (SHA-256) | Generates positive, negative, and branch-coverage test cases |
| `workflow-debugging-assistant` | `1.0.0` | Observability & Triage | `workflow:analyze` | Yes (SHA-256) | Pinpoints failed nodes and remediation steps from redacted traces |
| `safe-error-triage-assistant` | `1.0.0` | Observability & Triage | `workflow:analyze` | Yes (SHA-256) | Classifies transient vs. non-retriable errors and recommends retry policies |
| `api-integration-scaffold-generator` | `1.0.0` | Contributor Tooling | `workflow:draft` | Yes (SHA-256) | Generates `NodeSpec` and test scaffolds for new integrations |
| `workflow-documentation-generator` | `1.0.0` | Documentation & Governance | `workflow:analyze` | Yes (SHA-256) | Generates Markdown runbooks and node inventory tables from workflow JSON |
| `cron-schedule-auditor` | `1.0.0` | Observability & Triage | `workflow:analyze` | Yes (SHA-256) | Validates 5-field cron expressions and warns on high-frequency schedules |
| `security-posture-scanner` | `1.0.0` | Documentation & Governance | `workflow:analyze` | Yes (SHA-256) | Audits workflows for hardcoded secrets, HTTP URLs, and SQL safety (0-100 score) |
