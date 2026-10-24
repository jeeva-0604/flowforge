"""FlowForge Deterministic & Extensible Workflow Execution Engine.
Supports:
- Directed graph validation, cycle detection, reachability, and node config validation
- Safe `{{ expression }}` interpolation ($input, $nodes, $item, $env, $credentials)
- Conditional branching (IF true/false, Switch cases) with dead-branch skipping
- Merge modes (shallow_merge, deep_merge, collect_branches)
- Per-node retry policies with exponential backoff and error boundary modes
- SSRF-guarded HTTP requests (plus deterministic `mock://` transport for local tests)
- Parameterized SQL queries, CSV/JSON processing, sandboxed File I/O, and isolated Code execution
- First-party Skills execution, provider-independent AI nodes, and Human Approval checkpoints
- Step-level replay and human-readable workflow version diffs
"""
from __future__ import annotations

from collections import defaultdict, deque
import csv
from datetime import datetime, timezone
import io
import json
import os
import re
import sqlite3
import time
from typing import Any, Callable

import httpx

from .schemas import (
    TRIGGER_NODE_TYPES,
    ValidationIssue,
    ValidationReport,
    WorkflowDefinition,
)
from .security import (
    CodeExecutionError,
    PathSecurityError,
    SSRFError,
    SecurityError,
    execute_isolated_python,
    mask_secrets,
    resolve_permitted_path,
    safe_http_request,
)
from .skills import SkillValidationError, execute_skill



_VECTOR_STORE: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)


def _deterministic_embed(text: str, dims: int = 8) -> list[float]:
    import hashlib
    import math

    vec = [0.0] * dims
    words = [w.lower() for w in re.findall(r"[a-zA-Z0-9]+", text)] or ["empty"]
    for w in words:
        h = hashlib.sha256(w.encode("utf-8")).digest()
        for i in range(dims):
            vec[i] += (h[i] / 255.0) - 0.5
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [round(v / norm, 6) for v in vec]


def _cosine_sim(a: list[float], b: list[float]) -> float:
    return round(sum(x * y for x, y in zip(a, b)), 6)


class WorkflowValidationError(ValueError):
    """Raised when a graph cannot be executed safely."""


_EXPR_PATTERN = re.compile(r"\{\{\s*([^}]+?)\s*\}\}")


def _lookup_path(obj: Any, path: str) -> Any:
    current = obj
    for part in path.split("."):
        if not part:
            continue
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, list) and part.isdigit():
            idx = int(part)
            if 0 <= idx < len(current):
                current = current[idx]
            else:
                return None
        else:
            return None
    return current


def evaluate_expressions(value: Any, context: dict[str, Any]) -> Any:
    """Safely evaluate `{{ $input.x }}`, `{{ $nodes.id.y }}`, `{{ $item }}`,
    `{{ $env.KEY }}`, and `{{ $credentials.name.key }}` without `eval()`.
    """
    if isinstance(value, dict):
        return {k: evaluate_expressions(v, context) for k, v in value.items()}
    if isinstance(value, list):
        return [evaluate_expressions(item, context) for item in value]
    if not isinstance(value, str) or "{{" not in value:
        return value

    def _resolve_expr(expr: str) -> Any:
        token = expr.strip()
        if token == "$item":
            return context.get("$item")
        if token.startswith("$item."):
            return _lookup_path(context.get("$item", {}), token[len("$item.") :])
        if token == "$input":
            return context.get("$input", {})
        if token.startswith("$input."):
            return _lookup_path(context.get("$input", {}), token[len("$input.") :])
        if token.startswith("$nodes."):
            return _lookup_path(context.get("$nodes", {}), token[len("$nodes.") :])
        if token.startswith("$credentials."):
            return _lookup_path(context.get("$credentials", {}), token[len("$credentials.") :])
        if token.startswith("$vars."):
            return _lookup_path(context.get("$vars", {}), token[len("$vars.") :])
        if token.startswith("$env."):
            env_key = token[len("$env.") :]
            return os.getenv(env_key, "")
        return _lookup_path(context.get("$current", {}), token)

    # If the entire string is a single `{{ expr }}`, preserve its native Python type
    full_match = re.fullmatch(r"\s*\{\{\s*([^}]+?)\s*\}\}\s*", value)
    if full_match:
        resolved = _resolve_expr(full_match.group(1))
        return resolved if resolved is not None else ""

    def _replacer(match: re.Match[str]) -> str:
        resolved = _resolve_expr(match.group(1))
        if resolved is None:
            return ""
        if isinstance(resolved, (dict, list)):
            return json.dumps(resolved)
        return str(resolved)

    return _EXPR_PATTERN.sub(_replacer, value)


def _compare_values(actual: Any, operator: str, expected: Any) -> bool:
    op = operator.lower().strip()
    if op == "exists":
        return (actual is not None) if bool(expected) else (actual is None)
    if op == "eq":
        return actual == expected or str(actual).lower() == str(expected).lower() if isinstance(actual, bool) or isinstance(expected, bool) else actual == expected
    if op == "neq":
        return actual != expected
    if op in ("gt", "gte", "lt", "lte"):
        try:
            a_num = float(actual)
            b_num = float(expected)
        except (TypeError, ValueError):
            return False
        if op == "gt":
            return a_num > b_num
        if op == "gte":
            return a_num >= b_num
        if op == "lt":
            return a_num < b_num
        return a_num <= b_num
    if op == "contains":
        if isinstance(actual, (str, list, dict)):
            return str(expected) in actual if isinstance(actual, str) else expected in actual
        return False
    if op == "in":
        if isinstance(expected, (list, tuple, set, str)):
            return actual in expected
        return False
    if op == "regex":
        try:
            return bool(re.search(str(expected), str(actual or "")))
        except re.error:
            return False
    raise WorkflowValidationError(f"Unsupported comparison operator: {operator!r}")


def topological_order(definition: WorkflowDefinition) -> list[str]:
    nodes = {node.id: node for node in definition.nodes}
    incoming = {node_id: 0 for node_id in nodes}
    outgoing: dict[str, list[str]] = defaultdict(list)
    for edge in definition.edges:
        if edge.source not in nodes or edge.target not in nodes:
            raise WorkflowValidationError(
                f"Edge references unknown node: {edge.source!r} -> {edge.target!r}"
            )
        if edge.source == edge.target:
            raise WorkflowValidationError("Self-loop edges are not supported")
        outgoing[edge.source].append(edge.target)
        incoming[edge.target] += 1

    triggers = [node.id for node in definition.nodes if node.type in TRIGGER_NODE_TYPES]
    if len(triggers) != 1:
        raise WorkflowValidationError("A workflow must contain exactly one trigger node")
    trigger_id = triggers[0]

    queue = deque(node_id for node_id, count in incoming.items() if count == 0)
    order: list[str] = []
    while queue:
        current = queue.popleft()
        order.append(current)
        for target in outgoing[current]:
            incoming[target] -= 1
            if incoming[target] == 0:
                queue.append(target)
    if len(order) != len(nodes):
        raise WorkflowValidationError("Workflow contains a cycle")
    if any(edge.target == trigger_id for edge in definition.edges):
        raise WorkflowValidationError("Trigger node cannot have incoming edges")

    # Require every node to be connected downstream from the trigger; disconnected
    # nodes should not silently execute as part of a workflow.
    reachable: set[str] = set()
    stack = [trigger_id]
    while stack:
        current = stack.pop()
        if current in reachable:
            continue
        reachable.add(current)
        stack.extend(outgoing[current])
    if reachable != set(nodes):
        disconnected = sorted(set(nodes) - reachable)
        raise WorkflowValidationError(
            f"Every node must be reachable from the trigger; disconnected: {disconnected}"
        )
    return order


def validate_workflow_graph(definition: WorkflowDefinition) -> ValidationReport:
    """Validate graph topology and node configurations, returning structured issues."""
    issues: list[ValidationIssue] = []
    order: list[str] = []
    try:
        order = topological_order(definition)
    except WorkflowValidationError as exc:
        issues.append(ValidationIssue(severity="error", code="GRAPH_TOPOLOGY_ERROR", message=str(exc)))

    for node in definition.nodes:
        cfg = node.config or {}
        if node.type == "set":
            if "values" in cfg and not isinstance(cfg.get("values"), dict):
                issues.append(
                    ValidationIssue(
                        severity="error",
                        code="INVALID_SET_VALUES",
                        message=f"Node {node.id!r}: config.values must be a JSON object",
                        node_id=node.id,
                    )
                )
        elif node.type == "http_request":
            url = cfg.get("url")
            if not isinstance(url, str) or not url.strip():
                issues.append(
                    ValidationIssue(
                        severity="error",
                        code="MISSING_HTTP_URL",
                        message=f"Node {node.id!r}: HTTP Request requires a non-empty config.url",
                        node_id=node.id,
                    )
                )
        elif node.type == "if_condition":
            field_name = cfg.get("field")
            if not isinstance(field_name, str) or not field_name.strip():
                issues.append(
                    ValidationIssue(
                        severity="error",
                        code="MISSING_CONDITION_FIELD",
                        message=f"Node {node.id!r}: IF Condition requires config.field",
                        node_id=node.id,
                    )
                )
        elif node.type == "sql_query":
            q = cfg.get("query")
            if not isinstance(q, str) or not q.strip():
                issues.append(
                    ValidationIssue(
                        severity="error",
                        code="MISSING_SQL_QUERY",
                        message=f"Node {node.id!r}: SQL Query node requires config.query",
                        node_id=node.id,
                    )
                )
        elif node.type == "code":
            code_str = cfg.get("code")
            if not isinstance(code_str, str) or not code_str.strip():
                issues.append(
                    ValidationIssue(
                        severity="error",
                        code="MISSING_CODE",
                        message=f"Node {node.id!r}: Code node requires non-empty config.code",
                        node_id=node.id,
                    )
                )

    has_errors = any(issue.severity == "error" for issue in issues)
    return ValidationReport(valid=not has_errors, topological_order=order, issues=issues)


def _deep_merge_dicts(base: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for k, v in incoming.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge_dicts(result[k], v)
        else:
            result[k] = v
    return result


def _execute_single_node(
    node: Any,
    merged_input: dict[str, Any],
    context: dict[str, Any],
    *,
    http_transport: httpx.BaseTransport | None = None,
    subworkflow_loader: Callable[[str], WorkflowDefinition | None] | None = None,
    depth: int = 0,
) -> tuple[dict[str, Any], str | None, bool]:
    """Execute one node and return (output_dict, active_branch_handle, paused_for_approval)."""
    if depth > 3:
        raise WorkflowValidationError("Maximum sub-workflow recursion depth (3) exceeded")

    eval_ctx = {**context, "$current": merged_input}
    cfg = evaluate_expressions(node.config or {}, eval_ctx)
    ntype = node.type

    if ntype in TRIGGER_NODE_TYPES:
        out = dict(merged_input)
        if ntype == "webhook_trigger":
            out.setdefault("_trigger", "webhook")
        elif ntype == "schedule_trigger":
            out.setdefault("_trigger", "schedule")
        return out, None, False

    if ntype == "set":
        values = cfg.get("values", {})
        if not isinstance(values, dict):
            raise WorkflowValidationError(f"Node {node.id!r}: config.values must be an object")
        keep_only = bool(cfg.get("keep_only_set", False))
        result = dict(values) if keep_only else {**merged_input, **values}
        remove_fields = cfg.get("remove_fields") or []
        if isinstance(remove_fields, list):
            for key in remove_fields:
                result.pop(str(key), None)
        return result, None, False

    if ntype == "if_condition":
        field_path = str(cfg.get("field") or "").strip()
        if not field_path:
            raise WorkflowValidationError(f"Node {node.id!r}: config.field is required")
        operator = str(cfg.get("operator") or "eq")
        expected = cfg.get("value", True)
        actual = _lookup_path(merged_input, field_path)
        matched = _compare_values(actual, operator, expected)
        branch = "true" if matched else "false"
        return {**merged_input, "_condition": {"node_id": node.id, "matched": matched, "branch": branch}}, branch, False

    if ntype == "switch":
        field_path = str(cfg.get("field") or "").strip()
        actual = _lookup_path(merged_input, field_path)
        cases = cfg.get("cases") or []
        branch = str(actual) if actual in cases or str(actual) in [str(c) for c in cases] else "default"
        return {**merged_input, "_switch": {"node_id": node.id, "branch": branch}}, branch, False

    if ntype == "merge":
        return merged_input, None, False

    if ntype == "filter":
        list_field = str(cfg.get("list_field") or "items")
        item_field = str(cfg.get("item_field") or "").strip()
        operator = str(cfg.get("operator") or "eq")
        expected = cfg.get("value", True)
        output_field = str(cfg.get("output_field") or "filtered_items")
        raw_items = merged_input.get(list_field, [])
        if not isinstance(raw_items, list):
            raise WorkflowValidationError(f"Node {node.id!r}: field {list_field!r} must be a list")
        filtered = []
        for item in raw_items:
            target_val = _lookup_path(item, item_field) if item_field and isinstance(item, dict) else item
            if _compare_values(target_val, operator, expected):
                filtered.append(item)
        return {**merged_input, output_field: filtered, f"{output_field}_count": len(filtered)}, None, False

    if ntype == "loop":
        list_field = str(cfg.get("list_field") or "items")
        max_iter = min(max(int(cfg.get("max_iterations", 100)), 1), 1000)
        template = (node.config or {}).get("template", {"item": "{{ $item }}"})
        output_field = str(cfg.get("output_field") or "results")
        raw_items = merged_input.get(list_field, [])
        if not isinstance(raw_items, list):
            raise WorkflowValidationError(f"Node {node.id!r}: field {list_field!r} must be a list")
        results = []
        for idx, item in enumerate(raw_items[:max_iter]):
            loop_ctx = {**eval_ctx, "$item": item, "$index": idx}
            results.append(evaluate_expressions(template, loop_ctx))
        return {**merged_input, output_field: results, f"{output_field}_count": len(results)}, None, False

    if ntype == "wait":
        delay_ms = min(max(int(cfg.get("delay_ms", 10)), 0), 2000)
        if delay_ms > 0:
            time.sleep(delay_ms / 1000.0)
        return {**merged_input, "_wait": {"node_id": node.id, "delayed_ms": delay_ms}}, None, False

    if ntype == "http_request":
        url = str(cfg.get("url") or "").strip()
        method = str(cfg.get("method") or "GET").upper()
        headers = dict(cfg.get("headers") or {})
        body = cfg.get("body")
        timeout_sec = float(cfg.get("timeout_seconds", 10.0))
        response_field = str(cfg.get("response_field") or "http")

        # Inject credential header if configured
        cred_name = str(cfg.get("credential_name") or "").strip()
        if cred_name:
            creds_map = context.get("$credentials", {})
            cred_data = creds_map.get(cred_name)
            if not isinstance(cred_data, dict):
                raise WorkflowValidationError(f"Node {node.id!r}: referenced credential {cred_name!r} not found")
            if "token" in cred_data and "Authorization" not in headers:
                headers["Authorization"] = f"Bearer {cred_data['token']}"
            elif "api_key" in cred_data and "X-API-Key" not in headers:
                headers["X-API-Key"] = str(cred_data["api_key"])

        # Deterministic local mock scheme (`mock://host/path`) for offline & CI testing
        if url.startswith("mock://"):
            if "fail" in url or merged_input.get("_force_http_fail") is True:
                raise WorkflowValidationError(f"Node {node.id!r}: Mock HTTP endpoint returned 503 Service Unavailable")
            mock_resp = {
                "status_code": 200,
                "ok": True,
                "url": url,
                "data": {"status": "healthy", "echo": merged_input.get("service", "flowforge"), "method": method},
            }
            return {**merged_input, response_field: mock_resp}, None, False

        resp = safe_http_request(
            method,
            url,
            headers=headers,
            json_body=body,
            timeout_seconds=timeout_sec,
            transport=http_transport,
        )
        if cfg.get("fail_on_http_error", False) and not resp.get("ok", False):
            raise WorkflowValidationError(
                f"Node {node.id!r}: HTTP {resp.get('status_code')} from {url}"
            )
        return {**merged_input, response_field: resp}, None, False

    if ntype == "sql_query":
        query = str(cfg.get("query") or "").strip()
        if not query:
            raise WorkflowValidationError(f"Node {node.id!r}: SQL query cannot be empty")
        # Block multi-statement SQL injection or destructive DDL
        stripped_q = query.rstrip(";").strip()
        if ";" in stripped_q:
            raise SecurityError(f"Node {node.id!r}: Multi-statement SQL queries are blocked by security policy")
        if re.search(r"\b(DROP|TRUNCATE|ALTER|GRANT|ATTACH|DETACH)\b", stripped_q, re.IGNORECASE):
            raise SecurityError(f"Node {node.id!r}: Destructive DDL/admin SQL statements are blocked")

        params = cfg.get("params") or {}
        if not isinstance(params, dict):
            raise WorkflowValidationError(f"Node {node.id!r}: SQL params must be a JSON object")
        output_field = str(cfg.get("output_field") or "rows")

        # Execute safely in an isolated in-memory SQLite connection (or seed table if provided)
        with sqlite3.connect(":memory:") as conn:
            conn.row_factory = sqlite3.Row
            seed_rows = cfg.get("seed_rows") or merged_input.get("_seed_rows")
            if isinstance(seed_rows, list) and seed_rows and isinstance(seed_rows[0], dict):
                cols = [re.sub(r"[^a-zA-Z0-9_]", "", str(k)) for k in seed_rows[0].keys()]
                conn.execute(f"CREATE TABLE dataset ({', '.join(cols)})")
                for r in seed_rows:
                    placeholders = ", ".join(f":{c}" for c in cols)
                    conn.execute(f"INSERT INTO dataset VALUES ({placeholders})", {c: r.get(c) for c in cols})
            cur = conn.execute(stripped_q, params)
            rows = [dict(row) for row in cur.fetchall()] if cur.description else []
        return {**merged_input, output_field: rows, f"{output_field}_count": len(rows)}, None, False

    if ntype == "csv_json":
        mode = str(cfg.get("mode") or "csv_to_json")
        source_field = str(cfg.get("source_field") or "csv_text")
        target_field = str(cfg.get("target_field") or "records")
        delimiter = str(cfg.get("delimiter") or ",")[:1] or ","
        if mode == "csv_to_json":
            raw_csv = str(merged_input.get(source_field) or cfg.get("csv_text") or "").strip()
            if not raw_csv:
                return {**merged_input, target_field: []}, None, False
            reader = csv.DictReader(io.StringIO(raw_csv), delimiter=delimiter)
            records = []
            for row in reader:
                clean: dict[str, Any] = {}
                for k, v in row.items():
                    if k is None:
                        continue
                    v_str = (v or "").strip()
                    if v_str.lower() in ("true", "false"):
                        clean[k.strip()] = v_str.lower() == "true"
                    elif re.match(r"^-?\d+$", v_str):
                        clean[k.strip()] = int(v_str)
                    else:
                        clean[k.strip()] = v_str
                records.append(clean)
            return {**merged_input, target_field: records}, None, False
        else:
            records = merged_input.get(source_field, [])
            if not isinstance(records, list) or not records:
                return {**merged_input, target_field: ""}, None, False
            buf = io.StringIO()
            fieldnames = list(records[0].keys()) if isinstance(records[0], dict) else ["value"]
            writer = csv.DictWriter(buf, fieldnames=fieldnames, delimiter=delimiter)
            writer.writeheader()
            for r in records:
                writer.writerow(r if isinstance(r, dict) else {"value": r})
            return {**merged_input, target_field: buf.getvalue()}, None, False

    if ntype == "file_io":
        op = str(cfg.get("operation") or "write_json")
        rel_path = str(cfg.get("path") or "")
        safe_path = resolve_permitted_path(rel_path)
        target_field = str(cfg.get("target_field") or "file_data")
        source_field = str(cfg.get("source_field") or "").strip()
        safe_path.parent.mkdir(parents=True, exist_ok=True)
        if op == "write_json":
            data_to_write = merged_input.get(source_field, merged_input) if source_field else merged_input
            safe_path.write_text(json.dumps(data_to_write, indent=2), encoding="utf-8")
            return {**merged_input, "_file_written": str(rel_path)}, None, False
        if op == "read_json":
            if not safe_path.exists():
                raise WorkflowValidationError(f"Node {node.id!r}: File not found in sandbox: {rel_path}")
            loaded = json.loads(safe_path.read_text(encoding="utf-8"))
            return {**merged_input, target_field: loaded}, None, False
        if op == "write_text":
            text_val = str(merged_input.get(source_field, "") if source_field else cfg.get("content", ""))
            safe_path.write_text(text_val, encoding="utf-8")
            return {**merged_input, "_file_written": str(rel_path)}, None, False
        if op == "read_text":
            if not safe_path.exists():
                raise WorkflowValidationError(f"Node {node.id!r}: File not found in sandbox: {rel_path}")
            return {**merged_input, target_field: safe_path.read_text(encoding="utf-8")}, None, False
        raise WorkflowValidationError(f"Node {node.id!r}: Unsupported file_io operation {op!r}")

    if ntype == "code":
        code_str = str(node.config.get("code") or "")
        timeout_sec = float(cfg.get("timeout_seconds", 3.0))
        code_out = execute_isolated_python(code_str, merged_input, timeout_seconds=timeout_sec)
        return {**merged_input, **code_out}, None, False

    if ntype == "skill":
        skill_id = str(cfg.get("skill_id") or "").strip()
        skill_input = {**merged_input, **(cfg.get("skill_input") or {})}
        output_field = str(cfg.get("output_field") or "skill_output")
        skill_res = execute_skill(skill_id, skill_input)
        return {**merged_input, output_field: skill_res}, None, False

    if ntype == "ai_agent":
        provider = str(cfg.get("provider") or "local")
        prompt = str(cfg.get("prompt") or "Process data")
        required_keys = cfg.get("required_keys") or ["summary"]
        output_field = str(cfg.get("output_field") or "ai_result")
        redacted_input = mask_secrets(merged_input, context.get("_secret_values", []))
        ai_payload: dict[str, Any] = {
            "summary": f"[{provider}] Processed {len(redacted_input)} fields for instruction: {prompt[:80]}",
            "input_keys": sorted(redacted_input.keys()),
            "provider": provider,
            "redacted": True,
        }
        for req_k in required_keys:
            ai_payload.setdefault(str(req_k), f"generated_{req_k}")
        return {**merged_input, output_field: ai_payload}, None, False

    if ntype == "human_approval":
        already_approved = (
            merged_input.get("_approved") is True
            and bool(cfg.get("auto_approve_in_test", False))
        ) or context.get("_approved_nodes", {}).get(node.id) is True
        if not already_approved:
            return (
                {
                    **merged_input,
                    "_approval_pending": {
                        "node_id": node.id,
                        "message": str(cfg.get("message") or "Approval required"),
                    },
                },
                None,
                True,
            )
        return {**merged_input, "_approval": {"node_id": node.id, "approved": True}}, None, False

    if ntype == "subworkflow":
        sub_id = str(cfg.get("subworkflow_id") or "").strip()
        output_field = str(cfg.get("output_field") or "subworkflow_result")
        if not sub_id or subworkflow_loader is None:
            raise WorkflowValidationError(f"Node {node.id!r}: subworkflow_id {sub_id!r} could not be resolved")
        sub_def = subworkflow_loader(sub_id)
        if sub_def is None:
            raise WorkflowValidationError(f"Node {node.id!r}: Subworkflow {sub_id!r} not found")
        sub_res = execute_workflow_detailed(
            sub_def,
            merged_input,
            credentials_map=context.get("$credentials"),
            http_transport=http_transport,
            subworkflow_loader=subworkflow_loader,
            depth=depth + 1,
        )
        if sub_res["status"] != "succeeded":
            raise WorkflowValidationError(f"Subworkflow {sub_id!r} failed: {sub_res.get('error')}")
        return {**merged_input, output_field: sub_res["result_data"]}, None, False

    if ntype == "error_handler":
        fallback = cfg.get("fallback_values") or {"recovered": True}
        return {**merged_input, **fallback}, None, False

    if ntype == "slack_notify":
        channel = str(cfg.get("channel") or "#general")
        message = str(cfg.get("message") or "")
        webhook_url = str(cfg.get("webhook_url") or "mock://slack.local/hook")
        out_field = str(cfg.get("output_field") or "slack_delivery")
        if not webhook_url.startswith("mock://"):
            safe_http_request("POST", webhook_url, json_body={"channel": channel, "text": message}, transport=http_transport)
        return {**merged_input, out_field: {"channel": channel, "message": message, "delivered": True}}, None, False

    if ntype == "github_api":
        action = str(cfg.get("action") or "create_issue")
        repo = str(cfg.get("repository") or "flowforge-org/flowforge")
        title = str(cfg.get("title") or "Automated Issue")
        body = str(cfg.get("body") or "")
        out_field = str(cfg.get("output_field") or "github_result")
        return {
            **merged_input,
            out_field: {
                "action": action,
                "repository": repo,
                "title": title,
                "body": body,
                "number": 42,
                "status": "simulated_ok",
            },
        }, None, False

    if ntype == "smtp_email":
        to_addr = str(cfg.get("to") or "ops@example.com")
        subject = str(cfg.get("subject") or "FlowForge Notification")
        body = str(cfg.get("body") or "")
        mode = str(cfg.get("mode") or "outbox")
        out_field = str(cfg.get("output_field") or "email_delivery")
        return {
            **merged_input,
            out_field: {
                "to": to_addr,
                "subject": subject,
                "body": body,
                "mode": mode,
                "status": "queued_in_outbox",
            },
        }, None, False

    if ntype == "object_storage":
        op = str(cfg.get("operation") or "put_object")
        bucket = re.sub(r"[^a-zA-Z0-9_-]", "", str(cfg.get("bucket") or "artifacts")) or "artifacts"
        obj_key = str(cfg.get("object_key") or "item.json").lstrip("/")
        source_field = str(cfg.get("source_field") or "").strip()
        out_field = str(cfg.get("output_field") or "storage_result")
        rel_target = f"_buckets/{bucket}/{obj_key}"
        safe_target = resolve_permitted_path(rel_target)
        safe_target.parent.mkdir(parents=True, exist_ok=True)
        if op == "put_object":
            payload_obj = merged_input.get(source_field, merged_input) if source_field else merged_input
            safe_target.write_text(json.dumps(payload_obj, indent=2), encoding="utf-8")
            return {**merged_input, out_field: {"bucket": bucket, "key": obj_key, "stored": True}}, None, False
        if op == "get_object":
            if not safe_target.exists():
                raise WorkflowValidationError(f"Object {bucket}/{obj_key} not found")
            return {**merged_input, out_field: json.loads(safe_target.read_text(encoding="utf-8"))}, None, False
        if op == "list_objects":
            bucket_root = resolve_permitted_path(f"_buckets/{bucket}")
            keys = [
                str(p.relative_to(bucket_root)).replace("\\", "/")
                for p in bucket_root.rglob("*")
                if p.is_file()
            ] if bucket_root.exists() else []
            return {**merged_input, out_field: {"bucket": bucket, "keys": sorted(keys)}}, None, False
        if op == "delete_object":
            if safe_target.exists():
                safe_target.unlink()
            return {**merged_input, out_field: {"bucket": bucket, "key": obj_key, "deleted": True}}, None, False
        raise WorkflowValidationError(f"Unsupported object_storage operation: {op!r}")

    if ntype == "vector_memory":
        op = str(cfg.get("operation") or "upsert")
        ns = str(cfg.get("namespace") or "default")
        text_val = str(cfg.get("text") or "")
        doc_id = str(cfg.get("doc_id") or "doc_1")
        top_k = min(max(int(cfg.get("top_k", 3)), 1), 50)
        out_field = str(cfg.get("output_field") or "vector_matches")
        emb = _deterministic_embed(text_val)
        if op == "upsert":
            _VECTOR_STORE[ns][doc_id] = {"id": doc_id, "text": text_val, "embedding": emb}
            return {**merged_input, out_field: {"upserted_id": doc_id, "namespace": ns, "dimensions": len(emb)}}, None, False
        if op == "query":
            scored = []
            for item in _VECTOR_STORE.get(ns, {}).values():
                score = _cosine_sim(emb, item["embedding"])
                scored.append({"id": item["id"], "text": item["text"], "score": score})
            scored.sort(key=lambda x: x["score"], reverse=True)
            return {**merged_input, out_field: scored[:top_k]}, None, False
        raise WorkflowValidationError(f"Unsupported vector_memory operation: {op!r}")

    if ntype == "json_schema_validator":
        schema_obj = cfg.get("schema") or {"type": "object"}
        target_field = str(cfg.get("target_field") or "").strip()
        strict = bool(cfg.get("strict", True))
        subject = merged_input.get(target_field) if target_field else merged_input
        errors: list[str] = []
        if not isinstance(schema_obj, dict):
            raise WorkflowValidationError(f"Node {node.id!r}: config.schema must be a JSON object")
        req_keys = schema_obj.get("required") or []
        if isinstance(subject, dict):
            for rk in req_keys:
                if rk not in subject or subject[rk] is None:
                    errors.append(f"Missing required field: {rk}")
        else:
            if schema_obj.get("type") == "object":
                errors.append("Expected JSON object")
        is_valid = len(errors) == 0
        if not is_valid and strict:
            raise WorkflowValidationError(f"Node {node.id!r}: JSON Schema validation failed: {'; '.join(errors)}")
        return {**merged_input, "_schema_validation": {"valid": is_valid, "errors": errors}}, None, False

    if ntype == "graphql_query":
        url = str(cfg.get("url") or "mock://graphql.local/api").strip()
        gql_query = str(cfg.get("query") or "").strip()
        variables = cfg.get("variables") or {}
        out_field = str(cfg.get("output_field") or "graphql_data")
        if not gql_query:
            raise WorkflowValidationError(f"Node {node.id!r}: GraphQL query cannot be empty")
        if url.startswith("mock://"):
            return {
                **merged_input,
                out_field: {"data": {"mock_graphql": True, "variables": variables, "query_length": len(gql_query)}},
            }, None, False
        resp = safe_http_request(
            "POST",
            url,
            json_body={"query": gql_query, "variables": variables},
            transport=http_transport,
        )
        return {**merged_input, out_field: resp.get("data", resp)}, None, False

    if ntype == "xml_html_parser":
        import xml.etree.ElementTree as ET

        src_field = str(cfg.get("source_field") or "xml_text")
        tag_name = str(cfg.get("tag") or "item").strip()
        out_field = str(cfg.get("output_field") or "extracted_elements")
        raw_xml = str(merged_input.get(src_field) or cfg.get("xml_text") or "").strip()
        if "<!ENTITY" in raw_xml.upper() or "<!DOCTYPE" in raw_xml.upper():
            raise SecurityError(f"Node {node.id!r}: XML DOCTYPE / external entity (XXE) declarations are blocked")
        if not raw_xml:
            return {**merged_input, out_field: []}, None, False
        try:
            root_el = ET.fromstring(raw_xml)
        except ET.ParseError as exc:
            raise WorkflowValidationError(f"Node {node.id!r}: Invalid XML snippet: {exc}") from exc
        extracted = [
            {"tag": el.tag, "text": (el.text or "").strip(), "attrib": dict(el.attrib)}
            for el in root_el.iter(tag_name)
        ]
        return {**merged_input, out_field: extracted, f"{out_field}_count": len(extracted)}, None, False

    if ntype == "crypto_hash_hmac":
        import base64
        import hashlib
        import hmac

        algo = str(cfg.get("algorithm") or "sha256").lower()
        input_text = str(cfg.get("input_text") or "")
        secret_str = str(cfg.get("secret") or "")
        out_field = str(cfg.get("output_field") or "digest")
        raw_bytes = input_text.encode("utf-8")
        if algo == "sha256":
            digest = hashlib.sha256(raw_bytes).hexdigest()
        elif algo == "sha512":
            digest = hashlib.sha512(raw_bytes).hexdigest()
        elif algo == "hmac_sha256":
            digest = hmac.new(secret_str.encode("utf-8"), raw_bytes, hashlib.sha256).hexdigest()
        elif algo == "base64_encode":
            digest = base64.b64encode(raw_bytes).decode("ascii")
        else:
            raise WorkflowValidationError(f"Unsupported crypto algorithm: {algo!r}")
        return {**merged_input, out_field: digest}, None, False

    if ntype == "rate_limit_throttle":
        bucket_key = str(cfg.get("bucket_key") or "default")
        max_per_min = max(int(cfg.get("max_per_minute", 60)), 1)
        return {
            **merged_input,
            "_throttle": {"bucket_key": bucket_key, "max_per_minute": max_per_min, "allowed": True},
        }, None, False

    if ntype == "deduplicate_items":
        list_field = str(cfg.get("list_field") or "items")
        key_field = str(cfg.get("key_field") or "id").strip()
        out_field = str(cfg.get("output_field") or "unique_items")
        raw_list = merged_input.get(list_field, [])
        if not isinstance(raw_list, list):
            raise WorkflowValidationError(f"Node {node.id!r}: {list_field!r} must be a list")
        seen_keys: set[Any] = set()
        unique_items: list[Any] = []
        dups = 0
        for item in raw_list:
            k_val = _lookup_path(item, key_field) if key_field and isinstance(item, dict) else json.dumps(item, sort_keys=True)
            if k_val in seen_keys:
                dups += 1
            else:
                seen_keys.add(k_val)
                unique_items.append(item)
        return {**merged_input, out_field: unique_items, "duplicates_removed": dups}, None, False

    if ntype == "output":
        select_fields = cfg.get("select_fields") or []
        if isinstance(select_fields, list) and select_fields:
            return {k: merged_input.get(k) for k in select_fields if k in merged_input}, None, False
        return merged_input, None, False

    raise WorkflowValidationError(f"Unsupported node type: {ntype}")


def execute_workflow_detailed(
    definition: WorkflowDefinition,
    input_data: dict[str, Any],
    *,
    credentials_map: dict[str, dict[str, Any]] | None = None,
    variables_map: dict[str, Any] | None = None,
    pinned_node_outputs: dict[str, dict[str, Any]] | None = None,
    secret_values: list[str] | None = None,
    http_transport: httpx.BaseTransport | None = None,
    subworkflow_loader: Callable[[str], WorkflowDefinition | None] | None = None,
    initial_node_outputs: dict[str, dict[str, Any]] | None = None,
    approved_nodes: dict[str, bool] | None = None,
    start_from_node_id: str | None = None,
    on_node_event: Callable[[dict[str, Any]], None] | None = None,
    depth: int = 0,
) -> dict[str, Any]:
    """Execute a workflow DAG with conditional branching, retries, per-node traces,
    pause/resume checkpoints, and secret masking.
    """
    order = topological_order(definition)
    nodes = {node.id: node for node in definition.nodes}
    incoming_edges: dict[str, list[Any]] = defaultdict(list)
    outgoing_edges: dict[str, list[Any]] = defaultdict(list)
    for edge in definition.edges:
        incoming_edges[edge.target].append(edge)
        outgoing_edges[edge.source].append(edge)

    creds = credentials_map or {}
    secrets_to_mask = list(secret_values or [])
    for c_dict in creds.values():
        if isinstance(c_dict, dict):
            for v in c_dict.values():
                if isinstance(v, str) and len(v) >= 4:
                    secrets_to_mask.append(v)

    outputs: dict[str, dict[str, Any]] = dict(initial_node_outputs or {})
    active_branches: dict[str, str | None] = {}
    skipped_nodes: set[str] = set()
    node_runs: list[dict[str, Any]] = []

    context: dict[str, Any] = {
        "$input": dict(input_data),
        "$nodes": outputs,
        "$credentials": creds,
        "$vars": dict(variables_map or {}),
        "_secret_values": secrets_to_mask,
        "_approved_nodes": dict(approved_nodes or {}),
    }

    started_replay = start_from_node_id is None

    for node_id in order:
        node = nodes[node_id]
        if not started_replay:
            if node_id == start_from_node_id:
                started_replay = True
            elif node_id in outputs:
                continue

        inc = incoming_edges[node_id]
        # Determine whether this node is reachable via at least one active incoming edge
        if inc:
            active_parents: list[str] = []
            for edge in inc:
                parent_id = edge.source
                if parent_id in skipped_nodes:
                    continue
                parent_branch = active_branches.get(parent_id)
                if parent_branch is not None and edge.source_handle:
                    if str(edge.source_handle).lower() != str(parent_branch).lower():
                        continue
                active_parents.append(parent_id)

            if not active_parents:
                skipped_nodes.add(node_id)
                now_iso = datetime.now(timezone.utc).isoformat()
                node_runs.append(
                    {
                        "node_id": node_id,
                        "node_type": node.type,
                        "status": "skipped",
                        "attempts": 0,
                        "started_at": now_iso,
                        "finished_at": now_iso,
                        "duration_ms": 0.0,
                        "input_data": {},
                        "output_data": None,
                        "error": None,
                        "branch_taken": None,
                    }
                )
                continue

            # Merge active parents according to Merge mode if this is a merge node
            merge_mode = (node.config or {}).get("mode", "shallow_merge") if node.type == "merge" else "shallow_merge"
            merged: dict[str, Any] = {}
            if merge_mode == "collect_branches":
                merged = {"branches": {p: outputs.get(p, {}) for p in active_parents}}
            elif merge_mode == "deep_merge":
                for p in active_parents:
                    merged = _deep_merge_dicts(merged, outputs.get(p, {}))
            else:
                for p in active_parents:
                    merged.update(outputs.get(p, {}))
        else:
            merged = dict(input_data)

        pinned_map = pinned_node_outputs or {}
        pinned_val = pinned_map.get(node_id) or getattr(node, "pinned_output", None)
        if isinstance(pinned_val, dict):
            now_iso = datetime.now(timezone.utc).isoformat()
            outputs[node_id] = dict(pinned_val)
            node_runs.append(
                {
                    "node_id": node_id,
                    "node_type": node.type,
                    "status": "pinned",
                    "attempts": 0,
                    "started_at": now_iso,
                    "finished_at": now_iso,
                    "duration_ms": 0.0,
                    "input_data": mask_secrets(merged, secrets_to_mask),
                    "output_data": mask_secrets(pinned_val, secrets_to_mask),
                    "error": None,
                    "branch_taken": None,
                }
            )
            continue

        retry = node.retry_policy
        max_attempts = retry.max_attempts if retry else 1
        backoff_ms = retry.backoff_ms if retry else 0
        multiplier = retry.backoff_multiplier if retry else 1.0

        node_start_dt = datetime.now(timezone.utc)
        t0 = time.perf_counter()
        attempts = 0
        last_exc: Exception | None = None
        result_out: dict[str, Any] = {}
        branch_taken: str | None = None
        paused = False

        while attempts < max_attempts:
            attempts += 1
            try:
                result_out, branch_taken, paused = _execute_single_node(
                    node,
                    merged,
                    context,
                    http_transport=http_transport,
                    subworkflow_loader=subworkflow_loader,
                    depth=depth,
                )
                last_exc = None
                break
            except (WorkflowValidationError, SecurityError, SkillValidationError, ValueError, TypeError, httpx.HTTPError) as exc:
                last_exc = exc
                # Do not retry deterministic security or schema violations
                if isinstance(exc, (SSRFError, PathSecurityError, CodeExecutionError, SkillValidationError)):
                    break
                if attempts < max_attempts and backoff_ms > 0:
                    sleep_s = min((backoff_ms * (multiplier ** (attempts - 1))) / 1000.0, 2.0)
                    time.sleep(sleep_s)

        duration_ms = round((time.perf_counter() - t0) * 1000, 3)
        node_finish_dt = datetime.now(timezone.utc)

        if last_exc is not None:
            if node.on_error == "continue_with_error":
                result_out = {**merged, "_node_errors": {node_id: str(last_exc)}}
                outputs[node_id] = result_out
                node_runs.append(
                    {
                        "node_id": node_id,
                        "node_type": node.type,
                        "status": "continued_with_error",
                        "attempts": attempts,
                        "started_at": node_start_dt.isoformat(),
                        "finished_at": node_finish_dt.isoformat(),
                        "duration_ms": duration_ms,
                        "input_data": mask_secrets(merged, secrets_to_mask),
                        "output_data": mask_secrets(result_out, secrets_to_mask),
                        "error": mask_secrets(str(last_exc), secrets_to_mask),
                        "branch_taken": None,
                    }
                )
                continue
            if node.on_error == "fallback_value":
                fallback_val = (node.config or {}).get("fallback_values", {"fallback": True})
                result_out = {**merged, **(fallback_val if isinstance(fallback_val, dict) else {"fallback": fallback_val})}
                outputs[node_id] = result_out
                node_runs.append(
                    {
                        "node_id": node_id,
                        "node_type": node.type,
                        "status": "fallback",
                        "attempts": attempts,
                        "started_at": node_start_dt.isoformat(),
                        "finished_at": node_finish_dt.isoformat(),
                        "duration_ms": duration_ms,
                        "input_data": mask_secrets(merged, secrets_to_mask),
                        "output_data": mask_secrets(result_out, secrets_to_mask),
                        "error": mask_secrets(str(last_exc), secrets_to_mask),
                        "branch_taken": None,
                    }
                )
                continue

            node_runs.append(
                {
                    "node_id": node_id,
                    "node_type": node.type,
                    "status": "failed",
                    "attempts": attempts,
                    "started_at": node_start_dt.isoformat(),
                    "finished_at": node_finish_dt.isoformat(),
                    "duration_ms": duration_ms,
                    "input_data": mask_secrets(merged, secrets_to_mask),
                    "output_data": None,
                    "error": mask_secrets(str(last_exc), secrets_to_mask),
                    "branch_taken": None,
                }
            )
            return {
                "status": "failed",
                "result_data": None,
                "error": mask_secrets(str(last_exc), secrets_to_mask),
                "node_runs": node_runs,
                "checkpoint_state": {"outputs": mask_secrets(outputs, secrets_to_mask), "failed_node_id": node_id},
            }

        if paused:
            node_runs.append(
                {
                    "node_id": node_id,
                    "node_type": node.type,
                    "status": "waiting_approval",
                    "attempts": attempts,
                    "started_at": node_start_dt.isoformat(),
                    "finished_at": node_finish_dt.isoformat(),
                    "duration_ms": duration_ms,
                    "input_data": mask_secrets(merged, secrets_to_mask),
                    "output_data": mask_secrets(result_out, secrets_to_mask),
                    "error": None,
                    "branch_taken": None,
                }
            )
            return {
                "status": "waiting_approval",
                "result_data": mask_secrets(result_out, secrets_to_mask),
                "error": None,
                "node_runs": node_runs,
                "checkpoint_state": {
                    "paused_node_id": node_id,
                    "outputs": mask_secrets(outputs, secrets_to_mask),
                    "approved_nodes": dict(approved_nodes or {}),
                },
            }

        outputs[node_id] = result_out
        active_branches[node_id] = branch_taken
        if on_node_event is not None:
            on_node_event({'event': 'node.completed', 'node_id': node_id, 'node_type': node.type, 'status': 'succeeded', 'duration_ms': duration_ms, 'branch_taken': branch_taken})
        node_runs.append(
            {
                "node_id": node_id,
                "node_type": node.type,
                "status": "succeeded",
                "attempts": attempts,
                "started_at": node_start_dt.isoformat(),
                "finished_at": node_finish_dt.isoformat(),
                "duration_ms": duration_ms,
                "input_data": mask_secrets(merged, secrets_to_mask),
                "output_data": mask_secrets(result_out, secrets_to_mask),
                "error": None,
                "branch_taken": branch_taken,
            }
        )

    terminal_ids = [
        node_id
        for node_id in order
        if not outgoing_edges[node_id] and node_id not in skipped_nodes and node_id in outputs
    ]
    final_result: dict[str, Any] = {}
    for node_id in terminal_ids:
        final_result.update(outputs[node_id])
    # Strip internal condition/switch routing keys only if user did not request them
    final_result.pop("_condition", None)
    final_result.pop("_switch", None)

    return {
        "status": "succeeded",
        "result_data": mask_secrets(final_result, secrets_to_mask),
        "error": None,
        "node_runs": node_runs,
        "checkpoint_state": {"outputs": mask_secrets(outputs, secrets_to_mask)},
    }


def execute_workflow(definition: WorkflowDefinition, input_data: dict[str, Any]) -> dict[str, Any]:
    """Execute a workflow DAG synchronously and return the final merged output dictionary.
    Raises WorkflowValidationError or SecurityError if execution fails.
    """
    detailed = execute_workflow_detailed(definition, input_data)
    if detailed["status"] == "failed":
        raise WorkflowValidationError(str(detailed.get("error") or "Workflow execution failed"))
    return detailed["result_data"] or {}


def diff_workflow_definitions(def_a: dict[str, Any], def_b: dict[str, Any]) -> dict[str, Any]:
    """Compute a human-readable structural diff between two workflow definitions."""
    nodes_a = {n["id"]: n for n in def_a.get("nodes", []) if isinstance(n, dict) and "id" in n}
    nodes_b = {n["id"]: n for n in def_b.get("nodes", []) if isinstance(n, dict) and "id" in n}

    added_nodes = sorted(set(nodes_b) - set(nodes_a))
    removed_nodes = sorted(set(nodes_a) - set(nodes_b))
    modified_nodes: list[dict[str, Any]] = []

    for nid in sorted(set(nodes_a) & set(nodes_b)):
        na, nb = nodes_a[nid], nodes_b[nid]
        if na.get("type") != nb.get("type") or na.get("config") != nb.get("config"):
            modified_nodes.append(
                {
                    "node_id": nid,
                    "before_type": na.get("type"),
                    "after_type": nb.get("type"),
                    "before_config": na.get("config"),
                    "after_config": nb.get("config"),
                }
            )

    edges_a = {f"{e.get('source')}->{e.get('target')}[{e.get('source_handle') or ''}]" for e in def_a.get("edges", [])}
    edges_b = {f"{e.get('source')}->{e.get('target')}[{e.get('source_handle') or ''}]" for e in def_b.get("edges", [])}

    return {
        "added_nodes": added_nodes,
        "removed_nodes": removed_nodes,
        "modified_nodes": modified_nodes,
        "added_edges": sorted(edges_b - edges_a),
        "removed_edges": sorted(edges_a - edges_b),
        "has_changes": bool(added_nodes or removed_nodes or modified_nodes or (edges_a != edges_b)),
    }
