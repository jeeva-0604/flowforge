"""Provider-Independent AI Assistant & Evaluation Layer for FlowForge Community."""
from __future__ import annotations

import time
from typing import Any

from .schemas import WorkflowDefinition
from .security import mask_secrets


def draft_workflow_from_prompt(prompt: str, *, provider: str = "local") -> dict[str, Any]:
    started = time.perf_counter()
    clean_prompt = prompt.strip()
    lower = clean_prompt.lower()

    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []

    if "webhook" in lower:
        trigger_id = "webhook_1"
        nodes.append(
            {
                "id": trigger_id,
                "type": "webhook_trigger",
                "position": {"x": 80.0, "y": 190.0},
                "config": {"label": "Webhook Trigger", "path_slug": "incoming-order", "require_signature": True},
            }
        )
    elif "schedule" in lower or "cron" in lower or "every " in lower or "daily" in lower:
        trigger_id = "schedule_1"
        nodes.append(
            {
                "id": trigger_id,
                "type": "schedule_trigger",
                "position": {"x": 80.0, "y": 190.0},
                "config": {"label": "Schedule Trigger", "cron_expr": "*/15 * * * *", "interval_seconds": 900},
            }
        )
    else:
        trigger_id = "trigger_1"
        nodes.append(
            {
                "id": trigger_id,
                "type": "trigger",
                "position": {"x": 80.0, "y": 190.0},
                "config": {"label": "Manual Trigger", "subtitle": "Starts workflow run"},
            }
        )

    prev_id = trigger_id
    x_cursor = 340.0

    if "http" in lower or "api" in lower or "fetch" in lower or "endpoint" in lower:
        http_id = "http_1"
        nodes.append(
            {
                "id": http_id,
                "type": "http_request",
                "position": {"x": x_cursor, "y": 190.0},
                "config": {
                    "label": "HTTP Request",
                    "method": "POST" if "post" in lower else "GET",
                    "url": "mock://api.local/v1/resource",
                    "response_field": "http_response",
                    "timeout_seconds": 10.0,
                },
                "retry_policy": {"max_attempts": 2, "backoff_ms": 200, "backoff_multiplier": 2.0},
            }
        )
        edges.append({"source": prev_id, "target": http_id})
        prev_id = http_id
        x_cursor += 260.0

    if "sql" in lower or "postgres" in lower or "database" in lower or "query" in lower:
        sql_id = "sql_1"
        nodes.append(
            {
                "id": sql_id,
                "type": "sql_query",
                "position": {"x": x_cursor, "y": 190.0},
                "config": {
                    "label": "Parameterized SQL Query",
                    "query": "SELECT :status AS status_check",
                    "params": {"status": "healthy"},
                    "output_field": "db_rows",
                },
            }
        )
        edges.append({"source": prev_id, "target": sql_id})
        prev_id = sql_id
        x_cursor += 260.0

    if "csv" in lower:
        csv_id = "csv_1"
        nodes.append(
            {
                "id": csv_id,
                "type": "csv_json",
                "position": {"x": x_cursor, "y": 190.0},
                "config": {"label": "CSV to JSON", "mode": "csv_to_json", "source_field": "csv_text", "target_field": "records"},
            }
        )
        edges.append({"source": prev_id, "target": csv_id})
        prev_id = csv_id
        x_cursor += 260.0

    if "approval" in lower or "human" in lower or "review" in lower:
        app_id = "approval_1"
        nodes.append(
            {
                "id": app_id,
                "type": "human_approval",
                "position": {"x": x_cursor, "y": 190.0},
                "config": {"label": "Human Approval", "message": "Approve before completing sensitive action", "auto_approve_in_test": True},
            }
        )
        edges.append({"source": prev_id, "target": app_id})
        prev_id = app_id
        x_cursor += 260.0

    if prev_id == trigger_id:
        set_id = "set_1"
        nodes.append(
            {
                "id": set_id,
                "type": "set",
                "position": {"x": x_cursor, "y": 190.0},
                "config": {"label": "Set Fields", "values": {"processed": True, "note": "Drafted by FlowForge Assistant"}},
            }
        )
        edges.append({"source": prev_id, "target": set_id})
        prev_id = set_id
        x_cursor += 260.0

    if "if" in lower or "condition" in lower or "branch" in lower or "check" in lower:
        if_id = "if_1"
        field_name = "http_response.ok" if any(n["type"] == "http_request" for n in nodes) else "ok"
        nodes.append(
            {
                "id": if_id,
                "type": "if_condition",
                "position": {"x": x_cursor, "y": 190.0},
                "config": {"label": "IF Condition", "field": field_name, "operator": "eq", "value": True},
            }
        )
        edges.append({"source": prev_id, "target": if_id})
        x_cursor += 260.0
        nodes.append({"id": "output_true", "type": "output", "position": {"x": x_cursor, "y": 120.0}, "config": {"label": "Success Output"}})
        nodes.append({"id": "output_false", "type": "output", "position": {"x": x_cursor, "y": 270.0}, "config": {"label": "Fallback Output"}})
        edges.append({"source": if_id, "target": "output_true", "source_handle": "true", "label": "true"})
        edges.append({"source": if_id, "target": "output_false", "source_handle": "false", "label": "false"})
    else:
        nodes.append({"id": "output_1", "type": "output", "position": {"x": x_cursor, "y": 190.0}, "config": {"label": "Output"}})
        edges.append({"source": prev_id, "target": "output_1"})

    raw_def = {"schema_version": "1.0", "nodes": nodes, "edges": edges}
    validated = WorkflowDefinition.model_validate(raw_def)
    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)

    return {
        "is_draft": True,
        "requires_human_review": True,
        "provider": provider,
        "suggested_name": f"Draft: {clean_prompt[:48]}",
        "definition": validated.model_dump(mode="json"),
        "provenance": {
            "generator": f"flowforge-ai-{provider}",
            "prompt_length": len(clean_prompt),
            "latency_ms": elapsed_ms,
            "estimated_cost_usd": 0.0,
        },
    }


def explain_workflow(definition: dict[str, Any]) -> dict[str, Any]:
    nodes = definition.get("nodes") or []
    edges = definition.get("edges") or []
    steps = [
        f"Step {idx + 1}: [{n.get('id')}] ({n.get('type')}) — {n.get('config', {}).get('label', n.get('type'))}"
        for idx, n in enumerate(nodes)
    ]
    branches = [
        f"{e.get('source')} -> {e.get('target')}" + (f" [branch: {e.get('source_handle')}]" if e.get("source_handle") else "")
        for e in edges
    ]
    return {
        "summary": f"Workflow with {len(nodes)} nodes and {len(edges)} directed connections.",
        "steps": steps,
        "connections": branches,
    }


def diagnose_failed_execution(workflow_definition: dict[str, Any], execution_record: dict[str, Any]) -> dict[str, Any]:
    redacted_exec = mask_secrets(execution_record)
    error_text = str(redacted_exec.get("error") or "")
    node_runs = redacted_exec.get("node_runs") or []
    failed_node_id = None
    for nr in node_runs:
        if isinstance(nr, dict) and nr.get("status") == "failed":
            failed_node_id = nr.get("node_id")
            break

    proposed_diff: dict[str, Any] = {}
    nodes = workflow_definition.get("nodes") or []
    target_node = next((n for n in nodes if isinstance(n, dict) and n.get("id") == failed_node_id), None)

    if "ssrf" in error_text.lower() or "blocked" in error_text.lower() or "loopback" in error_text.lower() or "503" in error_text.lower():
        diagnosis = "The HTTP Request node failed due to a blocked address or upstream endpoint error."
        if target_node:
            old_url = target_node.get("config", {}).get("url")
            proposed_diff = {
                "node_id": failed_node_id,
                "field": "config.url",
                "before": old_url,
                "after": "mock://status.local/health",
                "reason": "Update endpoint URL to a healthy/permitted target.",
            }
    elif "must be an object" in error_text.lower():
        diagnosis = "The Set node `config.values` was not a valid JSON object."
        proposed_diff = {
            "node_id": failed_node_id or "set_1",
            "field": "config.values",
            "before": target_node.get("config", {}).get("values") if target_node else None,
            "after": {"fixed": True},
            "reason": "Ensure `config.values` is a JSON dictionary.",
        }
    else:
        diagnosis = error_text or "Execution completed without fatal error."
        if target_node:
            proposed_diff = {
                "node_id": failed_node_id,
                "field": "retry_policy",
                "before": target_node.get("retry_policy"),
                "after": {"max_attempts": 3, "backoff_ms": 200, "backoff_multiplier": 2.0},
                "reason": "Attach a bounded retry policy or inspect upstream input mappings.",
            }

    return {
        "failed_node_id": failed_node_id,
        "diagnosis": diagnosis,
        "proposed_diff": proposed_diff,
        "redacted_context_verified": True,
    }


def run_ai_benchmarks() -> dict[str, Any]:
    from .engine import validate_workflow_graph

    prompts = [
        "Trigger a webhook, call an HTTP API endpoint, check if condition is true, and output",
        "Run a scheduled job every 15 minutes to execute a SQL query and output",
        "Parse CSV data and require human approval before output",
    ]
    passed = 0
    latencies: list[float] = []
    for p in prompts:
        t0 = time.perf_counter()
        draft = draft_workflow_from_prompt(p)
        latencies.append((time.perf_counter() - t0) * 1000)
        wf_def = WorkflowDefinition.model_validate(draft["definition"])
        report = validate_workflow_graph(wf_def)
        if report.valid and draft["is_draft"]:
            passed += 1

    return {
        "total_cases": len(prompts),
        "passed_cases": passed,
        "pass_rate": round(passed / len(prompts), 4),
        "avg_latency_ms": round(sum(latencies) / len(latencies), 3),
    }
