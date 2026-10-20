"""FlowForge Integration SDK and First-Party Node Catalog."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class FieldSpec:
    name: str
    type: str
    label: str
    required: bool = False
    default: Any = None
    description: str = ""
    options: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class NodeSpec:
    type: str
    version: str
    display_name: str
    category: str
    description: str
    documentation: str
    icon: str
    color: str
    is_trigger: bool = False
    is_terminal: bool = False
    output_handles: list[str] = field(default_factory=lambda: ["default"])
    credential_kinds: list[str] = field(default_factory=list)
    config_schema: list[FieldSpec] = field(default_factory=list)
    input_contract: str = "JSON object from upstream node(s)"
    output_contract: str = "JSON object passed to downstream node(s)"
    troubleshooting: str = ""
    license: str = "Apache-2.0"
    provenance: str = "FlowForge Community First-Party SDK"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


FIRST_PARTY_NODES: list[NodeSpec] = [
    NodeSpec(
        type="trigger",
        version="1.0.0",
        display_name="Manual Trigger",
        category="Triggers",
        description="Starts a workflow run from the editor, API, or CLI with a JSON input payload.",
        documentation="Emits the initial input object supplied when the workflow execution starts.",
        icon="play",
        color="#54c99b",
        is_trigger=True,
    ),
    NodeSpec(
        type="webhook_trigger",
        version="1.0.0",
        display_name="Webhook Trigger",
        category="Triggers",
        description="Starts a workflow when an authenticated HTTP POST webhook arrives at the registered slug.",
        documentation="Receives external HTTP POST payloads with optional HMAC-SHA256 signature verification and replay deduplication.",
        icon="webhook",
        color="#38bdf8",
        is_trigger=True,
        config_schema=[
            FieldSpec("path_slug", "string", "Webhook Slug", required=False, default="incoming-hook"),
            FieldSpec("require_signature", "boolean", "Require HMAC Signature", default=False),
        ],
    ),
    NodeSpec(
        type="schedule_trigger",
        version="1.0.0",
        display_name="Schedule Trigger",
        category="Triggers",
        description="Starts a workflow on a recurring interval or cron expression.",
        documentation="Fires automatically when the scheduler ticks past `next_run_at`.",
        icon="clock",
        color="#fbbf24",
        is_trigger=True,
        config_schema=[
            FieldSpec("cron_expr", "string", "Cron Expression", default="*/5 * * * *"),
            FieldSpec("interval_seconds", "number", "Interval Seconds", default=300),
        ],
    ),
    NodeSpec(
        type="set",
        version="1.0.0",
        display_name="Set / Edit Fields",
        category="Core Flow",
        description="Adds, overwrites, projects, or removes fields on the flowing JSON payload with `{{ expression }}` support.",
        documentation="Evaluates `{{ $input.key }}` or `{{ $nodes.id.key }}` templates inside `values`, merges them into the incoming object, and optionally removes or filters keys.",
        icon="braces",
        color="#a78bfa",
        config_schema=[
            FieldSpec("values", "json", "Values (JSON Object)", required=True, default={}),
            FieldSpec("keep_only_set", "boolean", "Keep Only Set Fields", default=False),
            FieldSpec("remove_fields", "json", "Remove Fields (List)", default=[]),
        ],
    ),
    NodeSpec(
        type="http_request",
        version="1.0.0",
        display_name="HTTP Request",
        category="Data & Storage",
        description="Performs an SSRF-guarded HTTP/HTTPS request with timeouts, retries, and credential injection.",
        documentation="Validates target URL and DNS resolution against SSRF policies, blocks loopback/private/cloud-metadata IPs by default, enforces response size caps, and stores the response under `response_field`.",
        icon="globe",
        color="#60a5fa",
        credential_kinds=["http_bearer", "http_header", "basic_auth"],
        config_schema=[
            FieldSpec("method", "select", "HTTP Method", required=True, default="GET", options=["GET", "POST", "PUT", "PATCH", "DELETE"]),
            FieldSpec("url", "string", "Target URL", required=True, default="https://api.example.com/v1/status"),
            FieldSpec("headers", "json", "Headers (JSON)", default={}),
            FieldSpec("body", "json", "JSON Body", default=None),
            FieldSpec("credential_name", "credential", "Credential Name", default=""),
            FieldSpec("timeout_seconds", "number", "Timeout (s)", default=10.0),
            FieldSpec("response_field", "string", "Target Field Name", default="http"),
        ],
    ),
    NodeSpec(
        type="if_condition",
        version="1.0.0",
        display_name="IF Condition",
        category="Core Flow",
        description="Routes execution along the `true` or `false` branch based on a deterministic comparison.",
        documentation="Evaluates `field` against `value` using `operator` (`eq`, `neq`, `gt`, `gte`, `lt`, `lte`, `contains`, `in`, `exists`, `regex`).",
        icon="split",
        color="#f472b6",
        output_handles=["true", "false"],
        config_schema=[
            FieldSpec("field", "string", "Field Path", required=True, default="ok"),
            FieldSpec("operator", "select", "Operator", required=True, default="eq", options=["eq", "neq", "gt", "gte", "lt", "lte", "contains", "in", "exists", "regex"]),
            FieldSpec("value", "json", "Compare Value", default=True),
        ],
    ),
    NodeSpec(
        type="switch",
        version="1.0.0",
        display_name="Switch / Router",
        category="Core Flow",
        description="Routes execution to named case handles or `default` based on a field's value.",
        documentation="Reads `field` from the incoming payload and activates the outgoing edge whose `source_handle` matches.",
        icon="git-branch",
        color="#fb923c",
        output_handles=["case_1", "case_2", "default"],
        config_schema=[
            FieldSpec("field", "string", "Routing Field", required=True, default="tier"),
            FieldSpec("cases", "json", "Allowed Case Values", default=["gold", "silver"]),
        ],
    ),
    NodeSpec(
        type="merge",
        version="1.0.0",
        display_name="Merge Branches",
        category="Core Flow",
        description="Combines data from multiple incoming parent branches.",
        documentation="Supports `shallow_merge`, `deep_merge`, and `collect_branches`.",
        icon="git-merge",
        color="#34d399",
        config_schema=[
            FieldSpec("mode", "select", "Merge Mode", default="shallow_merge", options=["shallow_merge", "deep_merge", "collect_branches"]),
        ],
    ),
    NodeSpec(
        type="filter",
        version="1.0.0",
        display_name="Filter Items",
        category="Core Flow",
        description="Filters an array of items in `list_field` using a comparison operator.",
        documentation="Iterates over `list_field` and keeps only elements matching `item_field` `operator` `value`.",
        icon="filter",
        color="#2dd4bf",
        config_schema=[
            FieldSpec("list_field", "string", "Array Field", default="items"),
            FieldSpec("item_field", "string", "Item Key", default=""),
            FieldSpec("operator", "select", "Operator", default="eq", options=["eq", "neq", "gt", "gte", "lt", "lte", "contains", "exists"]),
            FieldSpec("value", "json", "Compare Value", default=True),
            FieldSpec("output_field", "string", "Output Field", default="filtered_items"),
        ],
    ),
    NodeSpec(
        type="loop",
        version="1.0.0",
        display_name="Loop / Batch Transform",
        category="Core Flow",
        description="Iterates over an array field with a bounded `max_iterations` cap and applies a template.",
        documentation="Processes each item in `list_field` up to `max_iterations` (default 100) and writes results to `output_field`.",
        icon="repeat",
        color="#818cf8",
        config_schema=[
            FieldSpec("list_field", "string", "Source Array Field", required=True, default="items"),
            FieldSpec("template", "json", "Item Mapping Template", default={"item": "{{ $item }}"}),
            FieldSpec("max_iterations", "number", "Max Iterations", default=100),
            FieldSpec("output_field", "string", "Output Array Field", default="results"),
        ],
    ),
    NodeSpec(
        type="wait",
        version="1.0.0",
        display_name="Wait / Delay",
        category="Core Flow",
        description="Pauses execution for a bounded number of milliseconds and records timing metadata.",
        documentation="Sleeps up to `delay_ms` and attaches `_wait` metadata.",
        icon="timer",
        color="#94a3b8",
        config_schema=[FieldSpec("delay_ms", "number", "Delay (ms)", default=50)],
    ),
    NodeSpec(
        type="code",
        version="1.0.0",
        display_name="Code (Isolated Python)",
        category="Code & Files",
        description="Executes pure data-transformation Python in an isolated subprocess with restricted builtins and timeout.",
        documentation="Runs in `python -I` subprocess with no environment variables, no filesystem/network imports, and a hard timeout.",
        icon="code",
        color="#f59e0b",
        config_schema=[
            FieldSpec("code", "code", "Python Code", required=True, default="result = {**data, 'computed': True}"),
            FieldSpec("timeout_seconds", "number", "Timeout (s)", default=3.0),
        ],
    ),
    NodeSpec(
        type="sql_query",
        version="1.0.0",
        display_name="SQL Query (Parameterized)",
        category="Data & Storage",
        description="Executes a parameterized SQL query against SQLite or PostgreSQL using safe `:param` bindings.",
        documentation="Supports `SELECT` and safe parameterized statements. Blocks multi-statement SQL injection.",
        icon="database",
        color="#38bdf8",
        credential_kinds=["database_url"],
        config_schema=[
            FieldSpec("query", "code", "SQL Query (use :param bindings)", required=True, default="SELECT :val AS echoed"),
            FieldSpec("params", "json", "Query Parameters (JSON)", default={"val": "hello"}),
            FieldSpec("output_field", "string", "Output Field", default="rows"),
        ],
    ),
    NodeSpec(
        type="csv_json",
        version="1.0.0",
        display_name="CSV / JSON Processor",
        category="Data & Storage",
        description="Parses CSV text into JSON records or formats an array of JSON objects into CSV text.",
        documentation="Deterministic in-memory CSV/JSON conversion using Python's `csv` module.",
        icon="table",
        color="#4ade80",
        config_schema=[
            FieldSpec("mode", "select", "Conversion Mode", default="csv_to_json", options=["csv_to_json", "json_to_csv"]),
            FieldSpec("source_field", "string", "Source Field", default="csv_text"),
            FieldSpec("target_field", "string", "Target Field", default="records"),
            FieldSpec("delimiter", "string", "Delimiter", default=","),
        ],
    ),
    NodeSpec(
        type="file_io",
        version="1.0.0",
        display_name="Sandboxed File I/O",
        category="Code & Files",
        description="Reads or writes JSON/text files strictly inside the permitted `FLOWFORGE_ALLOWED_FILE_DIR` sandbox.",
        documentation="Prevents path traversal (`..`) and absolute paths outside the sandbox directory.",
        icon="file-text",
        color="#cbd5e1",
        config_schema=[
            FieldSpec("operation", "select", "Operation", default="write_json", options=["write_json", "read_json", "write_text", "read_text"]),
            FieldSpec("path", "string", "Relative Path inside Sandbox", required=True, default="output.json"),
            FieldSpec("source_field", "string", "Field to Write (optional)", default=""),
            FieldSpec("target_field", "string", "Field to Store Read Data", default="file_data"),
        ],
    ),
    NodeSpec(
        type="skill",
        version="1.0.0",
        display_name="Run FlowForge Skill",
        category="AI & Governance",
        description="Invokes a versioned, integrity-verified FlowForge Skill package.",
        documentation="Verifies the skill's SHA-256 manifest integrity hash before running its deterministic tool handler.",
        icon="sparkles",
        color="#c084fc",
        config_schema=[
            FieldSpec("skill_id", "string", "Skill ID", required=True, default="csv-json-transformation-helper"),
            FieldSpec("skill_input", "json", "Skill Input Overrides", default={}),
            FieldSpec("output_field", "string", "Output Field", default="skill_output"),
        ],
    ),
    NodeSpec(
        type="ai_agent",
        version="1.0.0",
        display_name="AI Structured Transform",
        category="AI & Governance",
        description="Runs a provider-independent AI adapter (local, Ollama, OpenAI-compatible, or Gemini) with secret redaction.",
        documentation="Redacts secrets from context before invoking the configured provider and validates output against `required_keys`.",
        icon="bot",
        color="#e879f9",
        credential_kinds=["ai_api_key"],
        config_schema=[
            FieldSpec("provider", "select", "Provider", default="local", options=["local", "ollama", "openai_compat", "gemini"]),
            FieldSpec("prompt", "string", "Instruction Prompt", required=True, default="Summarize input payload"),
            FieldSpec("required_keys", "json", "Required Output Schema Keys", default=["summary"]),
            FieldSpec("output_field", "string", "Output Field", default="ai_result"),
        ],
    ),
    NodeSpec(
        type="human_approval",
        version="1.0.0",
        display_name="Human Approval Checkpoint",
        category="AI & Governance",
        description="Pauses workflow execution in `waiting_approval` status until a human operator approves or rejects the run.",
        documentation="Persists an execution checkpoint so the workflow can be safely resumed via `/api/executions/{id}/approve`.",
        icon="shield-check",
        color="#facc15",
        config_schema=[
            FieldSpec("message", "string", "Approval Prompt", default="Please review and approve this workflow execution."),
            FieldSpec("auto_approve_in_test", "boolean", "Auto-Approve if `_approved: true` in payload", default=False),
        ],
    ),
    NodeSpec(
        type="subworkflow",
        version="1.0.0",
        display_name="Execute Sub-Workflow",
        category="Core Flow",
        description="Invokes another saved workflow with recursion depth protection.",
        documentation="Allows composing reusable modular sub-workflows up to depth 3.",
        icon="layers",
        color="#22d3ee",
        config_schema=[
            FieldSpec("subworkflow_id", "string", "Target Workflow ID", default=""),
            FieldSpec("output_field", "string", "Output Field", default="subworkflow_result"),
        ],
    ),
    NodeSpec(
        type="error_handler",
        version="1.0.0",
        display_name="Error Triage / Fallback",
        category="Core Flow",
        description="Normalizes upstream `_errors` or provides structured fallback values.",
        documentation="Inspects incoming data for `_node_errors` and emits a clean recovery record.",
        icon="alert-triangle",
        color="#f87171",
        config_schema=[
            FieldSpec("fallback_values", "json", "Fallback Object", default={"recovered": True}),
        ],
    ),
    NodeSpec(
        type="output",
        version="1.0.0",
        display_name="Output",
        category="Core Flow",
        description="Terminal node that returns the final workflow result (or selected fields).",
        documentation="Passes through merged upstream data or projects `select_fields` if specified.",
        icon="arrow-right",
        color="#72b7ff",
        is_terminal=True,
        config_schema=[
            FieldSpec("select_fields", "json", "Select Specific Fields (optional list)", default=[]),
        ],
    ),
]

NODE_SPEC_MAP: dict[str, NodeSpec] = {spec.type: spec for spec in FIRST_PARTY_NODES}


def list_node_specs(category: str | None = None) -> list[dict[str, Any]]:
    specs = FIRST_PARTY_NODES
    if category:
        specs = [s for s in specs if s.category.lower() == category.lower()]
    return [s.to_dict() for s in specs]


def get_node_spec(node_type: str) -> NodeSpec | None:
    return NODE_SPEC_MAP.get(node_type)
