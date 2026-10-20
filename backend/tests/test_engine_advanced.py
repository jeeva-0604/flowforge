"""Advanced workflow engine unit and integration tests."""
from __future__ import annotations

import pytest
from flowforge.engine import (
    WorkflowValidationError,
    diff_workflow_definitions,
    execute_workflow_detailed,
    validate_workflow_graph,
)
from flowforge.schemas import WorkflowDefinition
from flowforge.security import CodeExecutionError, PathSecurityError, SecurityError


def test_expressions_and_if_condition_branch_pruning():
    definition = WorkflowDefinition.model_validate(
        {
            "nodes": [
                {"id": "start", "type": "trigger"},
                {
                    "id": "enrich",
                    "type": "set",
                    "config": {"values": {"greeting": "Hello {{ $input.user }}", "score": 95}},
                },
                {
                    "id": "branch",
                    "type": "if_condition",
                    "config": {"field": "score", "operator": "gte", "value": 80},
                },
                {
                    "id": "high_tier",
                    "type": "set",
                    "config": {"values": {"tier": "gold", "msg": "{{ $nodes.enrich.greeting }}!"}},
                },
                {
                    "id": "low_tier",
                    "type": "set",
                    "config": {"values": {"tier": "standard"}},
                },
                {"id": "out", "type": "output"},
            ],
            "edges": [
                {"source": "start", "target": "enrich"},
                {"source": "enrich", "target": "branch"},
                {"source": "branch", "target": "high_tier", "source_handle": "true"},
                {"source": "branch", "target": "low_tier", "source_handle": "false"},
                {"source": "high_tier", "target": "out"},
                {"source": "low_tier", "target": "out"},
            ],
        }
    )
    res = execute_workflow_detailed(definition, {"user": "Ada"})
    assert res["status"] == "succeeded"
    assert res["result_data"]["tier"] == "gold"
    assert res["result_data"]["msg"] == "Hello Ada!"
    statuses = {nr["node_id"]: nr["status"] for nr in res["node_runs"]}
    assert statuses["high_tier"] == "succeeded"
    assert statuses["low_tier"] == "skipped"


def test_filter_loop_csv_and_sql_nodes():
    definition = WorkflowDefinition.model_validate(
        {
            "nodes": [
                {"id": "start", "type": "trigger"},
                {
                    "id": "parse_csv",
                    "type": "csv_json",
                    "config": {"mode": "csv_to_json", "source_field": "csv_text", "target_field": "items"},
                },
                {
                    "id": "filter_active",
                    "type": "filter",
                    "config": {
                        "list_field": "items",
                        "item_field": "active",
                        "operator": "eq",
                        "value": True,
                        "output_field": "active_items",
                    },
                },
                {
                    "id": "loop_names",
                    "type": "loop",
                    "config": {
                        "list_field": "active_items",
                        "template": {"label": "{{ $item.name }}"},
                        "max_iterations": 10,
                        "output_field": "mapped",
                    },
                },
                {
                    "id": "sql_check",
                    "type": "sql_query",
                    "config": {
                        "query": "SELECT :dept AS department, 42 AS answer",
                        "params": {"dept": "engineering"},
                        "output_field": "query_rows",
                    },
                },
                {"id": "out", "type": "output"},
            ],
            "edges": [
                {"source": "start", "target": "parse_csv"},
                {"source": "parse_csv", "target": "filter_active"},
                {"source": "filter_active", "target": "loop_names"},
                {"source": "loop_names", "target": "sql_check"},
                {"source": "sql_check", "target": "out"},
            ],
        }
    )
    csv_payload = "name,active\nAlice,true\nBob,false\nCharlie,true"
    res = execute_workflow_detailed(definition, {"csv_text": csv_payload})
    assert res["status"] == "succeeded"
    out = res["result_data"]
    assert out["active_items_count"] == 2
    assert out["mapped"] == [{"label": "Alice"}, {"label": "Charlie"}]
    assert out["query_rows"] == [{"department": "engineering", "answer": 42}]


def test_sql_injection_multi_statement_is_blocked():
    definition = WorkflowDefinition.model_validate(
        {
            "nodes": [
                {"id": "start", "type": "trigger"},
                {
                    "id": "bad_sql",
                    "type": "sql_query",
                    "config": {"query": "SELECT 1; DROP TABLE workflows;"},
                },
            ],
            "edges": [{"source": "start", "target": "bad_sql"}],
        }
    )
    res = execute_workflow_detailed(definition, {})
    assert res["status"] == "failed"
    assert "Multi-statement SQL" in res["error"]


def test_isolated_code_node_executes_pure_transform_and_blocks_imports():
    good_def = WorkflowDefinition.model_validate(
        {
            "nodes": [
                {"id": "start", "type": "trigger"},
                {
                    "id": "compute",
                    "type": "code",
                    "config": {"code": "result = {'doubled': [x * 2 for x in data.get('nums', [])]}"},
                },
            ],
            "edges": [{"source": "start", "target": "compute"}],
        }
    )
    res = execute_workflow_detailed(good_def, {"nums": [2, 5, 9]})
    assert res["status"] == "succeeded"
    assert res["result_data"]["doubled"] == [4, 10, 18]

    bad_def = WorkflowDefinition.model_validate(
        {
            "nodes": [
                {"id": "start", "type": "trigger"},
                {
                    "id": "malicious",
                    "type": "code",
                    "config": {"code": "import os\nresult = {'env': dict(os.environ)}"},
                },
            ],
            "edges": [{"source": "start", "target": "malicious"}],
        }
    )
    bad_res = execute_workflow_detailed(bad_def, {})
    assert bad_res["status"] == "failed"
    assert "forbidden construct" in bad_res["error"]


def test_file_io_sandbox_and_path_traversal_block():
    good_def = WorkflowDefinition.model_validate(
        {
            "nodes": [
                {"id": "start", "type": "trigger"},
                {
                    "id": "write_f",
                    "type": "file_io",
                    "config": {"operation": "write_json", "path": "test_subdir/sample.json"},
                },
                {
                    "id": "read_f",
                    "type": "file_io",
                    "config": {"operation": "read_json", "path": "test_subdir/sample.json", "target_field": "loaded"},
                },
            ],
            "edges": [
                {"source": "start", "target": "write_f"},
                {"source": "write_f", "target": "read_f"},
            ],
        }
    )
    res = execute_workflow_detailed(good_def, {"hello": "sandbox"})
    assert res["status"] == "succeeded"
    assert res["result_data"]["loaded"]["hello"] == "sandbox"

    escape_def = WorkflowDefinition.model_validate(
        {
            "nodes": [
                {"id": "start", "type": "trigger"},
                {
                    "id": "escape",
                    "type": "file_io",
                    "config": {"operation": "read_text", "path": "../../etc/passwd"},
                },
            ],
            "edges": [{"source": "start", "target": "escape"}],
        }
    )
    escape_res = execute_workflow_detailed(escape_def, {})
    assert escape_res["status"] == "failed"
    assert "Path traversal" in escape_res["error"]


def test_validate_workflow_graph_and_diff():
    valid_def = WorkflowDefinition.model_validate(
        {
            "nodes": [
                {"id": "start", "type": "trigger"},
                {"id": "http_1", "type": "http_request", "config": {"url": ""}},
            ],
            "edges": [{"source": "start", "target": "http_1"}],
        }
    )
    report = validate_workflow_graph(valid_def)
    assert not report.valid
    assert any(i.code == "MISSING_HTTP_URL" and i.node_id == "http_1" for i in report.issues)

    diff = diff_workflow_definitions(
        {"nodes": [{"id": "start", "type": "trigger", "config": {}}], "edges": []},
        {
            "nodes": [
                {"id": "start", "type": "trigger", "config": {"label": "Updated"}},
                {"id": "out", "type": "output", "config": {}},
            ],
            "edges": [{"source": "start", "target": "out"}],
        },
    )
    assert diff["has_changes"] is True
    assert diff["added_nodes"] == ["out"]
    assert len(diff["modified_nodes"]) == 1
