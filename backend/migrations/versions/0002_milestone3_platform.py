"""Milestone 3 platform tables and workflow/execution column additions.

Revision ID: 0002_milestone3_platform
Revises: 0001_initial_foundation
Create Date: 2026-10-20
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002_milestone3_platform"
down_revision = "0001_initial_foundation"
branch_labels = None
depends_on = None

JSON_TYPE = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    with op.batch_alter_table("workflows") as batch_op:
        batch_op.add_column(sa.Column("description", sa.Text(), nullable=False, server_default=""))
        batch_op.add_column(sa.Column("tags", JSON_TYPE, nullable=False, server_default="[]"))
        batch_op.add_column(sa.Column("folder", sa.String(length=80), nullable=False, server_default="General"))
        batch_op.add_column(sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()))
        batch_op.add_column(sa.Column("environment", sa.String(length=20), nullable=False, server_default="dev"))
        batch_op.add_column(sa.Column("version", sa.Integer(), nullable=False, server_default="1"))

    with op.batch_alter_table("executions") as batch_op:
        batch_op.add_column(sa.Column("workflow_version", sa.Integer(), nullable=False, server_default="1"))
        batch_op.add_column(sa.Column("trigger_type", sa.String(length=30), nullable=False, server_default="manual"))
        batch_op.add_column(sa.Column("node_runs", JSON_TYPE, nullable=False, server_default="[]"))
        batch_op.add_column(sa.Column("checkpoint_state", JSON_TYPE, nullable=True))

    op.create_table(
        "workflow_versions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("workflow_id", sa.String(length=36), sa.ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("environment", sa.String(length=20), nullable=False),
        sa.Column("comment", sa.String(length=255), nullable=False),
        sa.Column("definition", JSON_TYPE, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "execution_jobs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("workflow_id", sa.String(length=36), sa.ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("execution_id", sa.String(length=36), nullable=True),
        sa.Column("trigger_type", sa.String(length=30), nullable=False),
        sa.Column("idempotency_key", sa.String(length=120), nullable=True, index=True),
        sa.Column("status", sa.String(length=30), nullable=False, index=True),
        sa.Column("input_data", JSON_TYPE, nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("worker_id", sa.String(length=80), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "credentials",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("name", sa.String(length=120), unique=True, nullable=False),
        sa.Column("kind", sa.String(length=60), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=False),
        sa.Column("encrypted_payload", sa.Text(), nullable=False),
        sa.Column("field_names", JSON_TYPE, nullable=False),
        sa.Column("key_fingerprint", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "webhook_endpoints",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("workflow_id", sa.String(length=36), sa.ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("path_slug", sa.String(length=100), unique=True, nullable=False, index=True),
        sa.Column("secret_hash", sa.String(length=128), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("last_delivery_ids", JSON_TYPE, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "schedule_triggers",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("workflow_id", sa.String(length=36), sa.ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("cron_expr", sa.String(length=80), nullable=False),
        sa.Column("interval_seconds", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("input_template", JSON_TYPE, nullable=False),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "api_tokens",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("token_prefix", sa.String(length=16), nullable=False),
        sa.Column("token_hash", sa.String(length=128), unique=True, nullable=False, index=True),
        sa.Column("role", sa.String(length=30), nullable=False),
        sa.Column("scopes", JSON_TYPE, nullable=False),
        sa.Column("is_revoked", sa.Boolean(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("actor", sa.String(length=120), nullable=False),
        sa.Column("action", sa.String(length=80), nullable=False, index=True),
        sa.Column("resource_type", sa.String(length=60), nullable=False),
        sa.Column("resource_id", sa.String(length=80), nullable=False),
        sa.Column("details", JSON_TYPE, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "installed_skills",
        sa.Column("id", sa.String(length=80), primary_key=True),
        sa.Column("version", sa.String(length=30), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("manifest", JSON_TYPE, nullable=False),
        sa.Column("integrity_hash", sa.String(length=128), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False),
        sa.Column("installed_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("installed_skills")
    op.drop_table("audit_logs")
    op.drop_table("api_tokens")
    op.drop_table("schedule_triggers")
    op.drop_table("webhook_endpoints")
    op.drop_table("credentials")
    op.drop_table("execution_jobs")
    op.drop_table("workflow_versions")
