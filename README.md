# PipelineGuard

**Live (graph):** [https://ali-pipelineguard.vercel.app](https://ali-pipelineguard.vercel.app)

Data pipelines fail silently. A job reports `status: SUCCEEDED` with `records_processed: 0` — no alert, no pager, just wrong data downstream until someone notices the numbers are off three days later. Standard monitoring tools catch crashes; they do not catch jobs that succeed at doing nothing.

PipelineGuard is an async SaaS backend that monitors pipelines for silent failures (succeeded + zero records), latency drift (execution time growing against a rolling p50/p95 baseline), and consecutive failure patterns — with full multi-tenancy, RS256 JWT auth, and Prometheus metrics.

> **Current state:** The core detection logic, RBAC, billing, GDPR, and Celery task infrastructure are fully implemented and tested (346 tests). The dependency-injection container wires **in-memory repositories** by default — `src/infrastructure/database/pipeline_repositories.py` contains the SQLAlchemy implementations but they are not yet wired into the container. Alerts are persisted but Slack/webhook delivery is not connected to the alert pipeline.

---

## Architecture

```
HTTP Client
    |
    v
FastAPI Presentation Layer  (src/presentation/)
    |  RS256 JWT + RBAC middleware
    |  tenant_id injected into every request
    v
Application Services  (src/application/services/)
    |  PipelineService, AuthService, BillingService, GDPRService
    |  coordinates domain logic; depends only on Protocol port interfaces
    v
Domain Layer  (src/domain/)
    |  Pipeline, JobExecution, LatencyRecord, PipelineAlert  (pure dataclasses)
    |  DriftAnalyzer  -- rolling p50/p95 + z-score anomaly detection
    |  AlertDeduplicator  -- cooldown-window suppression
    |  SummaryGenerator  -- plain-English weekly summaries
    v
Infrastructure Layer  (src/infrastructure/)
    |  JWTHandler (RS256 sign/verify)
    |  RBAC (VIEWER < MEMBER < ADMIN < OWNER, permission-level checks)
    |  SQLAlchemy ORM models + Alembic migrations (3 versioned files)
    |  Redis token store + cache manager
    |  Celery tasks (billing_tasks, gdpr_tasks, pipeline_tasks)
    v
Storage: PostgreSQL (primary) + Redis (cache/sessions)
Observability: Prometheus metrics via prometheus-client
```

**Silent failure detection flow:** every `JobExecution` reported as `SUCCEEDED` with `records_processed == 0`, or with a non-empty `error_message`, is immediately re-classified as `SILENT_FAILURE` and triggers a `CRITICAL` alert.

**Latency drift flow:** each execution duration is compared against the last 100 historical durations. If `current > p50 * 1.25`, the job is flagged as drifting. If `|z-score| > 2.5`, it is flagged as an anomaly. Both thresholds are configurable per pipeline.

---

## Key Design Decisions

**Clean Architecture with Protocol-based ports, not direct ORM coupling.** Application services depend on `Protocol` interfaces (`PipelineRepository`, `JobExecutionRepository`), not on SQLAlchemy sessions. This lets unit tests inject fast in-memory fakes while the integration layer swaps in real DB adapters. Tradeoff: more indirection, more files, and two implementations to keep in sync.

**RS256 asymmetric JWT, not HS256 symmetric.** Services that only verify tokens (e.g. a read-only analytics service) need only the public key. They cannot forge tokens. With HS256, sharing the key means sharing the ability to mint tokens. Tradeoff: RSA key-pair management overhead at deploy time.

**Tenant isolation via `tenant_id` claim in JWT, not per-tenant schema.** Every query is filtered by `tenant_id` extracted from the verified token. Per-tenant PostgreSQL schemas would give stronger isolation at the DDL level, but require a migration per new tenant and make cross-tenant reporting impossible. The shared-schema approach is simpler to operate at the cost of needing query discipline throughout the codebase.

**Alert deduplication in-process, not in the database.** The `AlertDeduplicator` uses an in-memory `dict[str, float]` keyed by `pipeline_id:alert_type` with a configurable cooldown window (default 300 s). No DB round-trip on every execution event. Tradeoff: state does not survive restarts, and two API instances would have independent cooldown windows.

**Celery for background tasks, not FastAPI `BackgroundTasks`.** Billing cycles, GDPR export jobs, and weekly summary generation are long-running and must survive web process restarts. FastAPI `BackgroundTasks` are tied to the request lifecycle. Tradeoff: requires a Redis broker and a separate Celery worker process in the deployment.

---

## Tech Stack

| Component | Justification |
|---|---|
| **FastAPI** | Native async, automatic OpenAPI generation, dependency injection for per-request auth context |
| **SQLAlchemy 2 (async)** | Declarative ORM with Alembic-managed migrations; async sessions via asyncpg |
| **asyncpg** | PostgreSQL wire protocol driver; significantly faster than psycopg2 for async workloads |
| **python-jose (RS256)** | JOSE-compliant JWT library with asymmetric key support; access tokens expire in 15 min, refresh tokens in 7 days |
| **argon2-cffi** | Password hashing; Argon2id is the current OWASP recommendation over bcrypt for new systems |
| **Celery + Redis** | Distributed task queue for jobs that must survive API restarts and be retriable |
| **Prometheus-client** | Exposes metrics in the standard scrape format compatible with Grafana/Prometheus stacks |
| **structlog** | Structured JSON log output with bound request context (tenant_id, request_id) |
| **Alembic** | Schema migrations versioned alongside application code; three migration files covering the full schema |
| **pytest-asyncio + pytest-xdist** | Async test runner with parallel execution; test suite is organized into unit, integration, contract, and load categories |

---

## Running Locally

```bash
git clone https://github.com/Aliipou/PipelineGuard.git
cd PipelineGuard

# Generate RSA key pair for JWT signing
openssl genrsa -out private_key.pem 2048
openssl rsa -in private_key.pem -pubout -out public_key.pem

# Install
pip install -e ".[dev]"

# Run unit tests (no external services required)
PYTHONPATH=src pytest tests/unit/ -v

# Start API (in-memory repositories; no database needed for smoke testing)
PYTHONPATH=src uvicorn src.presentation.main:app --reload --port 8000

# Alternatively, with Docker (single-container)
docker compose up
```

Integration tests require running Postgres and Redis:

```bash
docker run -d -e POSTGRES_PASSWORD=test -p 5432:5432 postgres:16-alpine
docker run -d -p 6379:6379 redis:7-alpine

PYTHONPATH=src pytest tests/integration/ -v
```

---

## Deployment

Minimum required infrastructure:

- **PostgreSQL 16+** — primary data store; run `alembic upgrade head` before first start
- **Redis 7+** — Celery task broker, refresh token store, response cache
- **Celery worker** — separate process consuming from Redis: `celery -A src.application.tasks.celery_app worker --loglevel=info`
- **RSA key pair** — private key for the API process; distribute only the public key to downstream services that verify tokens

For multi-instance production: the in-memory `AlertDeduplicator` and in-memory repositories must be replaced with their Redis/SQLAlchemy equivalents. Running two API instances with the current defaults would result in divergent deduplication state and data loss on any restart.

---

## Known Limitations / TODO

- **In-memory repositories are the default.** All data is lost on process restart. The SQLAlchemy-backed implementations in `src/infrastructure/database/pipeline_repositories.py` need to be wired into `src/infrastructure/container.py`.
- **Alert delivery is not connected.** Slack notifier and webhook classes exist in the infrastructure layer but are not attached to the alert pipeline. Alerts are persisted in the repository but never sent externally.
- **No horizontal-scale-safe alert deduplication.** The `AlertDeduplicator` is in-process; two API instances would double-fire alerts for the same pipeline.
- **Single-container Docker Compose.** The provided `docker-compose.yml` starts only the API container; it expects `.env` to point at externally-run Postgres and Redis.
- **Coverage threshold is 55%.** Reflects the gap between well-tested domain/application code and the not-yet-integrated infrastructure wiring.
