# ADR 0003: Clean-Room Integration SDK and SHA-256 Verified Skills Registry

- **Status:** Accepted (2026-10-20)
- **Context:** FlowForge must be an independent Apache-2.0-targeted platform with its own schema, SDK, and reusable Skills ecosystem.
- **Decision:** Define a declarative `NodeSpec` / `FieldSpec` SDK (`flowforge/sdk.py`) and a versioned `SkillManifest` format (`flowforge/skills.py`) with canonical JSON SHA-256 integrity hashes and static prompt-injection/command scanning.
- **Consequences:** Contributors can author nodes and skills with predictable schemas, while untrusted manifests tampering with hashes or requesting privileged permissions are rejected automatically.
