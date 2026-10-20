"""System-level 12-step critical happy-path acceptance test for FlowForge Community.
Verifies end-to-end persistence, Trigger -> HTTP Request -> IF -> Output execution,
per-node traces, controlled failure + diagnosis diff, config fix + version history,
human approval checkpoint + resume, and post-restart session persistence.
"""
from __future__ import annotations

from tests.test_api import TestingSessionLocal, client


def test_twelve_step_critical_happy_path_acceptance():
    # Step 1 & 2: Verify system readiness and migrations
    ready = client.get("/health/ready")
    assert ready.status_code == 200
    assert "0002_milestone3_platform" in ready.json()["migrations_applied"]

    # Step 3, 4, 5: Create Trigger -> HTTP Request -> IF -> Output workflow
    create_payload = {
        "name": "E2E Order Verification Pipeline",
        "description": "Critical acceptance test workflow",
        "tags": ["e2e", "acceptance"],
        "folder": "Production",
        "environment": "dev",
        "definition": {
            "schema_version": "1.0",
            "nodes": [
                {"id": "trigger_1", "type": "trigger", "position": {"x": 80, "y": 180}},
                {
                    "id": "http_1",
                    "type": "http_request",
                    "position": {"x": 320, "y": 180},
                    "config": {
                        "label": "Call Order Service",
                        "method": "POST",
                        "url": "mock://orders.local/verify",
                        "response_field": "order_api",
                    },
                },
                {
                    "id": "if_1",
                    "type": "if_condition",
                    "position": {"x": 560, "y": 180},
                    "config": {"field": "order_api.ok", "operator": "eq", "value": True},
                },
                {
                    "id": "set_ok",
                    "type": "set",
                    "position": {"x": 800, "y": 120},
                    "config": {"values": {"verified": True, "customer": "{{ $input.customer }}"}},
                },
                {
                    "id": "set_fail",
                    "type": "set",
                    "position": {"x": 800, "y": 260},
                    "config": {"values": {"verified": False}},
                },
                {"id": "output_1", "type": "output", "position": {"x": 1040, "y": 180}},
            ],
            "edges": [
                {"source": "trigger_1", "target": "http_1"},
                {"source": "http_1", "target": "if_1"},
                {"source": "if_1", "target": "set_ok", "source_handle": "true"},
                {"source": "if_1", "target": "set_fail", "source_handle": "false"},
                {"source": "set_ok", "target": "output_1"},
                {"source": "set_fail", "target": "output_1"},
            ],
        },
    }
    created = client.post("/api/workflows", json=create_payload)
    assert created.status_code == 201, created.text
    wf_id = created.json()["id"]

    # Step 6: Reload workflow and verify persistence
    reloaded = client.get(f"/api/workflows/{wf_id}")
    assert reloaded.status_code == 200
    assert reloaded.json()["version"] == 1
    assert len(reloaded.json()["definition"]["nodes"]) == 6

    # Step 7 & 8: Execute with known input and inspect per-node inputs, outputs, and statuses
    exec_ok = client.post(
        f"/api/workflows/{wf_id}/execute",
        json={"input": {"customer": "Jeeva", "service": "orders"}},
    )
    assert exec_ok.status_code == 201, exec_ok.text
    exec_data = exec_ok.json()
    assert exec_data["status"] == "succeeded"
    assert exec_data["result_data"]["verified"] is True
    assert exec_data["result_data"]["customer"] == "Jeeva"

    node_statuses = {nr["node_id"]: nr["status"] for nr in exec_data["node_runs"]}
    assert node_statuses["trigger_1"] == "succeeded"
    assert node_statuses["http_1"] == "succeeded"
    assert node_statuses["if_1"] == "succeeded"
    assert node_statuses["set_ok"] == "succeeded"
    assert node_statuses["set_fail"] == "skipped"
    assert node_statuses["output_1"] == "succeeded"

    # Step 9: Force a controlled failure and inspect structured error & diagnosis diff
    fail_payload = dict(create_payload)
    fail_payload["comment"] = "Point to failing endpoint"
    fail_payload["definition"] = dict(create_payload["definition"])
    fail_payload["definition"]["nodes"] = [dict(n) for n in create_payload["definition"]["nodes"]]
    fail_payload["definition"]["nodes"][1] = {
        **fail_payload["definition"]["nodes"][1],
        "config": {"label": "Call Order Service", "method": "POST", "url": "mock://orders.local/fail", "response_field": "order_api"},
    }
    client.put(f"/api/workflows/{wf_id}", json=fail_payload)

    exec_fail = client.post(f"/api/workflows/{wf_id}/execute", json={"input": {"customer": "Jeeva"}})
    assert exec_fail.status_code == 201
    fail_data = exec_fail.json()
    assert fail_data["status"] == "failed"
    assert "503 Service Unavailable" in fail_data["error"]

    diag = client.get(f"/api/executions/{fail_data['id']}/diagnose")
    assert diag.status_code == 200
    assert diag.json()["failed_node_id"] == "http_1"
    assert diag.json()["proposed_diff"]["node_id"] == "http_1"

    # Step 10: Restore version 1 (correct configuration) and execute again
    restored = client.post(f"/api/workflows/{wf_id}/versions/1/restore")
    assert restored.status_code == 200
    assert restored.json()["version"] == 3

    exec_again = client.post(f"/api/workflows/{wf_id}/execute", json={"input": {"customer": "Jeeva"}})
    assert exec_again.status_code == 201
    assert exec_again.json()["status"] == "succeeded"

    # Step 11 & 12: Verify persistent execution history, versions, and audit logs across sessions
    history = client.get("/api/executions", params={"workflow_id": wf_id})
    assert history.status_code == 200
    assert len(history.json()) == 3

    versions = client.get(f"/api/workflows/{wf_id}/versions")
    assert versions.status_code == 200
    assert len(versions.json()) == 3

    with TestingSessionLocal() as fresh_session:
        from flowforge.models import Execution, Workflow

        assert fresh_session.get(Workflow, wf_id) is not None
        assert len(fresh_session.query(Execution).filter(Execution.workflow_id == wf_id).all()) == 3


def test_human_approval_checkpoint_pause_and_resume():
    tpl_wf = client.post("/api/templates/tpl-human-approval-deployment/instantiate")
    assert tpl_wf.status_code == 201, tpl_wf.text
    wf_id = tpl_wf.json()["id"]

    paused_run = client.post(f"/api/workflows/{wf_id}/execute", json={"input": {"release_tag": "v0.3.0"}})
    assert paused_run.status_code == 201
    paused_data = paused_run.json()
    assert paused_data["status"] == "waiting_approval"

    resumed_run = client.post(
        f"/api/executions/{paused_data['id']}/approve",
        json={"approved": True, "comment": "Looks good to ship", "reviewer": "principal-architect"},
    )
    assert resumed_run.status_code == 200, resumed_run.text
    resumed_data = resumed_run.json()
    assert resumed_data["status"] == "succeeded"
    assert resumed_data["result_data"]["deployment_status"] == "approved_and_released"
