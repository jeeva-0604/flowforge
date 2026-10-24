"""Milestone 4 (v0.4.0) tests covering the 6 new enterprise/developer nodes,
workspace variables ($vars), node output pinning, workflow test suites & assertions,
custom skill installation, Prometheus metrics, CycloneDX SBOM, and backup/restore.
"""
from __future__ import annotations

from flowforge.engine import execute_workflow_detailed
from flowforge.schemas import WorkflowDefinition
from tests.test_api import client


def test_six_new_enterprise_and_ai_nodes():
    definition = WorkflowDefinition.model_validate(
        {
            "nodes": [
                {"id": "start", "type": "trigger"},
                {
                    "id": "validate_schema",
                    "type": "json_schema_validator",
                    "config": {
                        "schema": {"type": "object", "required": ["user", "query"]},
                        "strict": True,
                    },
                },
                {
                    "id": "vec_upsert",
                    "type": "vector_memory",
                    "config": {
                        "operation": "upsert",
                        "namespace": "kb_test",
                        "doc_id": "doc_101",
                        "text": "PostgreSQL database migration and backup guide",
                        "output_field": "vec_upsert_out",
                    },
                },
                {
                    "id": "vec_query",
                    "type": "vector_memory",
                    "config": {
                        "operation": "query",
                        "namespace": "kb_test",
                        "text": "{{ $input.query }}",
                        "top_k": 1,
                        "output_field": "kb_matches",
                    },
                },
                {
                    "id": "s3_put",
                    "type": "object_storage",
                    "config": {
                        "operation": "put_object",
                        "bucket": "audit-bucket",
                        "object_key": "runs/latest.json",
                        "output_field": "s3_put_res",
                    },
                },
                {
                    "id": "s3_get",
                    "type": "object_storage",
                    "config": {
                        "operation": "get_object",
                        "bucket": "audit-bucket",
                        "object_key": "runs/latest.json",
                        "output_field": "s3_loaded",
                    },
                },
                {
                    "id": "gh_issue",
                    "type": "github_api",
                    "config": {
                        "action": "create_issue",
                        "repository": "flowforge/core",
                        "title": "Run by {{ $input.user }}",
                        "output_field": "gh_out",
                    },
                },
                {
                    "id": "slack_msg",
                    "type": "slack_notify",
                    "config": {
                        "channel": "#ops",
                        "message": "Completed for {{ $input.user }}",
                        "webhook_url": "mock://slack.local/hook",
                        "output_field": "slack_out",
                    },
                },
                {
                    "id": "email_msg",
                    "type": "smtp_email",
                    "config": {
                        "to": "team@example.com",
                        "subject": "Report for {{ $input.user }}",
                        "body": "All checks passed",
                        "mode": "outbox",
                        "output_field": "email_out",
                    },
                },
                {"id": "out", "type": "output"},
            ],
            "edges": [
                {"source": "start", "target": "validate_schema"},
                {"source": "validate_schema", "target": "vec_upsert"},
                {"source": "vec_upsert", "target": "vec_query"},
                {"source": "vec_query", "target": "s3_put"},
                {"source": "s3_put", "target": "s3_get"},
                {"source": "s3_get", "target": "gh_issue"},
                {"source": "gh_issue", "target": "slack_msg"},
                {"source": "slack_msg", "target": "email_msg"},
                {"source": "email_msg", "target": "out"},
            ],
        }
    )
    res = execute_workflow_detailed(definition, {"user": "Ravi", "query": "PostgreSQL backup"})
    assert res["status"] == "succeeded", res.get("error")
    data = res["result_data"]
    assert data["_schema_validation"]["valid"] is True
    assert data["kb_matches"][0]["id"] == "doc_101"
    assert data["s3_loaded"]["user"] == "Ravi"
    assert data["gh_out"]["title"] == "Run by Ravi"
    assert data["slack_out"]["delivered"] is True
    assert data["email_out"]["status"] == "queued_in_outbox"


def test_workspace_variables_and_node_output_pinning():
    v1 = client.post(
        "/api/variables",
        json={"key": "REGION", "value": "ap-south-1", "environment": "all", "is_secret": False},
    )
    assert v1.status_code == 201
    v2 = client.post(
        "/api/variables",
        json={"key": "INTERNAL_TOKEN", "value": "super_secret_var_999", "environment": "dev", "is_secret": True},
    )
    assert v2.status_code == 201
    assert v2.json()["value"] == "***REDACTED***"

    wf = client.post(
        "/api/workflows",
        json={
            "name": "Variables & Pinning Workflow",
            "environment": "dev",
            "definition": {
                "nodes": [
                    {"id": "start", "type": "trigger"},
                    {
                        "id": "http_external",
                        "type": "http_request",
                        "config": {"url": "http://127.0.0.1:9999/would-fail-ssrf-if-not-pinned"},
                    },
                    {
                        "id": "enrich",
                        "type": "set",
                        "config": {
                            "values": {
                                "region": "{{ $vars.REGION }}",
                                "leaked": "{{ $vars.INTERNAL_TOKEN }}",
                                "mocked_status": "{{ $nodes.http_external.mock_ok }}",
                            }
                        },
                    },
                    {"id": "out", "type": "output"},
                ],
                "edges": [
                    {"source": "start", "target": "http_external"},
                    {"source": "http_external", "target": "enrich"},
                    {"source": "enrich", "target": "out"},
                ],
            },
        },
    ).json()

    run = client.post(
        f"/api/workflows/{wf['id']}/execute",
        json={
            "input": {"user": "tester"},
            "pinned_node_outputs": {"http_external": {"mock_ok": "pinned_success"}},
        },
    )
    assert run.status_code == 201, run.text
    ex = run.json()
    assert ex["status"] == "succeeded"
    assert ex["result_data"]["region"] == "ap-south-1"
    assert ex["result_data"]["mocked_status"] == "pinned_success"
    assert ex["result_data"]["leaked"] == "***REDACTED***"
    node_statuses = {nr["node_id"]: nr["status"] for nr in ex["node_runs"]}
    assert node_statuses["http_external"] == "pinned"


def test_workflow_test_suite_and_assertions_runner():
    wf = client.post(
        "/api/workflows",
        json={
            "name": "Testable Discount Pipeline",
            "definition": {
                "nodes": [
                    {"id": "start", "type": "trigger"},
                    {
                        "id": "check_vip",
                        "type": "if_condition",
                        "config": {"field": "spend", "operator": "gte", "value": 500},
                    },
                    {"id": "vip_set", "type": "set", "config": {"values": {"discount": 20}}},
                    {"id": "std_set", "type": "set", "config": {"values": {"discount": 5}}},
                    {"id": "out", "type": "output"},
                ],
                "edges": [
                    {"source": "start", "target": "check_vip"},
                    {"source": "check_vip", "target": "vip_set", "source_handle": "true"},
                    {"source": "check_vip", "target": "std_set", "source_handle": "false"},
                    {"source": "vip_set", "target": "out"},
                    {"source": "std_set", "target": "out"},
                ],
            },
        },
    ).json()

    tc1 = client.post(
        f"/api/workflows/{wf['id']}/test-cases",
        json={
            "name": "VIP Spend >= 500 gets 20% discount",
            "input_data": {"spend": 750},
            "assertions": [
                {"kind": "status_equals", "expected": "succeeded"},
                {"kind": "field_equals", "target": "discount", "expected": 20},
                {"kind": "node_status_equals", "target": "std_set", "expected": "skipped"},
            ],
        },
    )
    assert tc1.status_code == 201

    tc2 = client.post(
        f"/api/workflows/{wf['id']}/test-cases",
        json={
            "name": "Standard Spend < 500 gets 5% discount",
            "input_data": {"spend": 120},
            "assertions": [
                {"kind": "status_equals", "expected": "succeeded"},
                {"kind": "field_equals", "target": "discount", "expected": 5},
                {"kind": "node_status_equals", "target": "vip_set", "expected": "skipped"},
            ],
        },
    )
    assert tc2.status_code == 201

    suite_run = client.post(f"/api/workflows/{wf['id']}/test-cases/run")
    assert suite_run.status_code == 200, suite_run.text
    report = suite_run.json()
    assert report["total_cases"] == 2
    assert report["passed_cases"] == 2
    assert report["all_passed"] is True


def test_custom_skill_install_and_new_first_party_skills():
    scaf = client.post(
        "/api/skills/api-integration-scaffold-generator/execute",
        json={"service_name": "Linear Issue Tracker", "category": "Developer & Enterprise"},
    )
    assert scaf.status_code == 200
    assert scaf.json()["node_type"] == "linear_issue_tracker"

    doc = client.post(
        "/api/skills/workflow-documentation-generator/execute",
        json={"name": "Sample Flow", "nodes": [{"id": "t1", "type": "trigger"}], "edges": []},
    )
    assert doc.status_code == 200
    assert "# Workflow Runbook: Sample Flow" in doc.json()["markdown_doc"]

    installed = client.post(
        "/api/skills/install",
        json={
            "id": "custom-json-sanitizer",
            "version": "1.2.0",
            "name": "Custom JSON Sanitizer",
            "category": "Custom",
            "description": "Sanitizes custom fields for internal compliance workflows.",
            "permissions": ["data:transform"],
            "example_input": {"hello": "world"},
        },
    )
    assert installed.status_code == 201, installed.text
    assert installed.json()["integrity_hash"].startswith("sha256:")

    ran = client.post("/api/skills/custom-json-sanitizer/execute", json={"sample": 123})
    assert ran.status_code == 200
    assert ran.json()["custom_skill"] is True

    deleted = client.delete("/api/skills/custom-json-sanitizer")
    assert deleted.status_code == 200


def test_prometheus_metrics_cyclonedx_sbom_and_workspace_backup_restore():
    metrics = client.get("/metrics")
    assert metrics.status_code == 200
    assert "flowforge_workflows_total" in metrics.text
    assert "flowforge_integrations_total 32" in metrics.text

    sbom = client.get("/api/system/sbom")
    assert sbom.status_code == 200
    assert sbom.json()["bomFormat"] == "CycloneDX"
    assert len(sbom.json()["components"]) >= 15

    backup = client.get("/api/system/backup")
    assert backup.status_code == 200
    b_data = backup.json()
    assert b_data["integrity_hash"].startswith("sha256:")
    assert len(b_data["bundle"]["workflows"]) >= 1

    restored = client.post("/api/system/restore", json=b_data)
    assert restored.status_code == 200
    assert restored.json()["status"] == "restored"
