# FlowForge Community — First-Party Integrations Catalog (`v0.5.0`)

All 32 first-party nodes are independently implemented under Apache-2.0 target licensing in `backend/flowforge/sdk.py` and `backend/flowforge/engine.py`.

| Node Type (`type`) | Display Name | Category | Output Handles | Credentials | Summary |
|---|---|---|---|---|---|
| `trigger` | Manual Trigger | Triggers | `default` | None | Starts a workflow run with JSON input |
| `webhook_trigger` | Webhook Trigger | Triggers | `default` | Optional HMAC | Starts a workflow on authenticated HTTP POST |
| `schedule_trigger` | Schedule Trigger | Triggers | `default` | None | Recurring cron/interval trigger |
| `set` | Set / Edit Fields | Core Flow | `default` | None | Sets, interpolates (`{{ ... }}`), or removes JSON fields |
| `if_condition` | IF Condition | Core Flow | `true`, `false` | None | Deterministic comparison routing with dead-branch skipping |
| `switch` | Switch / Router | Core Flow | `case_1`, `case_2`, `default` | None | Multi-way value router |
| `merge` | Merge Branches | Core Flow | `default` | None | Combines upstream branches (`shallow_merge`, `deep_merge`, `collect_branches`) |
| `filter` | Filter Items | Core Flow | `default` | None | Filters an array field by operator/value |
| `loop` | Loop / Batch Transform | Core Flow | `default` | None | Bounded iteration over an array field (`max_iterations <= 1000`) |
| `wait` | Wait / Delay | Core Flow | `default` | None | Bounded millisecond pause with timing trace |
| `subworkflow` | Execute Sub-Workflow | Core Flow | `default` | Inherited | Calls a saved child workflow (max recursion depth 3) |
| `error_handler` | Error Triage / Fallback | Core Flow | `default` | None | Emits structured recovery values |
| `http_request` | HTTP Request | Data & Storage | `default` | `http_bearer`, `http_header` | SSRF-guarded HTTP/HTTPS client + `mock://` local test scheme |
| `sql_query` | SQL Query (Parameterized) | Data & Storage | `default` | `database_url` | Safe `:param` SQL queries; blocks multi-statement injection |
| `csv_json` | CSV / JSON Processor | Data & Storage | `default` | None | Deterministic CSV <-> JSON conversion |
| `code` | Code (Isolated Python) | Code & Files | `default` | None | Subprocess `python -I` transformation with restricted builtins |
| `file_io` | Sandboxed File I/O | Code & Files | `default` | None | Read/write JSON/text inside `FLOWFORGE_ALLOWED_FILE_DIR` |
| `skill` | Run FlowForge Skill | AI & Governance | `default` | None | Executes an integrity-verified FlowForge Skill |
| `ai_agent` | AI Structured Transform | AI & Governance | `default` | `ai_api_key` | Provider-independent AI node with secret redaction |
| `human_approval` | Human Approval Checkpoint | AI & Governance | `default` | None | Pauses workflow in `waiting_approval` until operator decision |
| `output` | Output | Core Flow | Terminal | None | Projects and returns final workflow result |
| `slack_notify` | Slack / Team Webhook | Communication & Ops | `default` | `http_bearer`, `webhook_url` | Dispatches formatted notifications to Slack/Mattermost/Discord |
| `github_api` | GitHub API Connector | Developer & Enterprise | `default` | `http_bearer` | Issues, pull requests, release notes, and workflow dispatches |
| `smtp_email` | Email Notification (SMTP/Outbox) | Communication & Ops | `default` | `smtp_auth` | Sends transactional email or records in local verifiable outbox |
| `object_storage` | Object Storage (S3 / Local Bucket) | Data & Storage | `default` | `s3_credentials` | `put_object`, `get_object`, `list_objects`, `delete_object` in isolated buckets |
| `vector_memory` | Vector Store & Embeddings | AI & Governance | `default` | None | Deterministic text embeddings & cosine-similarity semantic search (`upsert`/`query`) |
| `json_schema_validator` | JSON Schema Contract Validator | Data & Storage | `default` | None | Validates payload against required keys and schema rules |
| `graphql_query` | GraphQL Query / Mutation | Data & Storage | `default` | `http_bearer`, `http_header` | Typed GraphQL queries/mutations with variables and SSRF guard |
| `xml_html_parser` | XML / HTML Safe Extractor | Data & Storage | `default` | None | Extracts tag texts and attributes while blocking XXE entities |
| `crypto_hash_hmac` | Crypto Hash & HMAC Signer | Code & Files | `default` | None | Computes SHA-256, SHA-512, HMAC-SHA256, and Base64 digests |
| `rate_limit_throttle` | Rate Limit & Throttle Gate | Core Flow | `default` | None | Token-bucket rate limiter (`max_per_minute`) |
| `deduplicate_items` | Deduplicate Items | Core Flow | `default` | None | Deduplicates JSON object arrays by `key_field` |
