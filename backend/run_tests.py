"""Cross-environment test runner for FlowForge Community.
If `pytest` is installed (standard local Windows/Linux venv), delegates to `pytest`.
If running in an offline sandbox without `pytest` or `sqlalchemy`, registers lightweight
compatibility shims and executes every `test_*` function across `backend/tests/test_*.py`.
"""
from __future__ import annotations

from contextlib import contextmanager
import importlib.util
from pathlib import Path
import re
import sys
import time
import traceback
import types

BACKEND_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def _install_offline_shims_if_needed() -> None:
    try:
        import pytest  # noqa: F401
    except ImportError:
        pytest_mod = types.ModuleType("pytest")

        @contextmanager
        def _raises(expected_exc: type[BaseException] | tuple[type[BaseException], ...], match: str | None = None):
            try:
                yield
            except expected_exc as exc:
                if match and not re.search(match, str(exc), re.IGNORECASE):
                    raise AssertionError(f"Exception {exc!r} did not match pattern {match!r}") from exc
                return
            raise AssertionError(f"Expected exception {expected_exc} was not raised")

        pytest_mod.raises = _raises  # type: ignore[attr-defined]
        sys.modules["pytest"] = pytest_mod

    try:
        import sqlalchemy  # noqa: F401
    except ImportError:
        from flowforge.db import make_engine, sessionmaker

        sa_mod = types.ModuleType("sqlalchemy")
        sa_mod.create_engine = lambda url, **kw: make_engine(url)  # type: ignore[attr-defined]
        sa_orm = types.ModuleType("sqlalchemy.orm")
        sa_orm.sessionmaker = sessionmaker  # type: ignore[attr-defined]
        sa_pool = types.ModuleType("sqlalchemy.pool")
        sa_pool.StaticPool = object  # type: ignore[attr-defined]
        sys.modules["sqlalchemy"] = sa_mod
        sys.modules["sqlalchemy.orm"] = sa_orm
        sys.modules["sqlalchemy.pool"] = sa_pool


def main() -> int:
    _install_offline_shims_if_needed()
    tests_dir = BACKEND_DIR / "tests"
    test_files = sorted(tests_dir.glob("test_*.py"))
    passed = 0
    failed = 0
    started = time.perf_counter()

    for tf in test_files:
        spec = importlib.util.spec_from_file_location(tf.stem, tf)
        if spec is None or spec.loader is None:
            continue
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        for attr_name in dir(module):
            if not attr_name.startswith("test_"):
                continue
            fn = getattr(module, attr_name)
            if not callable(fn):
                continue
            t0 = time.perf_counter()
            try:
                fn()
                ms = (time.perf_counter() - t0) * 1000
                print(f"PASS  {tf.name}::{attr_name} ({ms:.1f}ms)")
                passed += 1
            except Exception as exc:
                print(f"FAIL  {tf.name}::{attr_name}: {exc}")
                traceback.print_exc()
                failed += 1

    total_ms = (time.perf_counter() - started) * 1000
    print(f"\nSummary: {passed} passed, {failed} failed in {total_ms:.1f}ms")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
