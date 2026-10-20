# FlowForge Skills Registry & Developer Guide (`v0.3.0`)

## 1. First-Party Shipped Skills (`backend/flowforge/skills.py`)

| Skill ID | Version | Category | Permissions | Integrity Verified | Description |
|---|---|---|---|---|---|
| `rest-api-workflow-builder` | `1.0.0` | Workflow Authoring | `workflow:draft` | Yes (SHA-256) | Generates a 5-node resilient Trigger -> HTTP -> IF -> Output workflow |
| `postgres-query-quality-helper` | `1.0.0` | Data & SQL | `sql:analyze` | Yes (SHA-256) | Audits SQL queries for `:param` bindings and blocks unsafe DDL/concatenation |
| `csv-json-transformation-helper` | `1.0.0` | Data & SQL | `data:transform` | Yes (SHA-256) | Normalizes CSV/JSON records, trims strings, and infers numeric types |
| `workflow-test-generator` | `1.0.0` | Testing & QA | `workflow:analyze` | Yes (SHA-256) | Generates positive, negative, and branch-coverage test cases |
| `workflow-debugging-assistant` | `1.0.0` | Observability & Triage | `workflow:analyze` | Yes (SHA-256) | Pinpoints failed nodes and remediation steps from redacted traces |
| `safe-error-triage-assistant` | `1.0.0` | Observability & Triage | `workflow:analyze` | Yes (SHA-256) | Classifies transient vs. non-retriable errors and recommends retry policies |
