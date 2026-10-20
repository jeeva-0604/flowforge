"""Database schema migration runner for FlowForge Community.
Works with both PostgreSQL and SQLite, and safely upgrades existing Milestone 1/2
installations by adding missing columns and tables idempotently while recording
applied revisions in `schema_migrations`.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from .db import Base, HAS_SQLALCHEMY, engine as default_engine
from . import models  # noqa: F401

MIGRATIONS: list[tuple[str, str]] = [
    ("0001_initial_foundation", "Create initial workflows and executions tables"),
    (
        "0002_milestone3_platform",
        "Add workflow_versions, execution_jobs, credentials, webhook_endpoints, schedule_triggers, api_tokens, audit_logs, installed_skills, and new columns on workflows/executions",
    ),
]


def _ensure_columns_sqlite(raw_conn: Any) -> None:
    cur = raw_conn.execute("PRAGMA table_info(workflows)")
    existing_wf_cols = {row[1] for row in cur.fetchall()}
    wf_additions = [
        ("description", "TEXT NOT NULL DEFAULT ''"),
        ("tags", "TEXT NOT NULL DEFAULT '[]'"),
        ("folder", "TEXT NOT NULL DEFAULT 'General'"),
        ("is_active", "INTEGER NOT NULL DEFAULT 1"),
        ("environment", "TEXT NOT NULL DEFAULT 'dev'"),
        ("version", "INTEGER NOT NULL DEFAULT 1"),
    ]
    for col, ddl in wf_additions:
        if existing_wf_cols and col not in existing_wf_cols:
            raw_conn.execute(f"ALTER TABLE workflows ADD COLUMN {col} {ddl}")

    cur = raw_conn.execute("PRAGMA table_info(executions)")
    existing_ex_cols = {row[1] for row in cur.fetchall()}
    ex_additions = [
        ("workflow_version", "INTEGER NOT NULL DEFAULT 1"),
        ("trigger_type", "TEXT NOT NULL DEFAULT 'manual'"),
        ("node_runs", "TEXT NOT NULL DEFAULT '[]'"),
        ("checkpoint_state", "TEXT"),
    ]
    for col, ddl in ex_additions:
        if existing_ex_cols and col not in existing_ex_cols:
            raw_conn.execute(f"ALTER TABLE executions ADD COLUMN {col} {ddl}")


def run_migrations(target_engine: Any = None) -> list[str]:
    bind = target_engine or default_engine
    Base.metadata.create_all(bind=bind)
    applied: list[str] = []
    now_iso = datetime.now(timezone.utc).isoformat()

    if HAS_SQLALCHEMY:
        from sqlalchemy import text

        with bind.begin() as conn:
            conn.execute(
                text(
                    "CREATE TABLE IF NOT EXISTS schema_migrations ("
                    "revision VARCHAR(64) PRIMARY KEY, "
                    "description TEXT NOT NULL, "
                    "applied_at VARCHAR(64) NOT NULL)"
                )
            )
            dialect = bind.dialect.name
            if dialect == "sqlite":
                _ensure_columns_sqlite(conn.connection.driver_connection)
            elif dialect == "postgresql":
                pg_alters = [
                    "ALTER TABLE workflows ADD COLUMN IF NOT EXISTS description TEXT NOT NULL DEFAULT ''",
                    "ALTER TABLE workflows ADD COLUMN IF NOT EXISTS tags JSONB NOT NULL DEFAULT '[]'::jsonb",
                    "ALTER TABLE workflows ADD COLUMN IF NOT EXISTS folder VARCHAR(80) NOT NULL DEFAULT 'General'",
                    "ALTER TABLE workflows ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE",
                    "ALTER TABLE workflows ADD COLUMN IF NOT EXISTS environment VARCHAR(20) NOT NULL DEFAULT 'dev'",
                    "ALTER TABLE workflows ADD COLUMN IF NOT EXISTS version INTEGER NOT NULL DEFAULT 1",
                    "ALTER TABLE executions ADD COLUMN IF NOT EXISTS workflow_version INTEGER NOT NULL DEFAULT 1",
                    "ALTER TABLE executions ADD COLUMN IF NOT EXISTS trigger_type VARCHAR(30) NOT NULL DEFAULT 'manual'",
                    "ALTER TABLE executions ADD COLUMN IF NOT EXISTS node_runs JSONB NOT NULL DEFAULT '[]'::jsonb",
                    "ALTER TABLE executions ADD COLUMN IF NOT EXISTS checkpoint_state JSONB",
                ]
                for stmt in pg_alters:
                    conn.execute(text(stmt))

            rows = conn.execute(text("SELECT revision FROM schema_migrations")).fetchall()
            already = {r[0] for r in rows}
            for rev, desc in MIGRATIONS:
                if rev not in already:
                    conn.execute(
                        text(
                            "INSERT INTO schema_migrations (revision, description, applied_at) "
                            "VALUES (:rev, :desc, :at)"
                        ),
                        {"rev": rev, "desc": desc, "at": now_iso},
                    )
                applied.append(rev)
    else:
        raw_conn = bind.raw_connection()
        raw_conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            "revision TEXT PRIMARY KEY, "
            "description TEXT NOT NULL, "
            "applied_at TEXT NOT NULL)"
        )
        _ensure_columns_sqlite(raw_conn)
        rows = raw_conn.execute("SELECT revision FROM schema_migrations").fetchall()
        already = {r[0] for r in rows}
        for rev, desc in MIGRATIONS:
            if rev not in already:
                raw_conn.execute(
                    "INSERT INTO schema_migrations (revision, description, applied_at) VALUES (?, ?, ?)",
                    (rev, desc, now_iso),
                )
            applied.append(rev)
        raw_conn.commit()

    return applied
