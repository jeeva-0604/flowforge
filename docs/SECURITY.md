# FlowForge Community — Security Model & Threat Model (`v0.3.0`)

## 1. Threat Assumptions
FlowForge assumes that workflow definitions, imported templates, webhook payloads, external HTTP redirect targets, skill manifests, and AI-generated drafts may be untrusted or malicious.

## 2. Implemented Security Controls

### A. Credential Encryption at Rest & Secret Masking
- **Cryptographic Design**: Uses `cryptography.fernet.Fernet` (AES-128-CBC with PKCS7 padding and HMAC-SHA256 authentication) backed by `PBKDF2HMAC` (SHA-256, 120,000 iterations) over `FLOWFORGE_MASTER_KEY`.
- **Key Rotation**: `CredentialVault.rotate_encrypted_payload(ciphertext, old_key, new_key)` re-encrypts stored credentials without exposing plaintext to logs.
- **Log & Trace Redaction**: `mask_secrets()` scrubs sensitive keys (`password`, `secret`, `token`, `api_key`, `authorization`) and any known decrypted credential values from `node_runs`, `result_data`, and `error` strings before database persistence.

### B. SSRF & Outbound Network Isolation
- `validate_outbound_url()` permits only `http` and `https` schemes, blocks `localhost` / `.local` / `.internal`, resolves DNS via `socket.getaddrinfo`, and blocks loopback (`127.0.0.0/8`, `::1`), RFC1918 private ranges (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`), and link-local / cloud metadata endpoints (`169.254.0.0/16`, `169.254.169.254`, `metadata.google.internal`).
- `safe_http_request()` disables automatic redirects and validates every `301/302/303/307/308` `Location` target hop-by-hop before following.

### C. Code Execution & File-System Isolation
- **Subprocess Isolation**: The `code` node spawns `python -I` in a separate child process with an empty environment (`PATH=""`), blocks dangerous tokens (`__import__`, `import os`, `import subprocess`, `import socket`, `open(`, `eval(`, `exec(`), restricts `__builtins__`, caps stdout at 512 KB, and enforces a strict wall-clock timeout.
- **Sandboxed File I/O**: `resolve_permitted_path()` confines all `file_io` operations to `FLOWFORGE_ALLOWED_FILE_DIR`, rejecting `..`, drive letters, and symlink escapes.
- **Parameterized SQL**: `sql_query` requires `:param` bindings and rejects multi-statement queries (`;`) and destructive DDL (`DROP`, `TRUNCATE`, `ALTER`, `GRANT`).

### D. Authentication, RBAC, Webhooks & Audit Logging
- **Scoped API Tokens**: Tokens (`ffk_...`) are hashed with SHA-256 (`api_tokens.token_hash`), support `viewer`, `editor`, and `admin` roles with granular scopes (`workflows:read`, `workflows:write`, `workflows:execute`, `credentials:manage`, `admin:*`), and support instant revocation.
- **Webhook Verification**: `/api/webhooks/ingest/{slug}` verifies `X-FlowForge-Signature` using constant-time `hmac.compare_digest` (HMAC-SHA256) and deduplicates `X-FlowForge-Delivery` IDs.
- **Audit Trail**: Sensitive mutations record immutable rows in `audit_logs`.

## 3. Known Limitations & Production Guidance
- **OS-Level Container Sandboxing**: While `code` nodes run in `python -I` subprocesses with restricted builtins and timeouts, production multi-tenant deployments should additionally run worker processes inside unprivileged Linux namespaces/cgroups or containers with seccomp profiles.
- **Default Dev Master Key**: If `FLOWFORGE_MASTER_KEY` is not set, FlowForge logs a warning in `/api/system/diagnostics` (`using_default_dev_master_key: true`). Always set a unique `FLOWFORGE_MASTER_KEY` and `FLOWFORGE_REQUIRE_AUTH=true` before network exposure.
