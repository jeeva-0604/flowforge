"""Database engine and session management.
Supports SQLAlchemy 2.x (PostgreSQL and SQLite) when SQLAlchemy is installed, and
includes a zero-dependency SQLite3 ORM compatibility layer for restricted test
environments where SQLAlchemy is not pre-installed.
"""
from __future__ import annotations

from collections.abc import Generator
from datetime import datetime, timezone
import json
import sqlite3
import threading
from typing import Any
from .config import database_url

try:
    from sqlalchemy import create_engine as _sa_create_engine
    from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

    HAS_SQLALCHEMY = True
except ImportError:  # pragma: no cover - fallback for restricted environments without SQLAlchemy
    HAS_SQLALCHEMY = False

    class _FieldDescriptor:
        def __init__(self, model_cls: type, name: str):
            self.model_cls = model_cls
            self.name = name

        def __eq__(self, other: Any) -> tuple[str, str, Any]:  # type: ignore[override]
            return (self.name, "=", other)

        def __ne__(self, other: Any) -> tuple[str, str, Any]:  # type: ignore[override]
            return (self.name, "!=", other)

        def desc(self) -> tuple[str, str]:
            return (self.name, "DESC")

        def asc(self) -> tuple[str, str]:
            return (self.name, "ASC")

    class _MetaRegistry:
        def __init__(self) -> None:
            self.models: list[type] = []

        def register(self, cls: type) -> None:
            if cls not in self.models and hasattr(cls, "__tablename__"):
                self.models.append(cls)

        def create_all(self, bind: Any) -> None:
            bind.create_tables(self.models)

    class _DeclarativeMeta(type):
        def __new__(mcls, name: str, bases: tuple[type, ...], namespace: dict[str, Any]):
            cls = super().__new__(mcls, name, bases, namespace)
            if name != "Base" and "__tablename__" in namespace:
                cols = namespace.get("__columns__", {})
                for col_name in cols:
                    setattr(cls, col_name, _FieldDescriptor(cls, col_name))
                Base.metadata.register(cls)
            return cls

    class DeclarativeBase(metaclass=_DeclarativeMeta):
        metadata = _MetaRegistry()

        def __init__(self, **kwargs: Any) -> None:
            defaults = getattr(self.__class__, "__defaults__", {})
            for col_name in getattr(self.__class__, "__columns__", {}):
                if col_name in kwargs:
                    val = kwargs[col_name]
                elif col_name in defaults:
                    default_fn = defaults[col_name]
                    val = default_fn() if callable(default_fn) else default_fn
                else:
                    val = None
                self.__dict__[col_name] = val

        def __getattribute__(self, name: str) -> Any:
            d = object.__getattribute__(self, "__dict__")
            if name in d:
                return d[name]
            return object.__getattribute__(self, name)

        def __setattr__(self, name: str, value: Any) -> None:
            self.__dict__[name] = value

    class SQLiteCompatEngine:
        """Thread-safe SQLite3 engine emulating SQLAlchemy Engine for test/offline environments."""

        def __init__(self, url: str) -> None:
            self.url = url
            self._lock = threading.RLock()
            if url in ("sqlite://", "sqlite:///:memory:") or ":memory:" in url:
                self._path = ":memory:"
                self._shared_conn = sqlite3.connect(":memory:", check_same_thread=False)
                self._shared_conn.row_factory = sqlite3.Row
                self._shared_conn.execute("PRAGMA foreign_keys = ON")
            elif url.startswith("sqlite:///"):
                self._path = url[len("sqlite:///") :]
                self._shared_conn = None
            else:
                # Fallback in-memory when PostgreSQL driver is not installed in offline container
                self._path = ":memory:"
                self._shared_conn = sqlite3.connect(":memory:", check_same_thread=False)
                self._shared_conn.row_factory = sqlite3.Row
                self._shared_conn.execute("PRAGMA foreign_keys = ON")

        def raw_connection(self) -> sqlite3.Connection:
            if self._shared_conn is not None:
                return self._shared_conn
            conn = sqlite3.connect(self._path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            return conn

        def create_tables(self, models: list[type]) -> None:
            with self._lock:
                conn = self.raw_connection()
                for model in models:
                    table = getattr(model, "__tablename__")
                    cols: dict[str, dict[str, Any]] = getattr(model, "__columns__", {})
                    col_defs = []
                    for col_name, spec in cols.items():
                        sql_type = spec.get("sql_type", "TEXT")
                        pk = " PRIMARY KEY" if spec.get("primary_key") else ""
                        not_null = " NOT NULL" if not spec.get("nullable", True) and not pk else ""
                        fk = f" REFERENCES {spec['foreign_key']} ON DELETE CASCADE" if spec.get("foreign_key") else ""
                        col_defs.append(f"{col_name} {sql_type}{pk}{not_null}{fk}")
                    ddl = f"CREATE TABLE IF NOT EXISTS {table} ({', '.join(col_defs)})"
                    conn.execute(ddl)
                conn.commit()

    class _CompatQuery:
        def __init__(self, session: "Session", model_cls: type) -> None:
            self.session = session
            self.model_cls = model_cls
            self._filters: list[tuple[str, str, Any]] = []
            self._order: list[tuple[str, str]] = []
            self._limit: int | None = None

        def filter(self, *conditions: tuple[str, str, Any]) -> "_CompatQuery":
            for cond in conditions:
                if cond is not None:
                    self._filters.append(cond)
            return self

        def filter_by(self, **kwargs: Any) -> "_CompatQuery":
            for k, v in kwargs.items():
                self._filters.append((k, "=", v))
            return self

        def order_by(self, *clauses: Any) -> "_CompatQuery":
            for clause in clauses:
                if isinstance(clause, tuple):
                    self._order.append(clause)
                elif hasattr(clause, "name"):
                    self._order.append((clause.name, "ASC"))
            return self

        def limit(self, count: int) -> "_CompatQuery":
            self._limit = count
            return self

        def all(self) -> list[Any]:
            table = self.model_cls.__tablename__
            sql = f"SELECT * FROM {table}"
            params: list[Any] = []
            if self._filters:
                where_parts = []
                for col, op, val in self._filters:
                    if val is None and op == "=":
                        where_parts.append(f"{col} IS NULL")
                    elif val is None and op == "!=":
                        where_parts.append(f"{col} IS NOT NULL")
                    else:
                        where_parts.append(f"{col} {op} ?")
                        params.append(self.session._serialize_val(self.model_cls, col, val))
                sql += " WHERE " + " AND ".join(where_parts)
            if self._order:
                order_parts = [f"{col} {direction}" for col, direction in self._order]
                sql += " ORDER BY " + ", ".join(order_parts)
            if self._limit is not None:
                sql += f" LIMIT {int(self._limit)}"
            cur = self.session._conn.execute(sql, params)
            rows = cur.fetchall()
            return [self.session._row_to_obj(self.model_cls, row) for row in rows]

        def first(self) -> Any | None:
            self._limit = 1
            items = self.all()
            return items[0] if items else None

        def count(self) -> int:
            return len(self.all())

    class Session:  # type: ignore[no-redef]
        """SQLAlchemy-compatible Session backed by SQLite3."""

        def __init__(self, bind: SQLiteCompatEngine) -> None:
            self.bind = bind
            self._conn = bind.raw_connection()
            self._pending: list[Any] = []
            self._deleted: list[Any] = []

        def __enter__(self) -> "Session":
            return self

        def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
            if self.bind._shared_conn is None:
                self._conn.close()

        def _serialize_val(self, model_cls: type, col: str, val: Any) -> Any:
            if val is None:
                return None
            spec = getattr(model_cls, "__columns__", {}).get(col, {})
            kind = spec.get("py_type")
            if kind == "json":
                return json.dumps(val)
            if kind == "datetime":
                if isinstance(val, datetime):
                    if val.tzinfo is None:
                        val = val.replace(tzinfo=timezone.utc)
                    return val.isoformat()
                return str(val)
            if kind == "bool":
                return 1 if val else 0
            return val

        def _deserialize_val(self, model_cls: type, col: str, val: Any) -> Any:
            if val is None:
                return None
            spec = getattr(model_cls, "__columns__", {}).get(col, {})
            kind = spec.get("py_type")
            if kind == "json":
                return json.loads(val) if isinstance(val, str) else val
            if kind == "datetime":
                if isinstance(val, str):
                    dt = datetime.fromisoformat(val)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    return dt
                return val
            if kind == "bool":
                return bool(val)
            return val

        def _row_to_obj(self, model_cls: type, row: sqlite3.Row) -> Any:
            data = {}
            for col in getattr(model_cls, "__columns__", {}):
                if col in row.keys():
                    data[col] = self._deserialize_val(model_cls, col, row[col])
            return model_cls(**data)

        def add(self, obj: Any) -> None:
            if obj not in self._pending:
                self._pending.append(obj)

        def delete(self, obj: Any) -> None:
            if obj not in self._deleted:
                self._deleted.append(obj)

        def get(self, model_cls: type, pk_val: Any) -> Any | None:
            table = model_cls.__tablename__
            pk_col = next(
                col for col, spec in model_cls.__columns__.items() if spec.get("primary_key")
            )
            cur = self._conn.execute(f"SELECT * FROM {table} WHERE {pk_col} = ?", (pk_val,))
            row = cur.fetchone()
            if row is None:
                return None
            return self._row_to_obj(model_cls, row)

        def query(self, model_cls: type) -> _CompatQuery:
            return _CompatQuery(self, model_cls)

        def commit(self) -> None:
            with self.bind._lock:
                for obj in list(self._deleted):
                    model_cls = obj.__class__
                    table = model_cls.__tablename__
                    pk_col = next(
                        col for col, spec in model_cls.__columns__.items() if spec.get("primary_key")
                    )
                    self._conn.execute(
                        f"DELETE FROM {table} WHERE {pk_col} = ?",
                        (getattr(obj, pk_col),),
                    )
                self._deleted.clear()

                for obj in list(self._pending):
                    model_cls = obj.__class__
                    table = model_cls.__tablename__
                    cols = list(model_cls.__columns__.keys())
                    pk_col = next(
                        col for col, spec in model_cls.__columns__.items() if spec.get("primary_key")
                    )
                    onupdates = getattr(model_cls, "__onupdates__", {})
                    cur = self._conn.execute(
                        f"SELECT 1 FROM {table} WHERE {pk_col} = ?",
                        (getattr(obj, pk_col),),
                    )
                    exists = cur.fetchone() is not None
                    if exists:
                        for col_name, fn in onupdates.items():
                            setattr(obj, col_name, fn() if callable(fn) else fn)
                        set_clause = ", ".join(f"{c} = ?" for c in cols if c != pk_col)
                        vals = [
                            self._serialize_val(model_cls, c, getattr(obj, c))
                            for c in cols
                            if c != pk_col
                        ]
                        vals.append(self._serialize_val(model_cls, pk_col, getattr(obj, pk_col)))
                        self._conn.execute(f"UPDATE {table} SET {set_clause} WHERE {pk_col} = ?", vals)
                    else:
                        placeholders = ", ".join("?" for _ in cols)
                        vals = [self._serialize_val(model_cls, c, getattr(obj, c)) for c in cols]
                        self._conn.execute(
                            f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({placeholders})",
                            vals,
                        )
                self._pending.clear()
                self._conn.commit()

        def refresh(self, obj: Any) -> None:
            model_cls = obj.__class__
            pk_col = next(
                col for col, spec in model_cls.__columns__.items() if spec.get("primary_key")
            )
            fresh = self.get(model_cls, getattr(obj, pk_col))
            if fresh is not None:
                for col in model_cls.__columns__:
                    setattr(obj, col, getattr(fresh, col))

        def execute_raw(self, sql: str, params: tuple[Any, ...] | dict[str, Any] = ()) -> list[dict[str, Any]]:
            cur = self._conn.execute(sql, params)
            if cur.description is None:
                self._conn.commit()
                return []
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]

    def sessionmaker(bind: Any, **kwargs: Any):  # type: ignore[misc]
        def _factory() -> Session:
            return Session(bind)

        return _factory


class Base(DeclarativeBase):
    pass


def make_engine(url: str | None = None, **extra_kwargs: Any):
    target = url or database_url()
    if HAS_SQLALCHEMY:
        kwargs: dict[str, Any] = {"pool_pre_ping": True}
        if target.startswith("sqlite"):
            kwargs["connect_args"] = {"check_same_thread": False}
        kwargs.update(extra_kwargs)
        return _sa_create_engine(target, **kwargs)
    return SQLiteCompatEngine(target)


engine = make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_session() -> Generator[Session, None, None]:
    with SessionLocal() as session:
        yield session
