"""Add projects, workspace_variables, and workflow_test_cases tables.

Revision ID: 0003_milestone4_enterprise_ops
Revises: 0002_milestone3_platform
Create Date: 2026-10-24
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0003_milestone4_enterprise_ops"
down_revision = "0002_milestone3_platform"
branch_labels = None
depends_on = None

JSON_TYPE = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("name", sa.String(length=120), unique=True, nullable=False),
        sa.Column("slug", sa.String(length=80), unique=True, nullable=False, index=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "workspace_variables",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("key", sa.String(length=80), nullable=False, index=True),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("environment", sa.String(length=20), nullable=False),
        sa.Column("is_secret", sa.Boolean(), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "workflow_test_cases",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("workflow_id", sa.String(length=36), sa.ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=False),
        sa.Column("input_data", JSON_TYPE, nullable=False),
        sa.Column("pinned_node_outputs", JSON_TYPE, nullable=False),
        sa.Column("assertions", JSON_TYPE, nullable=False),
        sa.Column("last_status", sa.String(length=30), nullable=True),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("workflow_test_cases")
    op.drop_table("workspace_variables")
    op.drop_table("projects")
