"""FlowForge Skills System."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from typing import Any

from .compat import CompatBaseModel, Field

ALLOWED_PERMISSIONS = {"none", "data:transform", "workflow:draft", "workflow:analyze", "sql:analyze"}
SUSPICIOUS_PATTERNS = (
    "ignore previous instructions",
    "exfiltrate",
    "curl http",
    "wget http",
    "rm -rf",
    "/etc/passwd",
    "169.254.169.254",
    "os.system",
    "subprocess.Popen",
)


class SkillValidationError(ValueError):
    """Raised when a skill manifest or invocation violates schema or security constraints."""


class SkillManifest(CompatBaseModel):
    id: str = Field(min_length=3, max_length=80)
    version: str = Field(min_length=5, max_length=30)
    name: str = Field(min_length=3, max_length=120)
    category: str = Field(default="Automation")
    description: str = Field(min_length=10, max_length=1000)
    intended_use: str = Field(default="")
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    permissions: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    license: str = Field(default="Apache-2.0")
    provenance: str = Field(default="FlowForge Community First-Party")
    compatibility: str = Field(default=">=0.3.0")
    security_constraints: list[str] = Field(default_factory=list)
    example_input: dict[str, Any] = Field(default_factory=dict)
    integrity_hash: str = Field(default="")


def compute_skill_integrity_hash(manifest_dict: dict[str, Any]) -> str:
    payload = {k: v for k, v in manifest_dict.items() if k != "integrity_hash"}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(canonical).hexdigest()


def validate_skill_manifest(manifest_data: dict[str, Any], verify_hash: bool = False) -> SkillManifest:
    manifest = SkillManifest.model_validate(manifest_data)
    if not re.match(r"^[a-z0-9][a-z0-9-]{2,79}$", manifest.id):
        raise SkillValidationError(f"Invalid skill ID {manifest.id!r}; use lowercase kebab-case")

    for perm in manifest.permissions:
        if perm not in ALLOWED_PERMISSIONS:
            raise SkillValidationError(f"Skill requests unsupported or privileged permission: {perm!r}")

    serialized_lower = json.dumps(manifest_data).lower()
    for pattern in SUSPICIOUS_PATTERNS:
        if pattern in serialized_lower:
            raise SkillValidationError(
                f"Skill rejected by security scanner: suspicious pattern {pattern!r} detected"
            )

    expected_hash = compute_skill_integrity_hash(manifest.model_dump(mode="json"))
    if verify_hash and manifest.integrity_hash and manifest.integrity_hash != expected_hash:
        raise SkillValidationError(
            f"Skill integrity hash mismatch: expected {expected_hash}, got {manifest.integrity_hash}"
        )
    manifest.integrity_hash = expected_hash
    return manifest


def _build_first_party_skills() -> list[SkillManifest]:
    raw_skills: list[dict[str, Any]] = [
        {
            "id": "rest-api-workflow-builder",
            "version": "1.0.0",
            "name": "REST API Workflow Builder",
            "category": "Workflow Authoring",
            "description": "Generates a complete Trigger -> HTTP Request -> IF Condition -> Output workflow definition for any public REST API endpoint.",
            "intended_use": "Bootstrap resilient API integrations with status-code validation and retry policy.",
            "input_schema": {"type": "object", "required": ["url"], "properties": {"url": {"type": "string"}, "method": {"type": "string"}}},
            "output_schema": {"type": "object", "required": ["workflow_definition", "notes"]},
            "permissions": ["workflow:draft"],
            "dependencies": [],
            "license": "Apache-2.0",
            "provenance": "FlowForge Community First-Party",
            "compatibility": ">=0.3.0",
            "security_constraints": ["No network execution during draft generation", "Enforces SSRF-safe URL structure"],
            "example_input": {"url": "https://api.example.com/v1/orders", "method": "GET"},
        },
        {
            "id": "postgres-query-quality-helper",
            "version": "1.0.0",
            "name": "PostgreSQL Query & Data-Quality Helper",
            "category": "Data & SQL",
            "description": "Audits a SQL query for parameterization safety, detects unsafe string concatenation, and generates data-quality assertion checks.",
            "intended_use": "Ensure SQL queries use safe :param bindings and read-only best practices before execution.",
            "input_schema": {"type": "object", "required": ["query"], "properties": {"query": {"type": "string"}}},
            "output_schema": {"type": "object", "required": ["is_safe", "parameterized", "parameters_detected", "recommendations"]},
            "permissions": ["sql:analyze"],
            "dependencies": [],
            "license": "Apache-2.0",
            "provenance": "FlowForge Community First-Party",
            "compatibility": ">=0.3.0",
            "security_constraints": ["Static query inspection only; never executes arbitrary DDL"],
            "example_input": {"query": "SELECT id, email FROM users WHERE status = :status LIMIT 50"},
        },
        {
            "id": "csv-json-transformation-helper",
            "version": "1.0.0",
            "name": "CSV/JSON Transformation Helper",
            "category": "Data & SQL",
            "description": "Normalizes CSV text or JSON record arrays, trims whitespace, infers numeric types, and computes field completeness metrics.",
            "intended_use": "Clean and validate tabular data inside automated pipelines.",
            "input_schema": {"type": "object", "properties": {"records": {"type": "array"}, "csv_text": {"type": "string"}}},
            "output_schema": {"type": "object", "required": ["normalized_records", "row_count", "columns"]},
            "permissions": ["data:transform"],
            "dependencies": [],
            "license": "Apache-2.0",
            "provenance": "FlowForge Community First-Party",
            "compatibility": ">=0.3.0",
            "security_constraints": ["In-memory transformation capped at 10,000 rows"],
            "example_input": {"csv_text": "name,score\nAlice,95\nBob,88"},
        },
        {
            "id": "workflow-test-generator",
            "version": "1.0.0",
            "name": "Workflow Test Suite Generator",
            "category": "Testing & QA",
            "description": "Analyzes a workflow definition and generates positive, negative, and boundary test input fixtures with expected assertions.",
            "intended_use": "Automate regression test creation for newly authored workflows.",
            "input_schema": {"type": "object", "required": ["nodes"], "properties": {"nodes": {"type": "array"}, "edges": {"type": "array"}}},
            "output_schema": {"type": "object", "required": ["test_cases", "coverage_summary"]},
            "permissions": ["workflow:analyze"],
            "dependencies": [],
            "license": "Apache-2.0",
            "provenance": "FlowForge Community First-Party",
            "compatibility": ">=0.3.0",
            "security_constraints": ["Pure static analysis of workflow graph"],
            "example_input": {
                "nodes": [{"id": "start", "type": "trigger"}, {"id": "check", "type": "if_condition", "config": {"field": "amount", "operator": "gt", "value": 100}}, {"id": "out", "type": "output"}],
                "edges": [{"source": "start", "target": "check"}, {"source": "check", "target": "out", "source_handle": "true"}],
            },
        },
        {
            "id": "workflow-debugging-assistant",
            "version": "1.0.0",
            "name": "Workflow Debugging Assistant",
            "category": "Observability & Triage",
            "description": "Inspects node execution traces to pinpoint failed steps, type mismatches, or pruned conditional branches.",
            "intended_use": "Accelerate root-cause analysis when a workflow execution fails or produces unexpected output.",
            "input_schema": {"type": "object", "properties": {"error": {"type": "string"}, "node_runs": {"type": "array"}}},
            "output_schema": {"type": "object", "required": ["root_cause", "failed_nodes", "remediation_steps"]},
            "permissions": ["workflow:analyze"],
            "dependencies": [],
            "license": "Apache-2.0",
            "provenance": "FlowForge Community First-Party",
            "compatibility": ">=0.3.0",
            "security_constraints": ["Operates only on redacted execution traces"],
            "example_input": {"error": "Blocked loopback IP address: 127.0.0.1", "node_runs": [{"node_id": "http_1", "status": "failed"}]},
        },
        {
            "id": "safe-error-triage-assistant",
            "version": "1.0.0",
            "name": "Safe Error-Triage Assistant",
            "category": "Observability & Triage",
            "description": "Classifies runtime errors into transient network faults, validation errors, or security policy blocks and recommends retry policies.",
            "intended_use": "Decide whether an error should be retried with exponential backoff or routed to a dead-letter queue.",
            "input_schema": {"type": "object", "required": ["error_message"], "properties": {"error_message": {"type": "string"}}},
            "output_schema": {"type": "object", "required": ["classification", "retriable", "recommended_retry_policy"]},
            "permissions": ["workflow:analyze"],
            "dependencies": [],
            "license": "Apache-2.0",
            "provenance": "FlowForge Community First-Party",
            "compatibility": ">=0.3.0",
            "security_constraints": ["Never suggests bypassing SSRF or sandbox boundaries"],
            "example_input": {"error_message": "HTTP 503 Service Unavailable"},
        },
    ]
    return [validate_skill_manifest(item) for item in raw_skills]


FIRST_PARTY_SKILLS: dict[str, SkillManifest] = {s.id: s for s in _build_first_party_skills()}


def list_skills() -> list[dict[str, Any]]:
    return [s.model_dump(mode="json") for s in FIRST_PARTY_SKILLS.values()]


def get_skill(skill_id: str) -> SkillManifest | None:
    return FIRST_PARTY_SKILLS.get(skill_id)


def execute_skill(skill_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    manifest = FIRST_PARTY_SKILLS.get(skill_id)
    if manifest is None:
        raise SkillValidationError(f"Unknown skill ID: {skill_id!r}")

    validate_skill_manifest(manifest.model_dump(mode="json"), verify_hash=True)

    if skill_id == "rest-api-workflow-builder":
        url = str(payload.get("url") or "https://api.example.com/v1/items")
        method = str(payload.get("method") or "GET").upper()
        wf_def = {
            "schema_version": "1.0",
            "nodes": [
                {"id": "trigger_1", "type": "trigger", "position": {"x": 80, "y": 180}, "config": {"label": "Manual Trigger"}},
                {
                    "id": "http_1",
                    "type": "http_request",
                    "position": {"x": 340, "y": 180},
                    "config": {"label": "Fetch API", "method": method, "url": url, "response_field": "api_response"},
                    "retry_policy": {"max_attempts": 3, "backoff_ms": 200, "backoff_multiplier": 2.0},
                },
                {
                    "id": "if_1",
                    "type": "if_condition",
                    "position": {"x": 600, "y": 180},
                    "config": {"label": "Check 2xx OK", "field": "api_response.ok", "operator": "eq", "value": True},
                },
                {"id": "output_ok", "type": "output", "position": {"x": 860, "y": 120}, "config": {"label": "Success Output"}},
                {"id": "output_err", "type": "output", "position": {"x": 860, "y": 260}, "config": {"label": "Failure Output"}},
            ],
            "edges": [
                {"source": "trigger_1", "target": "http_1"},
                {"source": "http_1", "target": "if_1"},
                {"source": "if_1", "target": "output_ok", "source_handle": "true", "label": "true"},
                {"source": "if_1", "target": "output_err", "source_handle": "false", "label": "false"},
            ],
        }
        return {
            "skill_id": skill_id,
            "integrity_verified": True,
            "workflow_definition": wf_def,
            "notes": f"Generated 5-node resilient REST workflow for {method} {url} with 3x exponential retry.",
        }

    if skill_id == "postgres-query-quality-helper":
        query = str(payload.get("query") or "").strip()
        params = re.findall(r":([a-zA-Z_][a-zA-Z0-9_]*)", query)
        has_multi_stmt = ";" in query[:-1] if query else False
        has_dangerous_ddl = bool(re.search(r"\b(DROP|TRUNCATE|ALTER|GRANT)\b", query, re.IGNORECASE))
        has_concat = ("+" in query and "'" in query) or "%s" in query or "f\"" in query
        is_safe = bool(query) and not has_multi_stmt and not has_dangerous_ddl and not has_concat
        recs: list[str] = []
        if not params:
            recs.append("Use named :param bindings for dynamic filter values.")
        if has_multi_stmt:
            recs.append("Remove multiple statements (;); execute one parameterized statement per node.")
        if has_dangerous_ddl:
            recs.append("Avoid destructive DDL (DROP/TRUNCATE/ALTER) inside automation workflows.")
        if "limit" not in query.lower() and query.lower().startswith("select"):
            recs.append("Add a LIMIT clause to bound result set memory consumption.")
        return {
            "skill_id": skill_id,
            "integrity_verified": True,
            "is_safe": is_safe,
            "parameterized": len(params) > 0,
            "parameters_detected": sorted(set(params)),
            "recommendations": recs or ["Query follows parameterized SQL best practices."],
        }

    if skill_id == "csv-json-transformation-helper":
        records: list[dict[str, Any]] = []
        if isinstance(payload.get("records"), list):
            records = [dict(r) for r in payload["records"] if isinstance(r, dict)]
        elif isinstance(payload.get("csv_text"), str) and payload["csv_text"].strip():
            reader = csv.DictReader(io.StringIO(payload["csv_text"].strip()))
            records = [dict(row) for row in reader]

        normalized: list[dict[str, Any]] = []
        columns: set[str] = set()
        for row in records[:10_000]:
            clean_row: dict[str, Any] = {}
            for k, v in row.items():
                if k is None:
                    continue
                col = str(k).strip()
                columns.add(col)
                if isinstance(v, str):
                    val_str = v.strip()
                    if re.match(r"^-?\d+$", val_str):
                        clean_row[col] = int(val_str)
                    elif re.match(r"^-?\d+\.\d+$", val_str):
                        clean_row[col] = float(val_str)
                    else:
                        clean_row[col] = val_str
                else:
                    clean_row[col] = v
            normalized.append(clean_row)
        return {
            "skill_id": skill_id,
            "integrity_verified": True,
            "normalized_records": normalized,
            "row_count": len(normalized),
            "columns": sorted(columns),
        }

    if skill_id == "workflow-test-generator":
        nodes = payload.get("nodes") or []
        test_cases = [
            {
                "name": "happy_path_default_payload",
                "input": {"user": "test_operator", "ok": True, "amount": 250, "items": [{"id": 1, "active": True}]},
                "expected_status": "succeeded",
            },
            {
                "name": "boundary_empty_payload",
                "input": {},
                "expected_status": "succeeded",
            },
        ]
        for node in nodes:
            if isinstance(node, dict) and node.get("type") == "if_condition":
                cfg = node.get("config") or {}
                field = cfg.get("field", "flag")
                val = cfg.get("value", True)
                test_cases.append({"name": f"branch_true_{node.get('id')}", "input": {field: val}, "expected_status": "succeeded"})
                test_cases.append({"name": f"branch_false_{node.get('id')}", "input": {field: None}, "expected_status": "succeeded"})
        return {
            "skill_id": skill_id,
            "integrity_verified": True,
            "test_cases": test_cases,
            "coverage_summary": f"Generated {len(test_cases)} test fixtures covering {len(nodes)} nodes.",
        }

    if skill_id == "workflow-debugging-assistant":
        err = str(payload.get("error") or "")
        node_runs = payload.get("node_runs") or []
        failed_nodes = [n.get("node_id") for n in node_runs if isinstance(n, dict) and n.get("status") == "failed"]
        if "loopback" in err.lower() or "private" in err.lower() or "ssrf" in err.lower():
            root_cause = "Outbound HTTP request targeted a restricted loopback/private/metadata IP blocked by SSRF guard."
            steps = [
                "Update the HTTP Request node URL to a public HTTPS endpoint.",
                "For local mock testing only, add the test hostname to FLOWFORGE_ALLOWED_HTTP_HOSTS.",
            ]
        elif "timed out" in err.lower():
            root_cause = "Node execution exceeded its configured timeout ceiling."
            steps = ["Optimize the target query/script or increase timeout_seconds within policy limits."]
        else:
            root_cause = err or "No runtime error recorded; check conditional branch handles."
            steps = ["Inspect per-node input_data and output_data in the Execution Trace drawer."]
        return {
            "skill_id": skill_id,
            "integrity_verified": True,
            "root_cause": root_cause,
            "failed_nodes": failed_nodes,
            "remediation_steps": steps,
        }

    if skill_id == "safe-error-triage-assistant":
        msg = str(payload.get("error_message") or "")
        msg_lower = msg.lower()
        if any(code in msg_lower for code in ("502", "503", "504", "429", "timeout", "temporarily")):
            return {
                "skill_id": skill_id,
                "integrity_verified": True,
                "classification": "transient_network_or_rate_limit",
                "retriable": True,
                "recommended_retry_policy": {"max_attempts": 3, "backoff_ms": 250, "backoff_multiplier": 2.0},
            }
        if any(tok in msg_lower for tok in ("ssrf", "blocked", "forbidden", "traversal", "validation")):
            return {
                "skill_id": skill_id,
                "integrity_verified": True,
                "classification": "security_or_validation_violation",
                "retriable": False,
                "recommended_retry_policy": {"max_attempts": 1, "backoff_ms": 0, "backoff_multiplier": 1.0},
            }
        return {
            "skill_id": skill_id,
            "integrity_verified": True,
            "classification": "application_error",
            "retriable": False,
            "recommended_retry_policy": {"max_attempts": 1, "backoff_ms": 100, "backoff_multiplier": 1.5},
        }

    raise SkillValidationError(f"No execution handler registered for skill {skill_id!r}")
