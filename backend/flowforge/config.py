"""Runtime configuration for FlowForge Community."""
from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

DEFAULT_DATABASE_URL = "postgresql+psycopg://flowforge:change-me@localhost:5432/flowforge_dev"
DEFAULT_DEV_MASTER_KEY = "flowforge-dev-only-insecure-master-key-change-in-prod"


def database_url() -> str:
    """Read the DB URL at runtime so tests and local environments can override it."""
    return os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)


def master_key() -> str:
    """Return the master key used for credential encryption at rest."""
    return os.getenv("FLOWFORGE_MASTER_KEY", DEFAULT_DEV_MASTER_KEY)


def is_default_master_key() -> bool:
    """Return True if the application is using the default development master key."""
    return master_key() == DEFAULT_DEV_MASTER_KEY


def require_auth() -> bool:
    """Whether API endpoints require an API token by default."""
    return os.getenv("FLOWFORGE_REQUIRE_AUTH", "false").lower() in ("1", "true", "yes")


def bootstrap_api_token() -> str | None:
    """Optional bootstrap admin API token from environment."""
    val = os.getenv("FLOWFORGE_API_TOKEN", "").strip()
    return val or None


def allow_private_http() -> bool:
    """Whether outbound HTTP requests are permitted to hit loopback/private IPs.
    Strictly False by default for SSRF protection.
    """
    return os.getenv("FLOWFORGE_ALLOW_PRIVATE_HTTP", "false").lower() in ("1", "true", "yes")


def allowed_http_hosts() -> set[str]:
    """Comma-separated hostnames explicitly allowed for outbound HTTP requests."""
    raw = os.getenv("FLOWFORGE_ALLOWED_HTTP_HOSTS", "")
    return {item.strip().lower() for item in raw.split(",") if item.strip()}


def allowed_file_dir() -> Path:
    """Sandboxed directory for file import/export operations."""
    default_dir = Path(os.getenv("FLOWFORGE_ALLOWED_FILE_DIR", "./flowforge_data/files")).resolve()
    default_dir.mkdir(parents=True, exist_ok=True)
    return default_dir


def max_execution_seconds() -> float:
    return float(os.getenv("FLOWFORGE_MAX_EXECUTION_SECONDS", "30.0"))


def code_timeout_seconds() -> float:
    return float(os.getenv("FLOWFORGE_CODE_TIMEOUT_SECONDS", "5.0"))


def cors_origins() -> list[str]:
    raw = os.getenv("FLOWFORGE_CORS_ORIGINS", "http://127.0.0.1:5173,http://localhost:5173")
    return [origin.strip() for origin in raw.split(",") if origin.strip()]
