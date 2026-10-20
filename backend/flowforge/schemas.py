"""Pydantic schemas for FlowForge Community API and workflow engine."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from .compat import CompatBaseModel, ConfigDict, Field, field_validator

NodeType = Literal[
    "trigger",
    "webhook_trigger",
    "schedule_trigger",
    "set",
    "http_request",
    "if_condition",
    "switch",
    "merge",
    "filter",
    "loop",
    "wait",
    "code",
    "sql_query",
    "csv_json",
    "file_io",
    "skill",
    "ai_agent",
    "human_approval",
    "subworkflow",
    "error_handler",
    "output",
]

TRIGGER_NODE_TYPES: set[str] = {"trigger", "webhook_trigger", "schedule_trigger"}


class RetryPolicy(CompatBaseModel):
    max_attempts: int = Field(default=1, ge=1, le=5)
    backoff_ms: int = Field(default=100, ge=0, le=10_000)
    backoff_multiplier: float = Field(default=2.0, ge=1.0, le=5.0)


class Node(CompatBaseModel):
    id: str = Field(min_length=1, max_length=80, regex=r"^[A-Za-z0-9_-]+$" if hasattr(Field, "regex") else None)
    type: NodeType
    config: dict[str, Any] = Field(default_factory=dict)
    # Canvas coordinates are presentation metadata; the execution engine ignores them.
    position: dict[str, float] = Field(default_factory=lambda: {"x": 100.0, "y": 100.0})
    retry_policy: RetryPolicy | None = None
    on_error: Literal["fail", "continue_with_error", "fallback_value"] = "fail"

    @field_validator("id")
    @classmethod
    def validate_id_chars(cls, value: str) -> str:
        import re

        if not re.match(r"^[A-Za-z0-9_-]+$", value):
            raise ValueError("Node ID must match ^[A-Za-z0-9_-]+$")
        return value


class Edge(CompatBaseModel):
    source: str = Field(min_length=1, max_length=80)
    target: str = Field(min_length=1, max_length=80)
    # Optional branch handle for conditional routing ("true", "false", "default", or case key)
    source_handle: str | None = Field(default=None, max_length=40)
    label: str | None = Field(default=None, max_length=80)


class WorkflowDefinition(CompatBaseModel):
    schema_version: str = Field(default="1.0")
    nodes: list[Node] = Field(min_items=1, max_items=100)
    edges: list[Edge] = Field(default_factory=list, max_items=300)

    @field_validator("nodes")
    @classmethod
    def unique_node_ids(cls, nodes: list[Node]) -> list[Node]:
        if not nodes:
            raise ValueError("Workflow must contain at least one node")
        ids = [node.id for node in nodes]
        if len(ids) != len(set(ids)):
            raise ValueError("Node IDs must be unique")
        trigger_count = sum(node.type in TRIGGER_NODE_TYPES for node in nodes)
        if trigger_count != 1:
            raise ValueError("A workflow must contain exactly one trigger node")
        return nodes


class WorkflowCreate(CompatBaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)
    tags: list[str] = Field(default_factory=list)
    folder: str = Field(default="General", max_length=80)
    is_active: bool = True
    environment: Literal["dev", "staging", "prod"] = "dev"
    comment: str = Field(default="Initial version", max_length=255)
    definition: WorkflowDefinition


class WorkflowUpdate(CompatBaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    tags: list[str] | None = None
    folder: str | None = Field(default=None, max_length=80)
    is_active: bool | None = None
    environment: Literal["dev", "staging", "prod"] | None = None
    comment: str = Field(default="Updated workflow", max_length=255)
    definition: WorkflowDefinition


class WorkflowRead(CompatBaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    folder: str = "General"
    is_active: bool = True
    environment: str = "dev"
    version: int = 1
    definition: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class WorkflowVersionRead(CompatBaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    workflow_id: str
    version: int
    name: str
    environment: str
    comment: str
    definition: dict[str, Any]
    created_at: datetime


class ValidationIssue(CompatBaseModel):
    severity: Literal["error", "warning"]
    code: str
    message: str
    node_id: str | None = None
    edge_source: str | None = None
    edge_target: str | None = None


class ValidationReport(CompatBaseModel):
    valid: bool
    topological_order: list[str] = Field(default_factory=list)
    issues: list[ValidationIssue] = Field(default_factory=list)


class ExecuteRequest(CompatBaseModel):
    input: dict[str, Any] = Field(default_factory=dict)
    mode: Literal["sync", "queued"] = "sync"
    idempotency_key: str | None = Field(default=None, max_length=120)


class ApprovalDecisionRequest(CompatBaseModel):
    approved: bool
    comment: str = Field(default="", max_length=500)
    reviewer: str = Field(default="local-operator", max_length=120)


class ReplayRequest(CompatBaseModel):
    from_node_id: str | None = None
    override_input: dict[str, Any] | None = None


class ExecutionRead(CompatBaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    workflow_id: str
    workflow_version: int = 1
    trigger_type: str = "manual"
    status: str
    input_data: dict[str, Any]
    result_data: dict[str, Any] | None
    node_runs: list[dict[str, Any]] = Field(default_factory=list)
    checkpoint_state: dict[str, Any] | None = None
    error: str | None
    started_at: datetime
    finished_at: datetime | None


class ExecutionJobRead(CompatBaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    workflow_id: str
    execution_id: str | None
    trigger_type: str
    idempotency_key: str | None
    status: str
    input_data: dict[str, Any]
    attempts: int
    max_attempts: int
    worker_id: str | None
    heartbeat_at: datetime | None
    available_at: datetime
    last_error: str | None
    created_at: datetime
    updated_at: datetime


class CredentialCreate(CompatBaseModel):
    name: str = Field(min_length=1, max_length=120)
    kind: str = Field(min_length=1, max_length=60)
    description: str = Field(default="", max_length=255)
    data: dict[str, Any]


class CredentialRead(CompatBaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    kind: str
    description: str
    field_names: list[str]
    key_fingerprint: str
    created_at: datetime
    updated_at: datetime


class WebhookCreate(CompatBaseModel):
    workflow_id: str
    path_slug: str = Field(min_length=2, max_length=100)
    secret: str | None = Field(default=None, max_length=255)


class WebhookRead(CompatBaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    workflow_id: str
    path_slug: str
    has_secret: bool = False
    is_active: bool
    created_at: datetime


class ScheduleCreate(CompatBaseModel):
    workflow_id: str
    cron_expr: str = Field(default="*/5 * * * *", max_length=80)
    interval_seconds: int = Field(default=300, ge=10, le=86_400)
    input_template: dict[str, Any] = Field(default_factory=dict)


class ScheduleRead(CompatBaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    workflow_id: str
    cron_expr: str
    interval_seconds: int
    is_active: bool
    input_template: dict[str, Any]
    last_run_at: datetime | None
    next_run_at: datetime
    created_at: datetime


class ApiTokenCreate(CompatBaseModel):
    name: str = Field(min_length=1, max_length=120)
    role: Literal["viewer", "editor", "admin"] = "editor"
    scopes: list[str] = Field(default_factory=lambda: ["workflows:read", "workflows:write", "workflows:execute"])


class ApiTokenCreatedResponse(CompatBaseModel):
    id: str
    name: str
    token: str
    token_prefix: str
    role: str
    scopes: list[str]
    created_at: datetime


class ApiTokenRead(CompatBaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    token_prefix: str
    role: str
    scopes: list[str]
    is_revoked: bool
    created_at: datetime


class AuditLogRead(CompatBaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    actor: str
    action: str
    resource_type: str
    resource_id: str
    details: dict[str, Any]
    created_at: datetime


class AIDraftRequest(CompatBaseModel):
    prompt: str = Field(min_length=3, max_length=4000)
    provider: Literal["local", "ollama", "openai_compat", "gemini"] = "local"


class PromoteWorkflowRequest(CompatBaseModel):
    target_environment: Literal["dev", "staging", "prod"]
    comment: str = Field(default="Promoted environment", max_length=255)
