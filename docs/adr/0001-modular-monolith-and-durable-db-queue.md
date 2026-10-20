# ADR 0001: Modular Monolith with Database-Backed Durable Queue

- **Status:** Accepted (2026-10-20)
- **Context:** Self-hosted users on Windows laptops and Linux servers need reliable background execution, retries, and crash recovery without mandatory Redis/RabbitMQ infrastructure overhead.
- **Decision:** Keep the control plane, engine, SDK, skills, and worker in a modular Python package backed by PostgreSQL (with SQLite compatibility for isolated tests). Store background jobs in `execution_jobs` with worker heartbeats, lease timeouts, exponential backoff, and dead-letter states.
- **Consequences:** Zero extra broker dependencies for initial self-hosted deployments; clean separation allows optional Redis worker adapters later without changing workflow definitions.
