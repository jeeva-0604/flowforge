# ADR 0002: Fernet Credential Vault, SSRF Hop Validation, and Subprocess Code Isolation

- **Status:** Accepted (2026-10-20)
- **Context:** Workflow platforms routinely handle API keys, make outbound HTTP calls, and run user transformation snippets.
- **Decision:**
  1. Encrypt credentials at rest using `cryptography.fernet.Fernet` (AES-128-CBC + HMAC-SHA256) with keys derived via `PBKDF2HMAC` (120,000 iterations, SHA-256).
  2. Validate every outbound HTTP URL and every HTTP redirect hop against loopback, RFC1918 private networks, and link-local/cloud metadata (`169.254.169.254`).
  3. Execute `code` nodes in a separate `python -I` subprocess with stripped environment variables, restricted builtins, and hard timeouts.
- **Consequences:** Prevents accidental credential leakage in logs/UI, blocks SSRF redirect bypasses, and isolates the FastAPI process from user code crashes or infinite loops.
