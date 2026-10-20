# FlowForge Community — Reproducible Performance Benchmarks (`v0.3.0`)

Command executed:
```bash
PYTHONPATH=backend python3 backend/benchmarks/run_benchmarks.py
```

## Measured Results (Python 3.11.2, Linux x86_64 Sandbox VM)

| Workload | Metric | Measured Result |
|---|---|---|
| **10-Node DAG Validation** (200 iterations) | p50 / p95 / Mean Latency | `0.1354 ms` / `0.2608 ms` / `0.1575 ms` |
| **50-Node DAG Validation** (200 iterations) | p50 / p95 / Mean Latency | `0.4585 ms` / `0.8072 ms` / `0.5182 ms` |
| **10-Node Workflow Execution** (100 runs = 1,000 node executions with traces & secret masking) | p50 / p95 / Mean Latency | `3.0622 ms` / `5.8441 ms` / `3.4825 ms` |
| **Node Execution Throughput** | Sustained Nodes / Sec | `2,868.3 nodes/sec` |
| **Durable Queue Enqueue** (30 jobs) | p50 / Mean Latency | `0.7718 ms` / `0.7490 ms` |
| **Worker Claim + Execute + Persist** (30 jobs) | p50 / Mean Latency | `49.2559 ms` / `49.7103 ms` |
| **Engine Memory Footprint** (`tracemalloc`) | Current / Peak Traced Memory | `216.35 KB` / `300.48 KB` |


## v0.4.0 Verification Run (Different Runtime Environment)

This follow-up run was captured after the Milestone 4 implementation in a Python 3.13.5 Linux sandbox using the local SQLite test path. It is **not directly comparable** to the historical Python 3.11 baseline above and does not measure live PostgreSQL or multi-worker contention.

| Workload | Metric | Measured Result |
|---|---|---|
| **10-Node DAG Validation** | p50 / p95 / Mean Latency | `0.0588 ms` / `0.0891 ms` / `0.0628 ms` |
| **50-Node DAG Validation** | p50 / p95 / Mean Latency | `0.1980 ms` / `0.2587 ms` / `0.2078 ms` |
| **10-Node Workflow Execution** | p50 / p95 / Mean Latency | `1.4978 ms` / `1.7426 ms` / `1.5524 ms` |
| **Node Execution Throughput** | Sustained Nodes / Sec | `6,436.5 nodes/sec` |
| **Durable Queue Enqueue** | p50 / Mean Latency | `2.1896 ms` / `2.3760 ms` |
| **Worker Claim + Execute + Persist** | p50 / Mean Latency | `27.2727 ms` / `29.0397 ms` |
| **Engine Memory Footprint** | Current / Peak Traced Memory | `5,614.38 KB` / `5,703.81 KB` |
