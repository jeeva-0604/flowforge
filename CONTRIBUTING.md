# Contributing to FlowForge Community

Thank you for helping build an independent, open-source workflow automation platform!

## Clean-Room & Licensing Rules
1. All contributions must be original work licensed under Apache-2.0.
2. Never copy source code, UI assets, icons, or proprietary schemas from n8n or any commercial automation tool.
3. Every new integration node (`sdk.py`) or skill (`skills.py`) must include configuration schemas, input/output contracts, unit tests, and security validation.

## Running Checks Before Submitting a PR
```powershell
$env:PYTHONPATH = "backend"
python backendun_tests.py
python -m flowforge.cli doctor
cd frontend
node verify_frontend.mjs
npm run build
```
