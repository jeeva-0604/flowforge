"""Add worker_nodes table and max_concurrent_runs on workflows.

Revision ID: 0004_milestone5_streaming_and_workers
Revises: 0003_milestone4_enterprise_ops
Create Date: 2026-10-24
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0004_milestone5_streaming_and_workers"
down_revision = "0003_milestone4_enterprise_ops"
branch_labels = None
depends_on = None

JSON_TYPE = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    with op.batch_alter_table("workflows") as batch_op:
        batch_op.add_column(sa.Column("max_concurrent_runs", sa.Integer(), nullable=False, server_default="5"))

    op.create_table(
        "worker_nodes",
        sa.Column("id", sa.String(length=80), primary_key=True),
        sa.Column("hostname", sa.String(length=120), nullable=False),
        sa.Column("queues", JSON_TYPE, nullable=False),
        sa.Column("concurrency", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("processed_count", sa.Integer(), nullable=False),
        sa.Column("failed_count", sa.Integer(), nullable=False),
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("worker_nodes")
