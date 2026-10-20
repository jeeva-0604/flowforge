"""Curated, secret-free Workflow Templates Catalog for FlowForge Community."""
from __future__ import annotations

from typing import Any

WORKFLOW_TEMPLATES: list[dict[str, Any]] = [
    {
        "id": "tpl-http-conditional-alert",
        "name": "HTTP Health Check & Conditional Routing",
        "category": "DevOps & Reliability",
        "tags": ["http", "if-condition", "monitoring"],
        "version": "1.0.0",
        "license": "Apache-2.0",
        "provenance": "FlowForge Community Official Templates",
        "maintenance_status": "verified",
        "compatibility": ">=0.3.0",
        "required_credentials": [],
        "description": "Triggers a run, calls an HTTP endpoint, evaluates status via an IF Condition node, and routes to success or alert output branches.",
        "sample_payload": {"service": "billing-api", "environment": "staging"},
        "definition": {
            "schema_version": "1.0",
            "nodes": [
                {"id": "trigger_1", "type": "trigger", "position": {"x": 70, "y": 180}, "config": {"label": "Manual Trigger", "subtitle": "Start check"}},
                {
                    "id": "http_1",
                    "type": "http_request",
                    "position": {"x": 310, "y": 180},
                    "config": {
                        "label": "Check Service Endpoint",
                        "method": "GET",
                        "url": "mock://status.local/health",
                        "response_field": "health_response",
                    },
                    "retry_policy": {"max_attempts": 2, "backoff_ms": 100, "backoff_multiplier": 2.0},
                },
                {
                    "id": "if_1",
                    "type": "if_condition",
                    "position": {"x": 560, "y": 180},
                    "config": {"label": "Is Service Healthy?", "field": "health_response.ok", "operator": "eq", "value": True},
                },
                {
                    "id": "set_healthy",
                    "type": "set",
                    "position": {"x": 810, "y": 100},
                    "config": {"label": "Mark Healthy", "values": {"alert_required": False, "health_state": "operational"}},
                },
                {
                    "id": "set_degraded",
                    "type": "set",
                    "position": {"x": 810, "y": 260},
                    "config": {"label": "Mark Degraded", "values": {"alert_required": True, "health_state": "degraded"}},
                },
                {"id": "output_1", "type": "output", "position": {"x": 1060, "y": 180}, "config": {"label": "Final Status"}},
            ],
            "edges": [
                {"source": "trigger_1", "target": "http_1"},
                {"source": "http_1", "target": "if_1"},
                {"source": "if_1", "target": "set_healthy", "source_handle": "true", "label": "true"},
                {"source": "if_1", "target": "set_degraded", "source_handle": "false", "label": "false"},
                {"source": "set_healthy", "target": "output_1"},
                {"source": "set_degraded", "target": "output_1"},
            ],
        },
    },
    {
        "id": "tpl-csv-normalization-pipeline",
        "name": "CSV Customer Ingestion & Filter Pipeline",
        "category": "Data Engineering",
        "tags": ["csv", "filter", "loop", "etl"],
        "version": "1.0.0",
        "license": "Apache-2.0",
        "provenance": "FlowForge Community Official Templates",
        "maintenance_status": "verified",
        "compatibility": ">=0.3.0",
        "required_credentials": [],
        "description": "Parses incoming CSV records into JSON, filters active records, and emits clean structured output.",
        "sample_payload": {"csv_text": "customer,tier,active\nAcme Corp,enterprise,true\nBeta LLC,starter,false\nGamma Inc,enterprise,true"},
        "definition": {
            "schema_version": "1.0",
            "nodes": [
                {"id": "trigger_1", "type": "trigger", "position": {"x": 70, "y": 180}, "config": {"label": "CSV Payload Trigger"}},
                {
                    "id": "csv_1",
                    "type": "csv_json",
                    "position": {"x": 320, "y": 180},
                    "config": {"label": "Parse CSV", "mode": "csv_to_json", "source_field": "csv_text", "target_field": "records"},
                },
                {
                    "id": "filter_1",
                    "type": "filter",
                    "position": {"x": 570, "y": 180},
                    "config": {
                        "label": "Filter Enterprise Tier",
                        "list_field": "records",
                        "item_field": "tier",
                        "operator": "eq",
                        "value": "enterprise",
                        "output_field": "enterprise_customers",
                    },
                },
                {"id": "output_1", "type": "output", "position": {"x": 830, "y": 180}, "config": {"label": "Normalized Output"}},
            ],
            "edges": [
                {"source": "trigger_1", "target": "csv_1"},
                {"source": "csv_1", "target": "filter_1"},
                {"source": "filter_1", "target": "output_1"},
            ],
        },
    },
    {
        "id": "tpl-human-approval-deployment",
        "name": "Human-in-the-Loop Release Approval Gate",
        "category": "Governance & Security",
        "tags": ["approval", "checkpoint", "governance"],
        "version": "1.0.0",
        "license": "Apache-2.0",
        "provenance": "FlowForge Community Official Templates",
        "maintenance_status": "verified",
        "compatibility": ">=0.3.0",
        "required_credentials": [],
        "description": "Prepares release metadata, pauses at a Human Approval checkpoint until an operator approves, and finalizes deployment status.",
        "sample_payload": {"release_tag": "v1.4.0", "requested_by": "release-bot"},
        "definition": {
            "schema_version": "1.0",
            "nodes": [
                {"id": "trigger_1", "type": "trigger", "position": {"x": 80, "y": 180}, "config": {"label": "Release Request"}},
                {
                    "id": "set_stage",
                    "type": "set",
                    "position": {"x": 330, "y": 180},
                    "config": {"label": "Prepare Metadata", "values": {"stage": "pre-approval", "risk_level": "medium"}},
                },
                {
                    "id": "approval_1",
                    "type": "human_approval",
                    "position": {"x": 580, "y": 180},
                    "config": {"label": "Operator Approval", "message": "Approve production rollout?", "auto_approve_in_test": False},
                },
                {
                    "id": "set_done",
                    "type": "set",
                    "position": {"x": 830, "y": 180},
                    "config": {"label": "Mark Approved", "values": {"deployment_status": "approved_and_released"}},
                },
                {"id": "output_1", "type": "output", "position": {"x": 1080, "y": 180}, "config": {"label": "Release Summary"}},
            ],
            "edges": [
                {"source": "trigger_1", "target": "set_stage"},
                {"source": "set_stage", "target": "approval_1"},
                {"source": "approval_1", "target": "set_done"},
                {"source": "set_done", "target": "output_1"},
            ],
        },
    },
]


def list_templates(category: str | None = None, search: str | None = None) -> list[dict[str, Any]]:
    items = WORKFLOW_TEMPLATES
    if category:
        items = [t for t in items if t["category"].lower() == category.lower()]
    if search:
        q = search.lower()
        items = [
            t
            for t in items
            if q in t["name"].lower()
            or q in t["description"].lower()
            or any(q in tag.lower() for tag in t["tags"])
        ]
    return items


def get_template(template_id: str) -> dict[str, Any] | None:
    return next((t for t in WORKFLOW_TEMPLATES if t["id"] == template_id), None)
