import pytest
from pydantic import ValidationError
from flowforge.engine import WorkflowValidationError, execute_workflow, topological_order
from flowforge.schemas import WorkflowDefinition


def demo_definition():
    return WorkflowDefinition.model_validate({
        "nodes": [
            {"id": "start", "type": "trigger"},
            {"id": "enrich", "type": "set", "config": {"values": {"greeting": "hello", "count": 3}}},
            {"id": "finish", "type": "output"},
        ],
        "edges": [
            {"source": "start", "target": "enrich"},
            {"source": "enrich", "target": "finish"},
        ],
    })


def test_three_node_workflow_executes_in_order_and_merges_values():
    definition = demo_definition()
    assert topological_order(definition) == ["start", "enrich", "finish"]
    assert execute_workflow(definition, {"name": "Jeeva"}) == {
        "name": "Jeeva", "greeting": "hello", "count": 3
    }


def test_cycle_is_rejected():
    definition = WorkflowDefinition.model_validate({
        "nodes": [
            {"id": "start", "type": "trigger"},
            {"id": "set", "type": "set", "config": {"values": {}}},
        ],
        "edges": [{"source": "start", "target": "set"}, {"source": "set", "target": "start"}],
    })
    with pytest.raises(WorkflowValidationError, match="cycle"):
        topological_order(definition)


def test_unknown_node_reference_is_rejected():
    definition = WorkflowDefinition.model_validate({
        "nodes": [{"id": "start", "type": "trigger"}],
        "edges": [{"source": "start", "target": "missing"}],
    })
    with pytest.raises(WorkflowValidationError, match="unknown node"):
        topological_order(definition)


def test_exactly_one_trigger_is_required():
    with pytest.raises(ValidationError, match="exactly one trigger"):
        WorkflowDefinition.model_validate({"nodes": [{"id": "one", "type": "set"}], "edges": []})


def test_trigger_cannot_have_incoming_edge():
    definition = WorkflowDefinition.model_validate({
        "nodes": [
            {"id": "start", "type": "trigger"},
            {"id": "other", "type": "set", "config": {"values": {}}},
        ],
        "edges": [{"source": "other", "target": "start"}],
    })
    with pytest.raises(WorkflowValidationError, match="Trigger node cannot have incoming"):
        topological_order(definition)


def test_disconnected_node_is_rejected():
    definition = WorkflowDefinition.model_validate({
        "nodes": [
            {"id": "start", "type": "trigger"},
            {"id": "finish", "type": "output"},
            {"id": "orphan", "type": "set", "config": {"values": {}}},
        ],
        "edges": [{"source": "start", "target": "finish"}],
    })
    with pytest.raises(WorkflowValidationError, match="reachable from the trigger"):
        topological_order(definition)
