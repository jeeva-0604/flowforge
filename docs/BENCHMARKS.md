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
