"""Reproducible performance benchmarks for FlowForge Community."""
from __future__ import annotations

import json
from pathlib import Path
import platform
import statistics
import sys
import time
import tracemalloc

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from flowforge.db import Base, make_engine, sessionmaker
from flowforge.engine import execute_workflow_detailed, validate_workflow_graph
from flowforge.models import Workflow
from flowforge.schemas import WorkflowDefinition
from flowforge.worker import enqueue_execution_job, process_next_job


def make_chain_workflow(num_nodes: int) -> WorkflowDefinition:
    nodes = [{"id": "n_0", "type": "trigger", "position": {"x": 0, "y": 0}}]
    edges = []
    for i in range(1, num_nodes - 1):
        nodes.append(
            {
                "id": f"n_{i}",
                "type": "set",
                "position": {"x": i * 200, "y": 0},
                "config": {"values": {f"step_{i}": i}},
            }
        )
        edges.append({"source": f"n_{i - 1}", "target": f"n_{i}"})
    nodes.append({"id": f"n_{num_nodes - 1}", "type": "output", "position": {"x": num_nodes * 200, "y": 0}})
    edges.append({"source": f"n_{num_nodes - 2}", "target": f"n_{num_nodes - 1}"})
    return WorkflowDefinition.model_validate({"nodes": nodes, "edges": edges})


def run_suite() -> dict:
    tracemalloc.start()

    wf_10 = make_chain_workflow(10)
    wf_50 = make_chain_workflow(50)

    # 1. Validation benchmark
    val_10_times = []
    for _ in range(200):
        t0 = time.perf_counter()
        validate_workflow_graph(wf_10)
        val_10_times.append((time.perf_counter() - t0) * 1000)

    val_50_times = []
    for _ in range(200):
        t0 = time.perf_counter()
        validate_workflow_graph(wf_50)
        val_50_times.append((time.perf_counter() - t0) * 1000)

    # 2. Execution throughput benchmark (10-node workflow x 100 runs = 1,000 node executions)
    exec_times = []
    t_batch_start = time.perf_counter()
    for i in range(100):
        t0 = time.perf_counter()
        res = execute_workflow_detailed(wf_10, {"run": i})
        assert res["status"] == "succeeded"
        exec_times.append((time.perf_counter() - t0) * 1000)
    total_batch_sec = time.perf_counter() - t_batch_start
    nodes_per_sec = round((10 * 100) / total_batch_sec, 1)

    # 3. Database & Queue latency benchmark
    bench_engine = make_engine("sqlite://")
    Base.metadata.create_all(bind=bench_engine)
    BenchSession = sessionmaker(bind=bench_engine)

    db_write_times = []
    queue_roundtrip_times = []
    with BenchSession() as session:
        wf_obj = Workflow(name="Bench WF", definition=wf_10.model_dump(mode="json"))
        session.add(wf_obj)
        session.commit()
        session.refresh(wf_obj)

        for i in range(30):
            t0 = time.perf_counter()
            job = enqueue_execution_job(session, wf_obj.id, {"idx": i})
            db_write_times.append((time.perf_counter() - t0) * 1000)

            t1 = time.perf_counter()
            done = process_next_job(session, worker_id="bench-worker")
            assert done is not None and done.status == "completed"
            queue_roundtrip_times.append((time.perf_counter() - t1) * 1000)

    current_mem, peak_mem = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    return {
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
        },
        "validation_10_nodes_ms": {
            "p50": round(statistics.median(val_10_times), 4),
            "p95": round(sorted(val_10_times)[int(0.95 * len(val_10_times))], 4),
            "mean": round(statistics.mean(val_10_times), 4),
        },
        "validation_50_nodes_ms": {
            "p50": round(statistics.median(val_50_times), 4),
            "p95": round(sorted(val_50_times)[int(0.95 * len(val_50_times))], 4),
            "mean": round(statistics.mean(val_50_times), 4),
        },
        "execution_10_nodes_ms": {
            "p50": round(statistics.median(exec_times), 4),
            "p95": round(sorted(exec_times)[int(0.95 * len(exec_times))], 4),
            "mean": round(statistics.mean(exec_times), 4),
            "throughput_nodes_per_sec": nodes_per_sec,
        },
        "queue_enqueue_ms": {
            "p50": round(statistics.median(db_write_times), 4),
            "mean": round(statistics.mean(db_write_times), 4),
        },
        "worker_claim_and_execute_ms": {
            "p50": round(statistics.median(queue_roundtrip_times), 4),
            "mean": round(statistics.mean(queue_roundtrip_times), 4),
        },
        "memory_kb": {
            "current_kb": round(current_mem / 1024, 2),
            "peak_kb": round(peak_mem / 1024, 2),
        },
    }


if __name__ == "__main__":
    print(json.dumps(run_suite(), indent=2))
