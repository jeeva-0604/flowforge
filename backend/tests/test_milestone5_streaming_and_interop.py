"""Milestone 5 (v0.5.0) tests covering:
- 5 new nodes: graphql_query, xml_html_parser (with XXE block), crypto_hash_hmac, rate_limit_throttle, deduplicate_items
- Real-time Server-Sent Events (SSE) execution streaming (/api/workflows/{id}/execute-stream)
- Distributed Worker Pool registration, heartbeat, draining, and Dead-Letter Queue job replay
- Clean-Room External Workflow JSON Interoperability Importer (/api/workflows/import-interoperable)
- Cron Schedule Auditor & Workflow Security Posture Scanner skills
"""
from __future__ import annotations

import hashlib
from flowforge.engine import execute_workflow_detailed
from flowforge.models import ExecutionJob
from flowforge.schemas import WorkflowDefinition
from tests.test_api import TestingSessionLocal, client


def test_five_new_milestone5_nodes_and_xxe_guard():
    definition = WorkflowDefinition.model_validate(
        {
            "nodes": [
                {"id": "start", "type": "trigger"},
                {
                    "id": "throttle",
                    "type": "rate_limit_throttle",
                    "config": {"bucket_key": "partner_api", "max_per_minute": 120},
                },
                {
                    "id": "gql",
                    "type": "graphql_query",
                    "config": {
                        "url": "mock://graphql.local/api",
                        "query": "query { orders { id } }",
                        "variables": {"org": "{{ $input.org }}"},
                        "output_field": "gql_out",
                    },
                },
                {
                    "id": "xml_parse",
                    "type": "xml_html_parser",
                    "config": {
                        "source_field": "xml_text",
                        "tag": "product",
                        "output_field": "products",
                    },
                },
                {
                    "id": "dedup",
                    "type": "deduplicate_items",
                    "config": {
                        "list_field": "raw_items",
                        "key_field": "sku",
                        "output_field": "clean_items",
                    },
                },
                {
                    "id": "signer",
                    "type": "crypto_hash_hmac",
                    "config": {
                        "algorithm": "sha256",
                        "input_text": "{{ $input.org }}",
                        "output_field": "org_hash",
                    },
                },
                {"id": "out", "type": "output"},
            ],
            "edges": [
                {"source": "start", "target": "throttle"},
                {"source": "throttle", "target": "gql"},
                {"source": "gql", "target": "xml_parse"},
                {"source": "xml_parse", "target": "dedup"},
                {"source": "dedup", "target": "signer"},
                {"source": "signer", "target": "out"},
            ],
        }
    )
    payload = {
        "org": "flowforge-india",
        "xml_text": "<catalog><product code='A1'>Router</product><product code='B2'>Switch</product></catalog>",
        "raw_items": [{"sku": "S1", "qty": 2}, {"sku": "S1", "qty": 9}, {"sku": "S2", "qty": 1}],
    }
    res = execute_workflow_detailed(definition, payload)
    assert res["status"] == "succeeded", res.get("error")
    out = res["result_data"]
    assert out["_throttle"]["allowed"] is True
    assert out["gql_out"]["data"]["mock_graphql"] is True
    assert out["products_count"] == 2
    assert out["products"][0]["text"] == "Router"
    assert len(out["clean_items"]) == 2
    assert out["duplicates_removed"] == 1
    assert out["org_hash"] == hashlib.sha256(b"flowforge-india").hexdigest()

    # Verify XXE external entity attack is blocked
    xxe_def = WorkflowDefinition.model_validate(
        {
            "nodes": [
                {"id": "start", "type": "trigger"},
                {"id": "xml_bad", "type": "xml_html_parser", "config": {"source_field": "xml_text", "tag": "foo"}},
            ],
            "edges": [{"source": "start", "target": "xml_bad"}],
        }
    )
    xxe_res = execute_workflow_detailed(
        xxe_def,
        {"xml_text": "<!DOCTYPE foo [<!ENTITY xxe SYSTEM 'file:///etc/passwd'>]><foo>&xxe;</foo>"},
    )
    assert xxe_res["status"] == "failed"
    assert "XXE" in xxe_res["error"]


def test_sse_execution_streaming_endpoint():
    wf = client.post(
        "/api/workflows",
        json={
            "name": "SSE Stream Test Workflow",
            "definition": {
                "nodes": [
                    {"id": "start", "type": "trigger"},
                    {"id": "step_a", "type": "set", "config": {"values": {"a": 1}}},
                    {"id": "out", "type": "output"},
                ],
                "edges": [
                    {"source": "start", "target": "step_a"},
                    {"source": "step_a", "target": "out"},
                ],
            },
        },
    ).json()

    resp = client.post(f"/api/workflows/{wf['id']}/execute-stream", json={"input": {"hello": "stream"}})
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers.get("content-type", "")
    body = resp.text
    assert "event: execution.started" in body
    assert "event: node.completed" in body
    assert '"node_id": "step_a"' in body
    assert "event: execution.completed" in body


def test_worker_pool_registry_and_dead_letter_replay():
    reg = client.post(
        "/api/workers/register",
        json={"worker_id": "worker-chennai-01", "hostname": "node-01.local", "queues": ["default", "critical"], "concurrency": 8},
    )
    assert reg.status_code == 201, reg.text
    assert reg.json()["status"] == "active"

    hb = client.post("/api/workers/worker-chennai-01/heartbeat")
    assert hb.status_code == 200

    dr = client.post("/api/workers/worker-chennai-01/drain")
    assert dr.status_code == 200
    assert dr.json()["status"] == "draining"

    workers = client.get("/api/workers").json()
    assert any(w["id"] == "worker-chennai-01" for w in workers)

    # Create a job, mark it dead_letter, and verify retry-dead-letter re-queues it
    wf = client.post(
        "/api/workflows",
        json={
            "name": "DLQ Retry Workflow",
            "definition": {"nodes": [{"id": "t", "type": "trigger"}], "edges": []},
        },
    ).json()
    job = client.post(f"/api/queue/jobs?workflow_id={wf['id']}", json={"input": {}}).json()
    with TestingSessionLocal() as session:
        j_obj = session.get(ExecutionJob, job["id"])
        j_obj.status = "dead_letter"
        j_obj.attempts = 3
        j_obj.last_error = "Simulated upstream outage"
        session.add(j_obj)
        session.commit()

    retried = client.post(f"/api/queue/jobs/{job['id']}/retry-dead-letter")
    assert retried.status_code == 200
    assert retried.json()["status"] == "queued"
    assert retried.json()["attempts"] == 0


def test_clean_room_interoperable_workflow_importer_and_security_scanner():
    external_json = {
        "name": "Migrated Order Webhook Pipeline",
        "nodes": [
            {"name": "Incoming Webhook", "type": "vendor.webhook", "parameters": {"path_slug": "ext-orders"}, "position": [100, 200]},
            {"name": "Fetch Customer", "type": "vendor.httpRequest", "parameters": {"url": "mock://crm.local/customer"}, "position": [360, 200]},
            {"name": "Check VIP", "type": "vendor.if", "parameters": {"field": "http.ok", "operator": "eq", "value": True}, "position": [620, 200]},
            {"name": "Notify Slack", "type": "vendor.slack", "parameters": {"channel": "#vip", "message": "VIP Order"}, "position": [880, 140]},
        ],
        "connections": {
            "Incoming Webhook": {"main": [[{"node": "Fetch Customer"}]]},
            "Fetch Customer": {"main": [[{"node": "Check VIP"}]]},
            "Check VIP": {"main": [[{"node": "Notify Slack"}], []]},
        },
    }
    imported = client.post("/api/workflows/import-interoperable", json=external_json)
    assert imported.status_code == 201, imported.text
    data = imported.json()
    assert data["migration_report"]["mapped_node_count"] == 4
    wf_id = data["workflow"]["id"]

    # Run security posture scan on the migrated workflow
    scan = client.get(f"/api/workflows/{wf_id}/security-scan")
    assert scan.status_code == 200
    assert scan.json()["score"] == 100
    assert scan.json()["passed_gate"] is True

    # Execute the migrated workflow end-to-end
    run = client.post(f"/api/workflows/{wf_id}/execute", json={"input": {"order_id": 9001}})
    assert run.status_code == 201
    assert run.json()["status"] == "succeeded"
