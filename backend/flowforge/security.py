"""Enterprise security primitives for FlowForge Community."""
from __future__ import annotations

import base64
from collections import defaultdict, deque
import hashlib
import hmac
import ipaddress
import json
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import time
from typing import Any
from urllib.parse import urljoin, urlparse

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import httpx

from .config import (
    allow_private_http,
    allowed_file_dir,
    allowed_http_hosts,
    code_timeout_seconds,
    master_key,
)

SENSITIVE_KEY_MARKERS = (
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "authorization",
    "private_key",
    "client_secret",
    "access_key",
)

_PBKDF2_SALT = b"flowforge-community-credential-vault-v1-salt"


class SecurityError(ValueError):
    """Base exception for security policy violations."""


class SSRFError(SecurityError):
    """Raised when an outbound URL violates SSRF network isolation rules."""


class PathSecurityError(SecurityError):
    """Raised when a file path attempts to escape the permitted sandbox directory."""


class CodeExecutionError(SecurityError):
    """Raised when isolated code execution fails or violates resource/security policies."""


def _derive_fernet_key(raw_key: str) -> bytes:
    cleaned = raw_key.strip().encode("utf-8")
    if len(cleaned) == 44:
        try:
            decoded = base64.urlsafe_b64decode(cleaned)
            if len(decoded) == 32:
                return cleaned
        except Exception:
            pass
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=_PBKDF2_SALT,
        iterations=120_000,
    )
    return base64.urlsafe_b64encode(kdf.derive(cleaned))


def key_fingerprint(raw_key: str | None = None) -> str:
    target = raw_key if raw_key is not None else master_key()
    digest = hashlib.sha256(target.encode("utf-8")).hexdigest()[:12]
    return f"sha256:{digest}"


class CredentialVault:
    """Encrypts and decrypts structured credential dictionaries at rest using Fernet."""

    def __init__(self, key: str | None = None) -> None:
        self._raw_key = key if key is not None else master_key()
        self._fernet = Fernet(_derive_fernet_key(self._raw_key))
        self.fingerprint = key_fingerprint(self._raw_key)

    def encrypt_dict(self, payload: dict[str, Any]) -> str:
        serialized = json.dumps(payload, sort_keys=True).encode("utf-8")
        return self._fernet.encrypt(serialized).decode("ascii")

    def decrypt_dict(self, token: str) -> dict[str, Any]:
        try:
            raw = self._fernet.decrypt(token.encode("ascii"))
            data = json.loads(raw.decode("utf-8"))
            if not isinstance(data, dict):
                raise SecurityError("Decrypted credential payload is not a JSON object")
            return data
        except InvalidToken as exc:
            raise SecurityError("Credential decryption failed: invalid master key or corrupted ciphertext") from exc

    @staticmethod
    def rotate_encrypted_payload(ciphertext: str, old_key: str, new_key: str) -> tuple[str, str]:
        old_vault = CredentialVault(old_key)
        new_vault = CredentialVault(new_key)
        decrypted = old_vault.decrypt_dict(ciphertext)
        return new_vault.encrypt_dict(decrypted), new_vault.fingerprint


def mask_secrets(value: Any, known_secrets: list[str] | None = None) -> Any:
    secrets_list = [s for s in (known_secrets or []) if isinstance(s, str) and len(s) >= 4]
    if isinstance(value, dict):
        masked: dict[str, Any] = {}
        for k, v in value.items():
            k_lower = str(k).lower()
            if any(marker in k_lower for marker in SENSITIVE_KEY_MARKERS):
                masked[k] = "***REDACTED***"
            else:
                masked[k] = mask_secrets(v, secrets_list)
        return masked
    if isinstance(value, list):
        return [mask_secrets(item, secrets_list) for item in value]
    if isinstance(value, str):
        result = value
        for secret in secrets_list:
            if secret in result:
                result = result.replace(secret, "***REDACTED***")
        return result
    return value


def _check_ip_address(ip_str: str) -> None:
    ip = ipaddress.ip_address(ip_str)
    if ip.is_link_local or ip_str == "169.254.169.254":
        raise SSRFError(f"Blocked link-local or cloud metadata IP address: {ip_str}")
    if ip.is_loopback:
        raise SSRFError(f"Blocked loopback IP address: {ip_str}")
    if ip.is_private:
        raise SSRFError(f"Blocked private network IP address: {ip_str}")
    if ip.is_multicast or ip.is_unspecified or ip.is_reserved:
        raise SSRFError(f"Blocked reserved/non-routable IP address: {ip_str}")


def validate_outbound_url(
    url: str,
    *,
    allow_private: bool | None = None,
    allowed_hosts: set[str] | None = None,
):
    if not isinstance(url, str) or not url.strip():
        raise SSRFError("URL must be a non-empty string")
    parsed = urlparse(url.strip())
    if parsed.scheme.lower() not in ("http", "https"):
        raise SSRFError(f"Unsupported URL scheme {parsed.scheme!r}; only 'http' and 'https' are permitted")
    hostname = (parsed.hostname or "").lower()
    if not hostname:
        raise SSRFError("URL must include a valid hostname")

    if hostname in ("169.254.169.254", "metadata.google.internal", "metadata"):
        raise SSRFError(f"Access to cloud metadata endpoint {hostname!r} is strictly prohibited")

    permit_private = allow_private if allow_private is not None else allow_private_http()
    explicit_hosts = allowed_hosts if allowed_hosts is not None else allowed_http_hosts()
    if hostname in explicit_hosts or permit_private:
        return parsed

    try:
        ipaddress.ip_address(hostname)
        _check_ip_address(hostname)
        return parsed
    except ValueError:
        pass

    if hostname in ("localhost", "localhost.localdomain") or hostname.endswith(".local") or hostname.endswith(".internal"):
        raise SSRFError(f"Blocked internal/local hostname: {hostname!r}")

    try:
        addr_info = socket.getaddrinfo(hostname, parsed.port or (443 if parsed.scheme == "https" else 80))
    except socket.gaierror as exc:
        raise SSRFError(f"Could not resolve hostname {hostname!r}: {exc}") from exc

    for family, _, _, _, sockaddr in addr_info:
        if family in (socket.AF_INET, socket.AF_INET6):
            resolved_ip = sockaddr[0]
            _check_ip_address(resolved_ip)

    return parsed


def safe_http_request(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    params: dict[str, Any] | None = None,
    json_body: Any = None,
    timeout_seconds: float = 10.0,
    max_response_bytes: int = 1_048_576,
    max_redirects: int = 3,
    allow_private: bool | None = None,
    allowed_hosts: set[str] | None = None,
    transport: httpx.BaseTransport | None = None,
) -> dict[str, Any]:
    current_url = url
    req_method = method.upper().strip()
    if req_method not in ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"):
        raise SecurityError(f"Unsupported HTTP method: {req_method}")

    for hop in range(max_redirects + 1):
        validate_outbound_url(
            current_url,
            allow_private=allow_private,
            allowed_hosts=allowed_hosts,
        )
        client_kwargs: dict[str, Any] = {
            "timeout": min(max(timeout_seconds, 0.5), 30.0),
            "follow_redirects": False,
        }
        if transport is not None:
            client_kwargs["transport"] = transport

        with httpx.Client(**client_kwargs) as client:
            response = client.request(
                req_method if hop == 0 else "GET",
                current_url,
                headers=headers,
                params=params if hop == 0 else None,
                json=json_body if hop == 0 and req_method in ("POST", "PUT", "PATCH") else None,
            )
            if response.status_code in (301, 302, 303, 307, 308):
                location = response.headers.get("location")
                if not location:
                    break
                if hop >= max_redirects:
                    raise SSRFError(f"Maximum redirect limit ({max_redirects}) exceeded")
                current_url = urljoin(current_url, location)
                continue

            content_bytes = response.content
            if len(content_bytes) > max_response_bytes:
                raise SecurityError(
                    f"HTTP response size ({len(content_bytes)} bytes) exceeds limit ({max_response_bytes} bytes)"
                )
            try:
                parsed_body = response.json()
            except Exception:
                parsed_body = response.text

            return {
                "status_code": response.status_code,
                "ok": 200 <= response.status_code < 300,
                "url": str(response.request.url),
                "headers": dict(response.headers),
                "data": parsed_body,
            }

    raise SSRFError("Redirect loop terminated")


def resolve_permitted_path(relative_path: str, base_dir: Path | None = None) -> Path:
    if not isinstance(relative_path, str) or not relative_path.strip():
        raise PathSecurityError("File path must be a non-empty relative path")
    cleaned = relative_path.strip().replace("\\", "/")
    if cleaned.startswith("/") or ":" in cleaned:
        raise PathSecurityError("Absolute paths and drive letters are not permitted")
    parts = Path(cleaned).parts
    if ".." in parts:
        raise PathSecurityError("Path traversal ('..') is not permitted")

    root = (base_dir or allowed_file_dir()).resolve()
    root.mkdir(parents=True, exist_ok=True)
    candidate = (root / cleaned).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise PathSecurityError(f"Resolved path escapes permitted sandbox directory: {relative_path!r}") from exc
    return candidate


_ISOLATED_RUNNER_SCRIPT = """
import json
import sys

FORBIDDEN_TOKENS = (
    "__import__", "import os", "import subprocess", "import socket",
    "import shutil", "import pathlib", "open(", "eval(", "exec(", "compile(",
)

payload = json.loads(sys.stdin.read())
code = payload["code"]
input_data = payload["input_data"]

for token in FORBIDDEN_TOKENS:
    if token in code:
        print(json.dumps({"ok": False, "error": f"Security policy blocked forbidden construct: {token}"}))
        sys.exit(0)

safe_builtins = {
    "abs": abs, "all": all, "any": any, "bool": bool, "dict": dict,
    "enumerate": enumerate, "filter": filter, "float": float, "int": int,
    "isinstance": isinstance, "len": len, "list": list, "map": map,
    "max": max, "min": min, "range": range, "round": round, "set": set,
    "sorted": sorted, "str": str, "sum": sum, "tuple": tuple, "zip": zip,
}

env = {"__builtins__": safe_builtins, "data": dict(input_data), "result": None}
try:
    exec(code, env, env)
    out = env.get("result")
    if out is None:
        out = env.get("data", {})
    if not isinstance(out, dict):
        out = {"value": out}
    print(json.dumps({"ok": True, "result": out}))
except Exception as exc:
    print(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}))
"""


def execute_isolated_python(
    code: str,
    input_data: dict[str, Any],
    *,
    timeout_seconds: float | None = None,
) -> dict[str, Any]:
    if not isinstance(code, str) or not code.strip():
        raise CodeExecutionError("Code node requires non-empty 'code' string")
    if len(code) > 16_000:
        raise CodeExecutionError("Code exceeds maximum length of 16,000 characters")

    timeout = min(max(timeout_seconds or code_timeout_seconds(), 0.2), 15.0)
    stdin_payload = json.dumps({"code": code, "input_data": input_data})

    try:
        proc = subprocess.run(
            [sys.executable, "-I", "-c", _ISOLATED_RUNNER_SCRIPT],
            input=stdin_payload,
            capture_output=True,
            text=True,
            timeout=timeout,
            env={"PATH": "", "PYTHONIOENCODING": "utf-8"},
        )
    except subprocess.TimeoutExpired as exc:
        raise CodeExecutionError(f"Isolated code execution timed out after {timeout:.1f}s") from exc

    stdout = (proc.stdout or "").strip()
    if len(stdout) > 512_000:
        raise CodeExecutionError("Isolated code output exceeded 512 KB cap")
    if not stdout:
        stderr_snippet = (proc.stderr or "").strip()[:400]
        raise CodeExecutionError(f"Isolated code runner failed: {stderr_snippet or 'empty output'}")

    try:
        parsed = json.loads(stdout.splitlines()[-1])
    except Exception as exc:
        raise CodeExecutionError("Isolated code runner did not return valid JSON") from exc

    if not parsed.get("ok"):
        raise CodeExecutionError(str(parsed.get("error", "Code execution error")))
    res = parsed.get("result", {})
    return res if isinstance(res, dict) else {"value": res}


def hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def generate_api_token() -> tuple[str, str, str]:
    raw = "ffk_" + secrets.token_urlsafe(28)
    return raw, raw[:10], hash_token(raw)


def verify_webhook_signature(payload_bytes: bytes, secret: str, signature_header: str) -> bool:
    if not signature_header:
        return False
    clean_sig = signature_header.strip()
    if clean_sig.startswith("sha256="):
        clean_sig = clean_sig[len("sha256=") :]
    expected = hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, clean_sig)


class RateLimiter:
    def __init__(self, max_requests: int = 120, window_seconds: float = 60.0) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._buckets: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str) -> bool:
        now = time.monotonic()
        bucket = self._buckets[key]
        cutoff = now - self.window_seconds
        while bucket and bucket[0] < cutoff:
            bucket.popleft()
        if len(bucket) >= self.max_requests:
            return False
        bucket.append(now)
        return True
