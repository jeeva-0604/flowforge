"""Clean-Room Public Workflow Interoperability & Migration Mapper (`flowforge/interop.py`).
Maps public declarative workflow formats (such as generic `nodes` + `connections` graphs
or `steps` pipelines) into FlowForge's `WorkflowDefinition` schema while reporting all
mapped constructs and unsupported features transparently.
"""
from __future__ import annotations

import re
from typing import Any
from .schemas import TRIGGER_NODE_TYPES, WorkflowDefinition

PUBLIC_TYPE_MAPPING: dict[str, str] = {
    "manualtrigger": "trigger",
    "start": "trigger",
    "webhook": "webhook_trigger",
    "schedule": "schedule_trigger",
    "cron": "schedule_trigger",
    "httprequest": "http_request",
    "http": "http_request",
    "fetch": "http_request",
    "set": "set",
    "editfields": "set",
    "if": "if_condition",
    "switch": "switch",
    "merge": "merge",
    "filter": "filter",
    "loop": "loop",
    "splitinbatches": "loop",
    "wait": "wait",
    "code": "code",
    "function": "code",
    "postgres": "sql_query",
    "sql": "sql_query",
    "slack": "slack_notify",
    "github": "github_api",
    "email": "smtp_email",
    "s3": "object_storage",
    "graphql": "graphql_query",
    "crypto": "crypto_hash_hmac",
    "deduplicate": "deduplicate_items",
    "removeduplicates": "deduplicate_items",
    "output": "output",
    "respond": "output",
}


def convert_external_workflow(raw_payload: dict[str, Any]) -> dict[str, Any]:
    """Convert an external declarative workflow JSON into a validated FlowForge definition."""
    name = str(raw_payload.get("name") or "Migrated Workflow")[:120]
    raw_nodes = raw_payload.get("nodes") or raw_payload.get("steps") or []
    raw_edges = raw_payload.get("edges") or []
    raw_connections = raw_payload.get("connections") or {}

    mapped_nodes: list[dict[str, Any]] = []
    warnings: list[str] = []
    converted_types: list[dict[str, str]] = []
    name_to_id: dict[str, str] = {}

    for idx, rn in enumerate(raw_nodes):
        if not isinstance(rn, dict):
            continue
        orig_id = str(rn.get("id") or rn.get("name") or f"node_{idx + 1}")
        clean_id = re.sub(r"[^A-Za-z0-9_-]", "_", orig_id)[:80] or f"node_{idx + 1}"
        orig_name = str(rn.get("name") or orig_id)
        name_to_id[orig_name] = clean_id
        name_to_id[orig_id] = clean_id

        raw_type = str(rn.get("type") or "set").lower()
        short_type = re.sub(r"[^a-z0-9]", "", raw_type.split(".")[-1])
        ff_type = PUBLIC_TYPE_MAPPING.get(short_type)
        if ff_type is None:
            ff_type = "set"
            warnings.append(f"Node {clean_id!r} had unmapped type {rn.get('type')!r}; converted to 'set' placeholder.")
        converted_types.append({"node_id": clean_id, "source_type": str(rn.get("type")), "flowforge_type": ff_type})

        params = rn.get("parameters") or rn.get("config") or {}
        cfg: dict[str, Any] = dict(params) if isinstance(params, dict) else {}
        cfg.setdefault("label", orig_name)
        if ff_type == "set" and "values" not in cfg:
            cfg["values"] = {"migrated_from": str(rn.get("type", "external"))}
        elif ff_type == "http_request" and "url" not in cfg:
            cfg["url"] = "mock://migrated.local/endpoint"
        elif ff_type == "if_condition" and "field" not in cfg:
            cfg["field"] = "ok"

        pos = rn.get("position")
        if isinstance(pos, list) and len(pos) >= 2:
            position = {"x": float(pos[0]), "y": float(pos[1])}
        elif isinstance(pos, dict) and "x" in pos and "y" in pos:
            position = {"x": float(pos["x"]), "y": float(pos["y"])}
        else:
            position = {"x": 80.0 + idx * 250.0, "y": 180.0}

        mapped_nodes.append({"id": clean_id, "type": ff_type, "config": cfg, "position": position})

    # Ensure exactly one trigger node exists
    triggers = [n for n in mapped_nodes if n["type"] in TRIGGER_NODE_TYPES]
    if not triggers:
        trigger_node = {
            "id": "migrated_trigger",
            "type": "trigger",
            "config": {"label": "Migrated Trigger"},
            "position": {"x": 60.0, "y": 180.0},
        }
        mapped_nodes.insert(0, trigger_node)
        warnings.append("Inserted 'migrated_trigger' because source workflow had no explicit trigger node.")
    elif len(triggers) > 1:
        for extra_t in triggers[1:]:
            extra_t["type"] = "set"
            extra_t["config"]["values"] = {"converted_secondary_trigger": True}
            warnings.append(f"Converted secondary trigger {extra_t['id']!r} to 'set' to satisfy single-trigger DAG rule.")

    mapped_edges: list[dict[str, Any]] = []
    if isinstance(raw_edges, list) and raw_edges:
        for e in raw_edges:
            if isinstance(e, dict) and "source" in e and "target" in e:
                mapped_edges.append(
                    {
                        "source": name_to_id.get(str(e["source"]), str(e["source"])),
                        "target": name_to_id.get(str(e["target"]), str(e["target"])),
                        "source_handle": e.get("source_handle"),
                    }
                )
    elif isinstance(raw_connections, dict) and raw_connections:
        for src_name, conn_spec in raw_connections.items():
            src_id = name_to_id.get(src_name, src_name)
            main_branches = conn_spec.get("main") if isinstance(conn_spec, dict) else []
            if isinstance(main_branches, list):
                for b_idx, branch_targets in enumerate(main_branches):
                    if isinstance(branch_targets, list):
                        for t_obj in branch_targets:
                            if isinstance(t_obj, dict) and "node" in t_obj:
                                tgt_id = name_to_id.get(str(t_obj["node"]), str(t_obj["node"]))
                                handle = "true" if b_idx == 0 and len(main_branches) == 2 else ("false" if b_idx == 1 else None)
                                mapped_edges.append({"source": src_id, "target": tgt_id, "source_handle": handle})

    # Connect any orphan nodes linearly so the migrated graph is immediately runnable
    connected_targets = {e["target"] for e in mapped_edges}
    trigger_id = next(n["id"] for n in mapped_nodes if n["type"] in TRIGGER_NODE_TYPES)
    prev_id = trigger_id
    for n in mapped_nodes:
        nid = n["id"]
        if nid == trigger_id:
            continue
        if nid not in connected_targets:
            mapped_edges.append({"source": prev_id, "target": nid, "source_handle": None})
        prev_id = nid

    wf_def = WorkflowDefinition.model_validate({"schema_version": "1.0", "nodes": mapped_nodes, "edges": mapped_edges})
    return {
        "name": name,
        "definition": wf_def.model_dump(mode="json"),
        "migration_report": {
            "mapped_node_count": len(mapped_nodes),
            "mapped_edge_count": len(mapped_edges),
            "converted_types": converted_types,
            "warnings": warnings,
        },
    }
