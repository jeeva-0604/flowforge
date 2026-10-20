"""FlowForge Community FastAPI Control Plane & API."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware

from .ai import (
    diagnose_failed_execution,
    draft_workflow_from_prompt,
    explain_workflow,
    run_ai_benchmarks,
)
from .config import (
    allow_private_http,
    bootstrap_api_token,
    cors_origins,
    is_default_master_key,
    require_auth,
)
from .db import Session, engine, get_session
from .engine import (
    WorkflowValidationError,
    diff_workflow_definitions,
    execute_workflow_detailed,
    topological_order,
    validate_workflow_graph,
)
from .migrations import MIGRATIONS, run_migrations
from .models import (
    ApiToken,
    AuditLog,
    Credential,
    Execution,
    ExecutionJob,
    ScheduleTrigger,
    WebhookEndpoint,
    Workflow,
    WorkflowVersion,
    utc_now,
)
from .schemas import (
    AIDraftRequest,
    ApiTokenCreate,
    ApiTokenCreatedResponse,
    ApiTokenRead,
    ApprovalDecisionRequest,
    AuditLogRead,
    CredentialCreate,
    CredentialRead,
    ExecuteRequest,
    ExecutionJobRead,
    ExecutionRead,
    PromoteWorkflowRequest,
    ReplayRequest,
    ScheduleCreate,
    ScheduleRead,
    ValidationReport,
    WebhookCreate,
    WebhookRead,
    WorkflowCreate,
    WorkflowDefinition,
    WorkflowRead,
    WorkflowUpdate,
    WorkflowVersionRead,
)
from .sdk import list_node_specs
from .security import (
    CredentialVault,
    RateLimiter,
    SecurityError,
    generate_api_token,
    hash_token,
    key_fingerprint,
    verify_webhook_signature,
)
from .skills import (
    SkillValidationError,
    execute_skill,
    list_skills,
    validate_skill_manifest,
)
from .templates import get_template, list_templates
from .worker import (
    enqueue_execution_job,
    get_queue_metrics,
    load_decrypted_credentials,
    process_next_job,
    recover_stale_jobs,
    tick_schedules,
)

# Ensure tables and migrations exist on startup
run_migrations(engine)

app = FastAPI(
    title="FlowForge Community API",
    version="0.4.0",
    description="Independent, self-hosted, open-source workflow automation platform.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins(),
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-API-Key", "X-FlowForge-Signature", "X-FlowForge-Delivery"],
)

_rate_limiter = RateLimiter(max_requests=300, window_seconds=60.0)


def record_audit(
    session: Session,
    action: str,
    resource_type: str,
    resource_id: str,
    details: dict[str, Any] | None = None,
    actor: str = "local-operator",
) -> None:
    entry = AuditLog(
        id=str(uuid4()),
        actor=actor,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details=details or {},
        created_at=utc_now(),
    )
    session.add(entry)
    session.commit()


def require_scope(required_scope: str):
    """Dependency enforcing API token authentication & RBAC scopes when enabled
    or when an explicit token header is provided.
    """

    def _verifier(
        request: Request,
        x_api_key: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
        session: Session = Depends(get_session),
    ) -> str:
        client_host = request.client.host if request.client else "local"
        if not _rate_limiter.check(f"{client_host}:{required_scope}"):
            raise HTTPException(status_code=429, detail="Rate limit exceeded")

        raw_token = x_api_key
        if not raw_token and authorization and authorization.lower().startswith("bearer "):
            raw_token = authorization[7:].strip()

        if not raw_token:
            if require_auth():
                raise HTTPException(status_code=401, detail="Authentication required: provide X-API-Key or Bearer token")
            return "local-operator"

        env_token = bootstrap_api_token()
        if env_token and raw_token == env_token:
            return "bootstrap-admin"

        t_hash = hash_token(raw_token)
        token_rec = session.query(ApiToken).filter(ApiToken.token_hash == t_hash).first()
        if token_rec is None or token_rec.is_revoked:
            raise HTTPException(status_code=401, detail="Invalid or revoked API token")
        if token_rec.expires_at:
            exp = token_rec.expires_at
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            if exp < utc_now():
                raise HTTPException(status_code=401, detail="API token has expired")

        scopes = set(token_rec.scopes or [])
        if token_rec.role != "admin" and "admin:*" not in scopes and required_scope not in scopes:
            raise HTTPException(status_code=403, detail=f"Token lacks required scope: {required_scope}")
        return f"token:{token_rec.name}"

    return _verifier


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/live")
def health_live() -> dict[str, str]:
    return {"status": "alive", "version": "0.4.0"}


@app.get("/health/ready")
def health_ready(session: Session = Depends(get_session)) -> dict[str, Any]:
    wf_count = len(session.query(Workflow).all())
    return {
        "status": "ready",
        "version": "0.4.0",
        "workflows_registered": wf_count,
        "migrations_applied": [m[0] for m in MIGRATIONS],
    }


@app.get("/api/system/diagnostics")
def system_diagnostics(session: Session = Depends(get_session)) -> dict[str, Any]:
    workflows = session.query(Workflow).all()
    executions = session.query(Execution).all()
    creds = session.query(Credential).all()
    webhooks = session.query(WebhookEndpoint).all()
    schedules = session.query(ScheduleTrigger).all()
    queue_stats = get_queue_metrics(session)

    succeeded = sum(1 for e in executions if e.status == "succeeded")
    failed = sum(1 for e in executions if e.status == "failed")
    waiting = sum(1 for e in executions if e.status == "waiting_approval")

    return {
        "version": "0.4.0",
        "status": "healthy",
        "counts": {
            "workflows": len(workflows),
            "executions": len(executions),
            "executions_succeeded": succeeded,
            "executions_failed": failed,
            "executions_waiting_approval": waiting,
            "credentials": len(creds),
            "webhooks": len(webhooks),
            "schedules": len(schedules),
            "integrations": len(list_node_specs()),
            "skills": len(list_skills()),
            "templates": len(list_templates()),
        },
        "queue": queue_stats,
        "security": {
            "auth_required": require_auth(),
            "using_default_dev_master_key": is_default_master_key(),
            "master_key_fingerprint": key_fingerprint(),
            "ssrf_private_ip_blocked": not allow_private_http(),
            "code_execution_isolated": True,
        },
        "migrations": [m[0] for m in MIGRATIONS],
    }


@app.post("/api/workflows/validate", response_model=ValidationReport)
def validate_workflow_endpoint(payload: WorkflowDefinition):
    return validate_workflow_graph(payload)


@app.post("/api/workflows", response_model=WorkflowRead, status_code=201)
def create_workflow(
    payload: WorkflowCreate,
    session: Session = Depends(get_session),
    actor: str = Depends(require_scope("workflows:write")),
):
    try:
        topological_order(payload.definition)
    except WorkflowValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    def_json = payload.definition.model_dump(mode="json")
    workflow = Workflow(
        id=str(uuid4()),
        name=payload.name,
        description=payload.description,
        tags=payload.tags,
        folder=payload.folder,
        is_active=payload.is_active,
        environment=payload.environment,
        version=1,
        definition=def_json,
    )
    session.add(workflow)
    session.commit()
    session.refresh(workflow)

    ver = WorkflowVersion(
        id=str(uuid4()),
        workflow_id=workflow.id,
        version=1,
        name=workflow.name,
        environment=workflow.environment,
        comment=payload.comment or "Initial version",
        definition=def_json,
    )
    session.add(ver)
    session.commit()
    record_audit(session, "workflow.create", "workflow", workflow.id, {"name": workflow.name, "version": 1}, actor=actor)
    return workflow


@app.get("/api/workflows", response_model=list[WorkflowRead])
def list_workflows(
    folder: str | None = None,
    environment: str | None = None,
    tag: str | None = None,
    session: Session = Depends(get_session),
    _actor: str = Depends(require_scope("workflows:read")),
):
    items = session.query(Workflow).order_by(Workflow.created_at.desc()).all()
    if folder:
        items = [w for w in items if getattr(w, "folder", "General") == folder]
    if environment:
        items = [w for w in items if getattr(w, "environment", "dev") == environment]
    if tag:
        items = [w for w in items if tag in (getattr(w, "tags", []) or [])]
    return items


@app.get("/api/workflows/{workflow_id}", response_model=WorkflowRead)
def get_workflow(
    workflow_id: str,
    session: Session = Depends(get_session),
    _actor: str = Depends(require_scope("workflows:read")),
):
    workflow = session.get(Workflow, workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return workflow


@app.put("/api/workflows/{workflow_id}", response_model=WorkflowRead)
def update_workflow(
    workflow_id: str,
    payload: WorkflowUpdate,
    session: Session = Depends(get_session),
    actor: str = Depends(require_scope("workflows:write")),
):
    workflow = session.get(Workflow, workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    try:
        topological_order(payload.definition)
    except WorkflowValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    def_json = payload.definition.model_dump(mode="json")
    workflow.name = payload.name
    if payload.description is not None:
        workflow.description = payload.description
    if payload.tags is not None:
        workflow.tags = payload.tags
    if payload.folder is not None:
        workflow.folder = payload.folder
    if payload.is_active is not None:
        workflow.is_active = payload.is_active
    if payload.environment is not None:
        workflow.environment = payload.environment
    workflow.version = (getattr(workflow, "version", 1) or 1) + 1
    workflow.definition = def_json
    workflow.updated_at = utc_now()
    session.add(workflow)
    session.commit()
    session.refresh(workflow)

    ver = WorkflowVersion(
        id=str(uuid4()),
        workflow_id=workflow.id,
        version=workflow.version,
        name=workflow.name,
        environment=workflow.environment,
        comment=payload.comment or f"Revision {workflow.version}",
        definition=def_json,
    )
    session.add(ver)
    session.commit()
    record_audit(
        session,
        "workflow.update",
        "workflow",
        workflow.id,
        {"name": workflow.name, "version": workflow.version},
        actor=actor,
    )
    return workflow


@app.delete("/api/workflows/{workflow_id}")
def delete_workflow(
    workflow_id: str,
    session: Session = Depends(get_session),
    actor: str = Depends(require_scope("workflows:write")),
) -> dict[str, Any]:
    workflow = session.get(Workflow, workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    session.delete(workflow)
    session.commit()
    record_audit(session, "workflow.delete", "workflow", workflow_id, {"name": workflow.name}, actor=actor)
    return {"deleted": True, "id": workflow_id}


@app.post("/api/workflows/{workflow_id}/duplicate", response_model=WorkflowRead, status_code=201)
def duplicate_workflow(
    workflow_id: str,
    session: Session = Depends(get_session),
    actor: str = Depends(require_scope("workflows:write")),
):
    source = session.get(Workflow, workflow_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    copy_wf = Workflow(
        id=str(uuid4()),
        name=f"{source.name} (Copy)",
        description=getattr(source, "description", ""),
        tags=list(getattr(source, "tags", []) or []),
        folder=getattr(source, "folder", "General"),
        is_active=getattr(source, "is_active", True),
        environment="dev",
        version=1,
        definition=dict(source.definition),
    )
    session.add(copy_wf)
    session.commit()
    session.refresh(copy_wf)
    ver = WorkflowVersion(
        id=str(uuid4()),
        workflow_id=copy_wf.id,
        version=1,
        name=copy_wf.name,
        environment=copy_wf.environment,
        comment=f"Duplicated from {source.id}",
        definition=dict(copy_wf.definition),
    )
    session.add(ver)
    session.commit()
    record_audit(session, "workflow.duplicate", "workflow", copy_wf.id, {"source_id": source.id}, actor=actor)
    return copy_wf


@app.post("/api/workflows/{workflow_id}/promote", response_model=WorkflowRead)
def promote_workflow(
    workflow_id: str,
    payload: PromoteWorkflowRequest,
    session: Session = Depends(get_session),
    actor: str = Depends(require_scope("workflows:write")),
):
    workflow = session.get(Workflow, workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    prev_env = getattr(workflow, "environment", "dev")
    workflow.environment = payload.target_environment
    workflow.version = (getattr(workflow, "version", 1) or 1) + 1
    workflow.updated_at = utc_now()
    session.add(workflow)
    session.commit()
    session.refresh(workflow)

    ver = WorkflowVersion(
        id=str(uuid4()),
        workflow_id=workflow.id,
        version=workflow.version,
        name=workflow.name,
        environment=workflow.environment,
        comment=payload.comment or f"Promoted {prev_env} -> {payload.target_environment}",
        definition=dict(workflow.definition),
    )
    session.add(ver)
    session.commit()
    record_audit(
        session,
        "workflow.promote",
        "workflow",
        workflow.id,
        {"from": prev_env, "to": payload.target_environment, "version": workflow.version},
        actor=actor,
    )
    return workflow


@app.get("/api/workflows/{workflow_id}/versions", response_model=list[WorkflowVersionRead])
def list_workflow_versions(
    workflow_id: str,
    session: Session = Depends(get_session),
    _actor: str = Depends(require_scope("workflows:read")),
):
    workflow = session.get(Workflow, workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return (
        session.query(WorkflowVersion)
        .filter(WorkflowVersion.workflow_id == workflow_id)
        .order_by(WorkflowVersion.version.desc())
        .all()
    )


@app.get("/api/workflows/{workflow_id}/versions/{version_a}/diff/{version_b}")
def diff_workflow_versions(
    workflow_id: str,
    version_a: int,
    version_b: int,
    session: Session = Depends(get_session),
    _actor: str = Depends(require_scope("workflows:read")),
) -> dict[str, Any]:
    versions = (
        session.query(WorkflowVersion)
        .filter(WorkflowVersion.workflow_id == workflow_id)
        .all()
    )
    va = next((v for v in versions if v.version == version_a), None)
    vb = next((v for v in versions if v.version == version_b), None)
    if va is None or vb is None:
        raise HTTPException(status_code=404, detail="Requested workflow version not found")
    return {
        "workflow_id": workflow_id,
        "version_a": version_a,
        "version_b": version_b,
        "diff": diff_workflow_definitions(va.definition, vb.definition),
    }


@app.post("/api/workflows/{workflow_id}/versions/{version}/restore", response_model=WorkflowRead)
def restore_workflow_version(
    workflow_id: str,
    version: int,
    session: Session = Depends(get_session),
    actor: str = Depends(require_scope("workflows:write")),
):
    workflow = session.get(Workflow, workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    versions = (
        session.query(WorkflowVersion)
        .filter(WorkflowVersion.workflow_id == workflow_id)
        .all()
    )
    target = next((v for v in versions if v.version == version), None)
    if target is None:
        raise HTTPException(status_code=404, detail="Version not found")

    workflow.name = target.name
    workflow.definition = dict(target.definition)
    workflow.version = (getattr(workflow, "version", 1) or 1) + 1
    workflow.updated_at = utc_now()
    session.add(workflow)
    session.commit()
    session.refresh(workflow)

    new_ver = WorkflowVersion(
        id=str(uuid4()),
        workflow_id=workflow.id,
        version=workflow.version,
        name=workflow.name,
        environment=workflow.environment,
        comment=f"Restored from version {version}",
        definition=dict(target.definition),
    )
    session.add(new_ver)
    session.commit()
    record_audit(
        session,
        "workflow.restore_version",
        "workflow",
        workflow.id,
        {"restored_from": version, "new_version": workflow.version},
        actor=actor,
    )
    return workflow


@app.get("/api/workflows/{workflow_id}/export")
def export_workflow(
    workflow_id: str,
    session: Session = Depends(get_session),
    _actor: str = Depends(require_scope("workflows:read")),
) -> dict[str, Any]:
    workflow = session.get(Workflow, workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return {
        "format": "flowforge-workflow-export",
        "format_version": "1.0",
        "exported_at": utc_now().isoformat(),
        "workflow": {
            "name": workflow.name,
            "description": getattr(workflow, "description", ""),
            "tags": getattr(workflow, "tags", []),
            "folder": getattr(workflow, "folder", "General"),
            "environment": getattr(workflow, "environment", "dev"),
            "definition": workflow.definition,
        },
    }


@app.post("/api/workflows/import", response_model=WorkflowRead, status_code=201)
def import_workflow(
    payload: dict[str, Any],
    session: Session = Depends(get_session),
    actor: str = Depends(require_scope("workflows:write")),
):
    wf_block = payload.get("workflow", payload)
    if not isinstance(wf_block, dict) or "definition" not in wf_block:
        raise HTTPException(status_code=422, detail="Import payload must include workflow.definition")
    try:
        definition = WorkflowDefinition.model_validate(wf_block["definition"])
        topological_order(definition)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Invalid imported workflow: {exc}") from exc

    create_req = WorkflowCreate(
        name=str(wf_block.get("name") or "Imported Workflow")[:120],
        description=str(wf_block.get("description") or ""),
        tags=list(wf_block.get("tags") or []),
        folder=str(wf_block.get("folder") or "General"),
        environment="dev",
        comment="Imported from JSON artifact",
        definition=definition,
    )
    return create_workflow(create_req, session=session, actor=actor)


@app.post("/api/workflows/{workflow_id}/execute", response_model=ExecutionRead, status_code=201)
def execute_saved_workflow(
    workflow_id: str,
    payload: ExecuteRequest,
    session: Session = Depends(get_session),
    actor: str = Depends(require_scope("workflows:execute")),
):
    workflow = session.get(Workflow, workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found")

    if payload.mode == "queued":
        job = enqueue_execution_job(
            session,
            workflow_id,
            payload.input,
            trigger_type="queued",
            idempotency_key=payload.idempotency_key,
        )
        processed = process_next_job(session, worker_id="api-inline-worker")
        if processed and processed.execution_id:
            ex = session.get(Execution, processed.execution_id)
            if ex is not None:
                return ex

    execution = Execution(
        id=str(uuid4()),
        workflow_id=workflow_id,
        workflow_version=getattr(workflow, "version", 1) or 1,
        trigger_type="manual",
        status="running",
        input_data=payload.input,
        node_runs=[],
    )
    session.add(execution)
    session.commit()

    creds_map, secret_vals = load_decrypted_credentials(session)

    def _load_sub(sub_id: str) -> WorkflowDefinition | None:
        sub_wf = session.get(Workflow, sub_id)
        return WorkflowDefinition.model_validate(sub_wf.definition) if sub_wf else None

    try:
        definition = WorkflowDefinition.model_validate(workflow.definition)
        detailed = execute_workflow_detailed(
            definition,
            payload.input,
            credentials_map=creds_map,
            secret_values=secret_vals,
            subworkflow_loader=_load_sub,
        )
        execution.status = detailed["status"]
        execution.result_data = detailed["result_data"]
        execution.node_runs = detailed["node_runs"]
        execution.checkpoint_state = detailed["checkpoint_state"]
        execution.error = detailed["error"]
    except (WorkflowValidationError, SecurityError, ValueError, TypeError) as exc:
        execution.status = "failed"
        execution.result_data = None
        execution.error = str(exc)[:4000]
    except Exception:
        execution.status = "failed"
        execution.result_data = None
        execution.error = "Unexpected execution error"

    execution.finished_at = datetime.now(timezone.utc)
    session.add(execution)
    session.commit()
    session.refresh(execution)
    record_audit(
        session,
        "workflow.execute",
        "execution",
        execution.id,
        {"workflow_id": workflow_id, "status": execution.status},
        actor=actor,
    )
    return execution


@app.get("/api/executions", response_model=list[ExecutionRead])
def list_executions(
    workflow_id: str | None = None,
    status: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    session: Session = Depends(get_session),
    _actor: str = Depends(require_scope("workflows:read")),
):
    query = session.query(Execution)
    if workflow_id is not None:
        query = query.filter(Execution.workflow_id == workflow_id)
    if status is not None:
        query = query.filter(Execution.status == status)
    return query.order_by(Execution.started_at.desc()).limit(limit).all()


@app.get("/api/executions/{execution_id}", response_model=ExecutionRead)
def get_execution(
    execution_id: str,
    session: Session = Depends(get_session),
    _actor: str = Depends(require_scope("workflows:read")),
):
    execution = session.get(Execution, execution_id)
    if execution is None:
        raise HTTPException(status_code=404, detail="Execution not found")
    return execution


@app.post("/api/executions/{execution_id}/approve", response_model=ExecutionRead)
def approve_execution_checkpoint(
    execution_id: str,
    payload: ApprovalDecisionRequest,
    session: Session = Depends(get_session),
    actor: str = Depends(require_scope("workflows:execute")),
):
    execution = session.get(Execution, execution_id)
    if execution is None:
        raise HTTPException(status_code=404, detail="Execution not found")
    if execution.status != "waiting_approval":
        raise HTTPException(status_code=409, detail=f"Execution is in state {execution.status!r}, not 'waiting_approval'")

    workflow = session.get(Workflow, execution.workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail="Associated workflow not found")

    if not payload.approved:
        execution.status = "cancelled"
        execution.error = f"Rejected by {payload.reviewer}: {payload.comment or 'No comment'}"
        execution.finished_at = utc_now()
        session.add(execution)
        session.commit()
        session.refresh(execution)
        record_audit(session, "execution.reject", "execution", execution.id, {"reviewer": payload.reviewer}, actor=actor)
        return execution

    ckpt = execution.checkpoint_state or {}
    paused_node_id = ckpt.get("paused_node_id")
    saved_outputs = ckpt.get("outputs") or {}
    approved_nodes = dict(ckpt.get("approved_nodes") or {})
    if paused_node_id:
        approved_nodes[paused_node_id] = True

    creds_map, secret_vals = load_decrypted_credentials(session)
    definition = WorkflowDefinition.model_validate(workflow.definition)
    detailed = execute_workflow_detailed(
        definition,
        execution.input_data,
        credentials_map=creds_map,
        secret_values=secret_vals,
        initial_node_outputs=saved_outputs,
        approved_nodes=approved_nodes,
        start_from_node_id=paused_node_id,
    )
    execution.status = detailed["status"]
    execution.result_data = detailed["result_data"]
    execution.node_runs = detailed["node_runs"]
    execution.checkpoint_state = detailed["checkpoint_state"]
    execution.error = detailed["error"]
    execution.finished_at = utc_now()
    session.add(execution)
    session.commit()
    session.refresh(execution)
    record_audit(session, "execution.approve", "execution", execution.id, {"reviewer": payload.reviewer}, actor=actor)
    return execution


@app.post("/api/executions/{execution_id}/replay", response_model=ExecutionRead, status_code=201)
def replay_execution(
    execution_id: str,
    payload: ReplayRequest,
    session: Session = Depends(get_session),
    actor: str = Depends(require_scope("workflows:execute")),
):
    orig = session.get(Execution, execution_id)
    if orig is None:
        raise HTTPException(status_code=404, detail="Execution not found")
    workflow = session.get(Workflow, orig.workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found")

    replay_input = payload.override_input if payload.override_input is not None else orig.input_data
    cached_outputs = (orig.checkpoint_state or {}).get("outputs", {}) if payload.from_node_id else None

    creds_map, secret_vals = load_decrypted_credentials(session)
    definition = WorkflowDefinition.model_validate(workflow.definition)
    detailed = execute_workflow_detailed(
        definition,
        replay_input,
        credentials_map=creds_map,
        secret_values=secret_vals,
        initial_node_outputs=cached_outputs,
        start_from_node_id=payload.from_node_id,
    )
    new_exec = Execution(
        id=str(uuid4()),
        workflow_id=workflow.id,
        workflow_version=getattr(workflow, "version", 1) or 1,
        trigger_type="replay",
        status=detailed["status"],
        input_data=replay_input,
        result_data=detailed["result_data"],
        node_runs=detailed["node_runs"],
        checkpoint_state=detailed["checkpoint_state"],
        error=detailed["error"],
        started_at=utc_now(),
        finished_at=utc_now(),
    )
    session.add(new_exec)
    session.commit()
    session.refresh(new_exec)
    record_audit(
        session,
        "execution.replay",
        "execution",
        new_exec.id,
        {"source_execution_id": execution_id, "from_node_id": payload.from_node_id},
        actor=actor,
    )
    return new_exec


@app.post("/api/executions/{execution_id}/cancel", response_model=ExecutionRead)
def cancel_execution(
    execution_id: str,
    session: Session = Depends(get_session),
    actor: str = Depends(require_scope("workflows:execute")),
):
    execution = session.get(Execution, execution_id)
    if execution is None:
        raise HTTPException(status_code=404, detail="Execution not found")
    execution.status = "cancelled"
    execution.error = "Cancelled by operator"
    execution.finished_at = utc_now()
    session.add(execution)
    session.commit()
    session.refresh(execution)
    record_audit(session, "execution.cancel", "execution", execution.id, {}, actor=actor)
    return execution


@app.get("/api/executions/{execution_id}/diagnose")
def diagnose_execution_endpoint(
    execution_id: str,
    session: Session = Depends(get_session),
    _actor: str = Depends(require_scope("workflows:read")),
) -> dict[str, Any]:
    execution = session.get(Execution, execution_id)
    if execution is None:
        raise HTTPException(status_code=404, detail="Execution not found")
    workflow = session.get(Workflow, execution.workflow_id)
    wf_def = workflow.definition if workflow else {"nodes": [], "edges": []}
    exec_dict = {
        "id": execution.id,
        "status": execution.status,
        "error": execution.error,
        "node_runs": getattr(execution, "node_runs", []) or [],
    }
    return diagnose_failed_execution(wf_def, exec_dict)


# --- Queue & Worker Endpoints ---


@app.get("/api/queue/jobs", response_model=list[ExecutionJobRead])
def list_queue_jobs(
    status: str | None = None,
    session: Session = Depends(get_session),
    _actor: str = Depends(require_scope("workflows:read")),
):
    q = session.query(ExecutionJob)
    if status:
        q = q.filter(ExecutionJob.status == status)
    return q.order_by(ExecutionJob.created_at.desc()).limit(50).all()


@app.post("/api/queue/jobs", response_model=ExecutionJobRead, status_code=201)
def enqueue_job_endpoint(
    workflow_id: str,
    payload: ExecuteRequest,
    session: Session = Depends(get_session),
    actor: str = Depends(require_scope("workflows:execute")),
):
    wf = session.get(Workflow, workflow_id)
    if wf is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    job = enqueue_execution_job(
        session,
        workflow_id,
        payload.input,
        trigger_type="queued",
        idempotency_key=payload.idempotency_key,
    )
    record_audit(session, "queue.enqueue", "execution_job", job.id, {"workflow_id": workflow_id}, actor=actor)
    return job


@app.post("/api/queue/worker/run-next")
def worker_run_next_endpoint(
    worker_id: str = "worker-api-1",
    session: Session = Depends(get_session),
    _actor: str = Depends(require_scope("workflows:execute")),
) -> dict[str, Any]:
    job = process_next_job(session, worker_id=worker_id)
    if job is None:
        return {"processed": False, "job": None}
    return {"processed": True, "job": ExecutionJobRead.model_validate(job).model_dump(mode="json")}


@app.post("/api/queue/worker/recover-stale")
def worker_recover_stale_endpoint(
    lease_timeout_seconds: int = 60,
    session: Session = Depends(get_session),
    _actor: str = Depends(require_scope("workflows:execute")),
) -> dict[str, int]:
    recovered = recover_stale_jobs(session, lease_timeout_seconds=lease_timeout_seconds)
    return {"recovered_jobs": recovered}


# --- Credentials Vault Endpoints ---


@app.post("/api/credentials", response_model=CredentialRead, status_code=201)
def create_credential(
    payload: CredentialCreate,
    session: Session = Depends(get_session),
    actor: str = Depends(require_scope("credentials:manage")),
):
    existing = session.query(Credential).filter(Credential.name == payload.name).first()
    if existing is not None:
        raise HTTPException(status_code=409, detail=f"Credential {payload.name!r} already exists")
    vault = CredentialVault()
    ciphertext = vault.encrypt_dict(payload.data)
    cred = Credential(
        id=str(uuid4()),
        name=payload.name,
        kind=payload.kind,
        description=payload.description,
        encrypted_payload=ciphertext,
        field_names=sorted(payload.data.keys()),
        key_fingerprint=vault.fingerprint,
    )
    session.add(cred)
    session.commit()
    session.refresh(cred)
    record_audit(
        session,
        "credential.create",
        "credential",
        cred.id,
        {"name": cred.name, "kind": cred.kind, "fields": cred.field_names},
        actor=actor,
    )
    return cred


@app.get("/api/credentials", response_model=list[CredentialRead])
def list_credentials(
    session: Session = Depends(get_session),
    _actor: str = Depends(require_scope("workflows:read")),
):
    return session.query(Credential).order_by(Credential.created_at.desc()).all()


@app.delete("/api/credentials/{credential_id}")
def delete_credential(
    credential_id: str,
    session: Session = Depends(get_session),
    actor: str = Depends(require_scope("credentials:manage")),
) -> dict[str, Any]:
    cred = session.get(Credential, credential_id)
    if cred is None:
        raise HTTPException(status_code=404, detail="Credential not found")
    session.delete(cred)
    session.commit()
    record_audit(session, "credential.delete", "credential", credential_id, {"name": cred.name}, actor=actor)
    return {"deleted": True, "id": credential_id}


# --- Webhooks & Schedules Endpoints ---


@app.post("/api/webhooks", response_model=WebhookRead, status_code=201)
def create_webhook(
    payload: WebhookCreate,
    session: Session = Depends(get_session),
    actor: str = Depends(require_scope("workflows:write")),
):
    wf = session.get(Workflow, payload.workflow_id)
    if wf is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    existing = session.query(WebhookEndpoint).filter(WebhookEndpoint.path_slug == payload.path_slug).first()
    if existing is not None:
        raise HTTPException(status_code=409, detail=f"Webhook slug {payload.path_slug!r} already registered")
    wh = WebhookEndpoint(
        id=str(uuid4()),
        workflow_id=payload.workflow_id,
        path_slug=payload.path_slug,
        secret_hash=payload.secret if payload.secret else None,
        is_active=True,
        last_delivery_ids=[],
    )
    session.add(wh)
    session.commit()
    session.refresh(wh)
    record_audit(session, "webhook.create", "webhook", wh.id, {"path_slug": wh.path_slug}, actor=actor)
    return WebhookRead(
        id=wh.id,
        workflow_id=wh.workflow_id,
        path_slug=wh.path_slug,
        has_secret=bool(wh.secret_hash),
        is_active=wh.is_active,
        created_at=wh.created_at,
    )


@app.get("/api/webhooks", response_model=list[WebhookRead])
def list_webhooks(session: Session = Depends(get_session)):
    items = session.query(WebhookEndpoint).order_by(WebhookEndpoint.created_at.desc()).all()
    return [
        WebhookRead(
            id=w.id,
            workflow_id=w.workflow_id,
            path_slug=w.path_slug,
            has_secret=bool(w.secret_hash),
            is_active=w.is_active,
            created_at=w.created_at,
        )
        for w in items
    ]


@app.delete("/api/webhooks/{webhook_id}")
def delete_webhook(
    webhook_id: str,
    session: Session = Depends(get_session),
    actor: str = Depends(require_scope("workflows:write")),
) -> dict[str, Any]:
    wh = session.get(WebhookEndpoint, webhook_id)
    if wh is None:
        raise HTTPException(status_code=404, detail="Webhook not found")
    session.delete(wh)
    session.commit()
    record_audit(session, "webhook.delete", "webhook", webhook_id, {}, actor=actor)
    return {"deleted": True, "id": webhook_id}


@app.post("/api/webhooks/ingest/{path_slug}")
async def ingest_webhook(
    path_slug: str,
    request: Request,
    x_flowforge_signature: str | None = Header(default=None),
    x_flowforge_delivery: str | None = Header(default=None),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    wh = session.query(WebhookEndpoint).filter(WebhookEndpoint.path_slug == path_slug).first()
    if wh is None or not wh.is_active:
        raise HTTPException(status_code=404, detail="Active webhook endpoint not found")

    raw_bytes = await request.body()
    if len(raw_bytes) > 256_000:
        raise HTTPException(status_code=413, detail="Webhook payload exceeds 256 KB limit")

    if wh.secret_hash:
        if not x_flowforge_signature or not verify_webhook_signature(raw_bytes, wh.secret_hash, x_flowforge_signature):
            raise HTTPException(status_code=401, detail="Invalid webhook HMAC signature")

    seen_ids = list(wh.last_delivery_ids or [])
    if x_flowforge_delivery:
        if x_flowforge_delivery in seen_ids:
            return {"status": "duplicate_ignored", "delivery_id": x_flowforge_delivery}
        seen_ids = (seen_ids + [x_flowforge_delivery])[-100:]
        wh.last_delivery_ids = seen_ids
        session.add(wh)
        session.commit()

    try:
        body_json = await request.json() if raw_bytes else {}
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Webhook body must be valid JSON") from exc

    if not isinstance(body_json, dict):
        body_json = {"payload": body_json}

    exec_req = ExecuteRequest(
        input={**body_json, "_webhook": {"slug": path_slug, "delivery_id": x_flowforge_delivery}},
        mode="sync",
    )
    execution = execute_saved_workflow(wh.workflow_id, exec_req, session=session, actor=f"webhook:{path_slug}")
    return {"status": "accepted", "execution_id": execution.id, "execution_status": execution.status}


@app.post("/api/schedules", response_model=ScheduleRead, status_code=201)
def create_schedule(
    payload: ScheduleCreate,
    session: Session = Depends(get_session),
    actor: str = Depends(require_scope("workflows:write")),
):
    wf = session.get(Workflow, payload.workflow_id)
    if wf is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    sched = ScheduleTrigger(
        id=str(uuid4()),
        workflow_id=payload.workflow_id,
        cron_expr=payload.cron_expr,
        interval_seconds=payload.interval_seconds,
        is_active=True,
        input_template=payload.input_template,
        last_run_at=None,
        next_run_at=utc_now(),
    )
    session.add(sched)
    session.commit()
    session.refresh(sched)
    record_audit(session, "schedule.create", "schedule", sched.id, {"workflow_id": payload.workflow_id}, actor=actor)
    return sched


@app.get("/api/schedules", response_model=list[ScheduleRead])
def list_schedules(session: Session = Depends(get_session)):
    return session.query(ScheduleTrigger).order_by(ScheduleTrigger.created_at.desc()).all()


@app.delete("/api/schedules/{schedule_id}")
def delete_schedule(
    schedule_id: str,
    session: Session = Depends(get_session),
    actor: str = Depends(require_scope("workflows:write")),
) -> dict[str, Any]:
    sched = session.get(ScheduleTrigger, schedule_id)
    if sched is None:
        raise HTTPException(status_code=404, detail="Schedule not found")
    session.delete(sched)
    session.commit()
    record_audit(session, "schedule.delete", "schedule", schedule_id, {}, actor=actor)
    return {"deleted": True, "id": schedule_id}


@app.post("/api/schedules/tick")
def trigger_schedules_tick(
    session: Session = Depends(get_session),
    _actor: str = Depends(require_scope("workflows:execute")),
) -> dict[str, Any]:
    jobs = tick_schedules(session)
    processed_ids: list[str] = []
    for _ in jobs:
        done = process_next_job(session, worker_id="scheduler-worker")
        if done and done.execution_id:
            processed_ids.append(done.execution_id)
    return {"schedules_triggered": len(jobs), "executions_completed": processed_ids}


# --- API Tokens & Audit Logs ---


@app.post("/api/auth/tokens", response_model=ApiTokenCreatedResponse, status_code=201)
def create_api_token_endpoint(
    payload: ApiTokenCreate,
    session: Session = Depends(get_session),
    actor: str = Depends(require_scope("admin:*")),
):
    raw_token, prefix, t_hash = generate_api_token()
    tok = ApiToken(
        id=str(uuid4()),
        name=payload.name,
        token_prefix=prefix,
        token_hash=t_hash,
        role=payload.role,
        scopes=payload.scopes,
        is_revoked=False,
    )
    session.add(tok)
    session.commit()
    session.refresh(tok)
    record_audit(session, "auth.token_create", "api_token", tok.id, {"name": tok.name, "role": tok.role}, actor=actor)
    return ApiTokenCreatedResponse(
        id=tok.id,
        name=tok.name,
        token=raw_token,
        token_prefix=tok.token_prefix,
        role=tok.role,
        scopes=tok.scopes,
        created_at=tok.created_at,
    )


@app.get("/api/auth/tokens", response_model=list[ApiTokenRead])
def list_api_tokens(session: Session = Depends(get_session)):
    return session.query(ApiToken).order_by(ApiToken.created_at.desc()).all()


@app.post("/api/auth/tokens/{token_id}/revoke", response_model=ApiTokenRead)
def revoke_api_token(
    token_id: str,
    session: Session = Depends(get_session),
    actor: str = Depends(require_scope("admin:*")),
):
    tok = session.get(ApiToken, token_id)
    if tok is None:
        raise HTTPException(status_code=404, detail="API token not found")
    tok.is_revoked = True
    session.add(tok)
    session.commit()
    session.refresh(tok)
    record_audit(session, "auth.token_revoke", "api_token", tok.id, {"name": tok.name}, actor=actor)
    return tok


@app.get("/api/audit-logs", response_model=list[AuditLogRead])
def list_audit_logs(
    limit: int = Query(default=50, ge=1, le=200),
    session: Session = Depends(get_session),
):
    return session.query(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit).all()


# --- Integrations, Skills, Templates & AI Assistant ---


@app.get("/api/integrations")
def list_integrations_endpoint(category: str | None = None) -> list[dict[str, Any]]:
    return list_node_specs(category=category)


@app.get("/api/skills")
def list_skills_endpoint() -> list[dict[str, Any]]:
    return list_skills()


@app.post("/api/skills/validate")
def validate_skill_endpoint(manifest: dict[str, Any]) -> dict[str, Any]:
    try:
        validated = validate_skill_manifest(manifest)
        return {"valid": True, "manifest": validated.model_dump(mode="json")}
    except (SkillValidationError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/skills/{skill_id}/execute")
def execute_skill_endpoint(skill_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        return execute_skill(skill_id, payload)
    except SkillValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/api/templates")
def list_templates_endpoint(category: str | None = None, search: str | None = None) -> list[dict[str, Any]]:
    return list_templates(category=category, search=search)


@app.post("/api/templates/{template_id}/instantiate", response_model=WorkflowRead, status_code=201)
def instantiate_template_endpoint(
    template_id: str,
    session: Session = Depends(get_session),
    actor: str = Depends(require_scope("workflows:write")),
):
    tpl = get_template(template_id)
    if tpl is None:
        raise HTTPException(status_code=404, detail="Template not found")
    create_req = WorkflowCreate(
        name=tpl["name"],
        description=tpl["description"],
        tags=tpl["tags"],
        folder=tpl["category"],
        environment="dev",
        comment=f"Instantiated from template {template_id}",
        definition=WorkflowDefinition.model_validate(tpl["definition"]),
    )
    return create_workflow(create_req, session=session, actor=actor)


@app.post("/api/ai/draft")
def ai_draft_endpoint(payload: AIDraftRequest) -> dict[str, Any]:
    return draft_workflow_from_prompt(payload.prompt, provider=payload.provider)


@app.post("/api/ai/explain")
def ai_explain_endpoint(definition: WorkflowDefinition) -> dict[str, Any]:
    return explain_workflow(definition.model_dump(mode="json"))


@app.get("/api/ai/benchmarks")
def ai_benchmarks_endpoint() -> dict[str, Any]:
    return run_ai_benchmarks()
