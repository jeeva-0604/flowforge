"""Workflow Test Suite & Assertion Runner for FlowForge Community."""
from __future__ import annotations

from typing import Any
from .engine import _lookup_path, execute_workflow_detailed
from .models import WorkflowTestCase, utc_now
from .schemas import WorkflowDefinition


def evaluate_test_case(
    definition: WorkflowDefinition,
    test_case: WorkflowTestCase,
    *,
    credentials_map: dict[str, dict[str, Any]] | None = None,
    variables_map: dict[str, Any] | None = None,
    secret_values: list[str] | None = None,
) -> dict[str, Any]:
    """Run a single WorkflowTestCase and evaluate all configured assertions."""
    detailed = execute_workflow_detailed(
        definition,
        test_case.input_data or {},
        credentials_map=credentials_map,
        variables_map=variables_map,
        pinned_node_outputs=test_case.pinned_node_outputs or {},
        secret_values=secret_values,
    )
    assertion_results: list[dict[str, Any]] = []
    all_passed = True

    assertions = test_case.assertions or []
    if not assertions:
        # Default assertion: workflow succeeded
        ok = detailed["status"] == "succeeded"
        all_passed = ok
        assertion_results.append(
            {
                "kind": "status_equals",
                "target": "status",
                "expected": "succeeded",
                "actual": detailed["status"],
                "passed": ok,
            }
        )
    else:
        for raw_a in assertions:
            kind = raw_a.get("kind", "status_equals")
            target = str(raw_a.get("target") or "")
            expected = raw_a.get("expected")
            if kind == "status_equals":
                actual = detailed["status"]
                ok = actual == expected
            elif kind == "field_equals":
                actual = _lookup_path(detailed.get("result_data") or {}, target)
                ok = actual == expected
            elif kind == "field_exists":
                actual = _lookup_path(detailed.get("result_data") or {}, target)
                ok = (actual is not None) is bool(expected)
            elif kind == "node_status_equals":
                node_map = {nr["node_id"]: nr["status"] for nr in detailed.get("node_runs") or []}
                actual = node_map.get(target)
                ok = actual == expected
            else:
                actual = None
                ok = False
            if not ok:
                all_passed = False
            assertion_results.append(
                {
                    "kind": kind,
                    "target": target,
                    "expected": expected,
                    "actual": actual,
                    "passed": ok,
                }
            )

    return {
        "test_case_id": test_case.id,
        "name": test_case.name,
        "passed": all_passed,
        "execution_status": detailed["status"],
        "result_data": detailed["result_data"],
        "assertions": assertion_results,
    }


def run_workflow_test_suite(
    session: Any,
    workflow_id: str,
    definition: WorkflowDefinition,
    *,
    credentials_map: dict[str, dict[str, Any]] | None = None,
    variables_map: dict[str, Any] | None = None,
    secret_values: list[str] | None = None,
) -> dict[str, Any]:
    """Run all saved WorkflowTestCases for a workflow and persist their status."""
    cases = (
        session.query(WorkflowTestCase)
        .filter(WorkflowTestCase.workflow_id == workflow_id)
        .order_by(WorkflowTestCase.created_at)
        .all()
    )
    results = []
    passed_count = 0
    for tc in cases:
        outcome = evaluate_test_case(
            definition,
            tc,
            credentials_map=credentials_map,
            variables_map=variables_map,
            secret_values=secret_values,
        )
        tc.last_status = "passed" if outcome["passed"] else "failed"
        tc.last_run_at = utc_now()
        session.add(tc)
        if outcome["passed"]:
            passed_count += 1
        results.append(outcome)
    session.commit()
    return {
        "workflow_id": workflow_id,
        "total_cases": len(cases),
        "passed_cases": passed_count,
        "failed_cases": len(cases) - passed_count,
        "all_passed": passed_count == len(cases),
        "results": results,
    }
