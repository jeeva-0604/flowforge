"""Database models for FlowForge Community.
Supports SQLAlchemy 2.x (with PostgreSQL JSONB variant) when installed, as well as
the built-in SQLite compatibility layer for restricted test environments.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4
from .db import Base, HAS_SQLALCHEMY


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def new_uuid() -> str:
    return str(uuid4())


if HAS_SQLALCHEMY:
    from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text
    from sqlalchemy.dialects.postgresql import JSONB
    from sqlalchemy.orm import Mapped, mapped_column

    # JSONB on PostgreSQL; SQLAlchemy's JSON type also supports SQLite test databases.
    JSON_TYPE = JSON().with_variant(JSONB, "postgresql")

    class Workflow(Base):
        __tablename__ = "workflows"

        id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
        name: Mapped[str] = mapped_column(String(120), nullable=False)
        description: Mapped[str] = mapped_column(Text, default="", nullable=False)
        tags: Mapped[list[str]] = mapped_column(JSON_TYPE, default=list, nullable=False)
        folder: Mapped[str] = mapped_column(String(80), default="General", nullable=False)
        is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
        environment: Mapped[str] = mapped_column(String(20), default="dev", nullable=False)
        version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
        definition: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, nullable=False)
        created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
        updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    class WorkflowVersion(Base):
        __tablename__ = "workflow_versions"

        id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
        workflow_id: Mapped[str] = mapped_column(ForeignKey("workflows.id", ondelete="CASCADE"), index=True, nullable=False)
        version: Mapped[int] = mapped_column(Integer, nullable=False)
        name: Mapped[str] = mapped_column(String(120), nullable=False)
        environment: Mapped[str] = mapped_column(String(20), default="dev", nullable=False)
        comment: Mapped[str] = mapped_column(String(255), default="Saved revision", nullable=False)
        definition: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, nullable=False)
        created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    class Execution(Base):
        __tablename__ = "executions"

        id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
        workflow_id: Mapped[str] = mapped_column(ForeignKey("workflows.id", ondelete="CASCADE"), index=True, nullable=False)
        workflow_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
        trigger_type: Mapped[str] = mapped_column(String(30), default="manual", nullable=False)
        status: Mapped[str] = mapped_column(String(30), nullable=False)
        input_data: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, nullable=False)
        result_data: Mapped[dict[str, Any] | None] = mapped_column(JSON_TYPE, nullable=True)
        node_runs: Mapped[list[dict[str, Any]]] = mapped_column(JSON_TYPE, default=list, nullable=False)
        checkpoint_state: Mapped[dict[str, Any] | None] = mapped_column(JSON_TYPE, nullable=True)
        error: Mapped[str | None] = mapped_column(Text, nullable=True)
        started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
        finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    class ExecutionJob(Base):
        __tablename__ = "execution_jobs"

        id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
        workflow_id: Mapped[str] = mapped_column(ForeignKey("workflows.id", ondelete="CASCADE"), index=True, nullable=False)
        execution_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
        trigger_type: Mapped[str] = mapped_column(String(30), default="queued", nullable=False)
        idempotency_key: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
        status: Mapped[str] = mapped_column(String(30), default="queued", nullable=False, index=True)
        input_data: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, default=dict, nullable=False)
        attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
        max_attempts: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
        worker_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
        heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
        available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
        last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
        created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
        updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    class Credential(Base):
        __tablename__ = "credentials"

        id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
        name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
        kind: Mapped[str] = mapped_column(String(60), nullable=False)
        description: Mapped[str] = mapped_column(String(255), default="", nullable=False)
        encrypted_payload: Mapped[str] = mapped_column(Text, nullable=False)
        field_names: Mapped[list[str]] = mapped_column(JSON_TYPE, default=list, nullable=False)
        key_fingerprint: Mapped[str] = mapped_column(String(32), default="v1", nullable=False)
        created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
        updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    class WebhookEndpoint(Base):
        __tablename__ = "webhook_endpoints"

        id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
        workflow_id: Mapped[str] = mapped_column(ForeignKey("workflows.id", ondelete="CASCADE"), index=True, nullable=False)
        path_slug: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
        secret_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
        is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
        last_delivery_ids: Mapped[list[str]] = mapped_column(JSON_TYPE, default=list, nullable=False)
        created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    class ScheduleTrigger(Base):
        __tablename__ = "schedule_triggers"

        id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
        workflow_id: Mapped[str] = mapped_column(ForeignKey("workflows.id", ondelete="CASCADE"), index=True, nullable=False)
        cron_expr: Mapped[str] = mapped_column(String(80), nullable=False)
        interval_seconds: Mapped[int] = mapped_column(Integer, default=300, nullable=False)
        is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
        input_template: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, default=dict, nullable=False)
        last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
        next_run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
        created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    class ApiToken(Base):
        __tablename__ = "api_tokens"

        id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
        name: Mapped[str] = mapped_column(String(120), nullable=False)
        token_prefix: Mapped[str] = mapped_column(String(16), nullable=False)
        token_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
        role: Mapped[str] = mapped_column(String(30), default="editor", nullable=False)
        scopes: Mapped[list[str]] = mapped_column(JSON_TYPE, default=list, nullable=False)
        is_revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
        expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
        created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    class AuditLog(Base):
        __tablename__ = "audit_logs"

        id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
        actor: Mapped[str] = mapped_column(String(120), default="local-operator", nullable=False)
        action: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
        resource_type: Mapped[str] = mapped_column(String(60), nullable=False)
        resource_id: Mapped[str] = mapped_column(String(80), nullable=False)
        details: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, default=dict, nullable=False)
        created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    class InstalledSkill(Base):
        __tablename__ = "installed_skills"

        id: Mapped[str] = mapped_column(String(80), primary_key=True)
        version: Mapped[str] = mapped_column(String(30), nullable=False)
        name: Mapped[str] = mapped_column(String(120), nullable=False)
        manifest: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, nullable=False)
        integrity_hash: Mapped[str] = mapped_column(String(128), nullable=False)
        is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
        installed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

else:
    # SQLite compatibility definitions with identical column names, defaults, and foreign keys
    class Workflow(Base):  # type: ignore[no-redef]
        __tablename__ = "workflows"
        __columns__ = {
            "id": {"sql_type": "TEXT", "primary_key": True, "py_type": "str"},
            "name": {"sql_type": "TEXT", "nullable": False, "py_type": "str"},
            "description": {"sql_type": "TEXT", "nullable": False, "py_type": "str"},
            "tags": {"sql_type": "TEXT", "nullable": False, "py_type": "json"},
            "folder": {"sql_type": "TEXT", "nullable": False, "py_type": "str"},
            "is_active": {"sql_type": "INTEGER", "nullable": False, "py_type": "bool"},
            "environment": {"sql_type": "TEXT", "nullable": False, "py_type": "str"},
            "version": {"sql_type": "INTEGER", "nullable": False, "py_type": "int"},
            "definition": {"sql_type": "TEXT", "nullable": False, "py_type": "json"},
            "created_at": {"sql_type": "TEXT", "nullable": False, "py_type": "datetime"},
            "updated_at": {"sql_type": "TEXT", "nullable": False, "py_type": "datetime"},
        }
        __defaults__ = {
            "id": new_uuid,
            "description": "",
            "tags": list,
            "folder": "General",
            "is_active": True,
            "environment": "dev",
            "version": 1,
            "created_at": utc_now,
            "updated_at": utc_now,
        }
        __onupdates__ = {"updated_at": utc_now}

    class WorkflowVersion(Base):  # type: ignore[no-redef]
        __tablename__ = "workflow_versions"
        __columns__ = {
            "id": {"sql_type": "TEXT", "primary_key": True, "py_type": "str"},
            "workflow_id": {"sql_type": "TEXT", "nullable": False, "foreign_key": "workflows(id)", "py_type": "str"},
            "version": {"sql_type": "INTEGER", "nullable": False, "py_type": "int"},
            "name": {"sql_type": "TEXT", "nullable": False, "py_type": "str"},
            "environment": {"sql_type": "TEXT", "nullable": False, "py_type": "str"},
            "comment": {"sql_type": "TEXT", "nullable": False, "py_type": "str"},
            "definition": {"sql_type": "TEXT", "nullable": False, "py_type": "json"},
            "created_at": {"sql_type": "TEXT", "nullable": False, "py_type": "datetime"},
        }
        __defaults__ = {
            "id": new_uuid,
            "environment": "dev",
            "comment": "Saved revision",
            "created_at": utc_now,
        }

    class Execution(Base):  # type: ignore[no-redef]
        __tablename__ = "executions"
        __columns__ = {
            "id": {"sql_type": "TEXT", "primary_key": True, "py_type": "str"},
            "workflow_id": {"sql_type": "TEXT", "nullable": False, "foreign_key": "workflows(id)", "py_type": "str"},
            "workflow_version": {"sql_type": "INTEGER", "nullable": False, "py_type": "int"},
            "trigger_type": {"sql_type": "TEXT", "nullable": False, "py_type": "str"},
            "status": {"sql_type": "TEXT", "nullable": False, "py_type": "str"},
            "input_data": {"sql_type": "TEXT", "nullable": False, "py_type": "json"},
            "result_data": {"sql_type": "TEXT", "nullable": True, "py_type": "json"},
            "node_runs": {"sql_type": "TEXT", "nullable": False, "py_type": "json"},
            "checkpoint_state": {"sql_type": "TEXT", "nullable": True, "py_type": "json"},
            "error": {"sql_type": "TEXT", "nullable": True, "py_type": "str"},
            "started_at": {"sql_type": "TEXT", "nullable": False, "py_type": "datetime"},
            "finished_at": {"sql_type": "TEXT", "nullable": True, "py_type": "datetime"},
        }
        __defaults__ = {
            "id": new_uuid,
            "workflow_version": 1,
            "trigger_type": "manual",
            "node_runs": list,
            "checkpoint_state": None,
            "started_at": utc_now,
        }

    class ExecutionJob(Base):  # type: ignore[no-redef]
        __tablename__ = "execution_jobs"
        __columns__ = {
            "id": {"sql_type": "TEXT", "primary_key": True, "py_type": "str"},
            "workflow_id": {"sql_type": "TEXT", "nullable": False, "foreign_key": "workflows(id)", "py_type": "str"},
            "execution_id": {"sql_type": "TEXT", "nullable": True, "py_type": "str"},
            "trigger_type": {"sql_type": "TEXT", "nullable": False, "py_type": "str"},
            "idempotency_key": {"sql_type": "TEXT", "nullable": True, "py_type": "str"},
            "status": {"sql_type": "TEXT", "nullable": False, "py_type": "str"},
            "input_data": {"sql_type": "TEXT", "nullable": False, "py_type": "json"},
            "attempts": {"sql_type": "INTEGER", "nullable": False, "py_type": "int"},
            "max_attempts": {"sql_type": "INTEGER", "nullable": False, "py_type": "int"},
            "worker_id": {"sql_type": "TEXT", "nullable": True, "py_type": "str"},
            "heartbeat_at": {"sql_type": "TEXT", "nullable": True, "py_type": "datetime"},
            "available_at": {"sql_type": "TEXT", "nullable": False, "py_type": "datetime"},
            "last_error": {"sql_type": "TEXT", "nullable": True, "py_type": "str"},
            "created_at": {"sql_type": "TEXT", "nullable": False, "py_type": "datetime"},
            "updated_at": {"sql_type": "TEXT", "nullable": False, "py_type": "datetime"},
        }
        __defaults__ = {
            "id": new_uuid,
            "trigger_type": "queued",
            "status": "queued",
            "input_data": dict,
            "attempts": 0,
            "max_attempts": 3,
            "available_at": utc_now,
            "created_at": utc_now,
            "updated_at": utc_now,
        }
        __onupdates__ = {"updated_at": utc_now}

    class Credential(Base):  # type: ignore[no-redef]
        __tablename__ = "credentials"
        __columns__ = {
            "id": {"sql_type": "TEXT", "primary_key": True, "py_type": "str"},
            "name": {"sql_type": "TEXT", "nullable": False, "py_type": "str"},
            "kind": {"sql_type": "TEXT", "nullable": False, "py_type": "str"},
            "description": {"sql_type": "TEXT", "nullable": False, "py_type": "str"},
            "encrypted_payload": {"sql_type": "TEXT", "nullable": False, "py_type": "str"},
            "field_names": {"sql_type": "TEXT", "nullable": False, "py_type": "json"},
            "key_fingerprint": {"sql_type": "TEXT", "nullable": False, "py_type": "str"},
            "created_at": {"sql_type": "TEXT", "nullable": False, "py_type": "datetime"},
            "updated_at": {"sql_type": "TEXT", "nullable": False, "py_type": "datetime"},
        }
        __defaults__ = {
            "id": new_uuid,
            "description": "",
            "field_names": list,
            "key_fingerprint": "v1",
            "created_at": utc_now,
            "updated_at": utc_now,
        }
        __onupdates__ = {"updated_at": utc_now}

    class WebhookEndpoint(Base):  # type: ignore[no-redef]
        __tablename__ = "webhook_endpoints"
        __columns__ = {
            "id": {"sql_type": "TEXT", "primary_key": True, "py_type": "str"},
            "workflow_id": {"sql_type": "TEXT", "nullable": False, "foreign_key": "workflows(id)", "py_type": "str"},
            "path_slug": {"sql_type": "TEXT", "nullable": False, "py_type": "str"},
            "secret_hash": {"sql_type": "TEXT", "nullable": True, "py_type": "str"},
            "is_active": {"sql_type": "INTEGER", "nullable": False, "py_type": "bool"},
            "last_delivery_ids": {"sql_type": "TEXT", "nullable": False, "py_type": "json"},
            "created_at": {"sql_type": "TEXT", "nullable": False, "py_type": "datetime"},
        }
        __defaults__ = {
            "id": new_uuid,
            "is_active": True,
            "last_delivery_ids": list,
            "created_at": utc_now,
        }

    class ScheduleTrigger(Base):  # type: ignore[no-redef]
        __tablename__ = "schedule_triggers"
        __columns__ = {
            "id": {"sql_type": "TEXT", "primary_key": True, "py_type": "str"},
            "workflow_id": {"sql_type": "TEXT", "nullable": False, "foreign_key": "workflows(id)", "py_type": "str"},
            "cron_expr": {"sql_type": "TEXT", "nullable": False, "py_type": "str"},
            "interval_seconds": {"sql_type": "INTEGER", "nullable": False, "py_type": "int"},
            "is_active": {"sql_type": "INTEGER", "nullable": False, "py_type": "bool"},
            "input_template": {"sql_type": "TEXT", "nullable": False, "py_type": "json"},
            "last_run_at": {"sql_type": "TEXT", "nullable": True, "py_type": "datetime"},
            "next_run_at": {"sql_type": "TEXT", "nullable": False, "py_type": "datetime"},
            "created_at": {"sql_type": "TEXT", "nullable": False, "py_type": "datetime"},
        }
        __defaults__ = {
            "id": new_uuid,
            "interval_seconds": 300,
            "is_active": True,
            "input_template": dict,
            "next_run_at": utc_now,
            "created_at": utc_now,
        }

    class ApiToken(Base):  # type: ignore[no-redef]
        __tablename__ = "api_tokens"
        __columns__ = {
            "id": {"sql_type": "TEXT", "primary_key": True, "py_type": "str"},
            "name": {"sql_type": "TEXT", "nullable": False, "py_type": "str"},
            "token_prefix": {"sql_type": "TEXT", "nullable": False, "py_type": "str"},
            "token_hash": {"sql_type": "TEXT", "nullable": False, "py_type": "str"},
            "role": {"sql_type": "TEXT", "nullable": False, "py_type": "str"},
            "scopes": {"sql_type": "TEXT", "nullable": False, "py_type": "json"},
            "is_revoked": {"sql_type": "INTEGER", "nullable": False, "py_type": "bool"},
            "expires_at": {"sql_type": "TEXT", "nullable": True, "py_type": "datetime"},
            "created_at": {"sql_type": "TEXT", "nullable": False, "py_type": "datetime"},
        }
        __defaults__ = {
            "id": new_uuid,
            "role": "editor",
            "scopes": list,
            "is_revoked": False,
            "created_at": utc_now,
        }

    class AuditLog(Base):  # type: ignore[no-redef]
        __tablename__ = "audit_logs"
        __columns__ = {
            "id": {"sql_type": "TEXT", "primary_key": True, "py_type": "str"},
            "actor": {"sql_type": "TEXT", "nullable": False, "py_type": "str"},
            "action": {"sql_type": "TEXT", "nullable": False, "py_type": "str"},
            "resource_type": {"sql_type": "TEXT", "nullable": False, "py_type": "str"},
            "resource_id": {"sql_type": "TEXT", "nullable": False, "py_type": "str"},
            "details": {"sql_type": "TEXT", "nullable": False, "py_type": "json"},
            "created_at": {"sql_type": "TEXT", "nullable": False, "py_type": "datetime"},
        }
        __defaults__ = {
            "id": new_uuid,
            "actor": "local-operator",
            "details": dict,
            "created_at": utc_now,
        }

    class InstalledSkill(Base):  # type: ignore[no-redef]
        __tablename__ = "installed_skills"
        __columns__ = {
            "id": {"sql_type": "TEXT", "primary_key": True, "py_type": "str"},
            "version": {"sql_type": "TEXT", "nullable": False, "py_type": "str"},
            "name": {"sql_type": "TEXT", "nullable": False, "py_type": "str"},
            "manifest": {"sql_type": "TEXT", "nullable": False, "py_type": "json"},
            "integrity_hash": {"sql_type": "TEXT", "nullable": False, "py_type": "str"},
            "is_enabled": {"sql_type": "INTEGER", "nullable": False, "py_type": "bool"},
            "installed_at": {"sql_type": "TEXT", "nullable": False, "py_type": "datetime"},
        }
        __defaults__ = {
            "is_enabled": True,
            "installed_at": utc_now,
        }
