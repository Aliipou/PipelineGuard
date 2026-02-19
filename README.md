# PipelineGuard

API-first monitoring layer for async data pipelines. Detects silent job failures, tracks latency drift with percentile baselines, and generates weekly plain-English risk summaries for engineering leadership.

Built on an EU-grade multi-tenant cloud platform with cost-aware billing, GDPR-native compliance, and production-grade SaaS architecture.

## The Problem

Async data pipelines pulling from 100+ marketing platforms (Google Ads, Facebook, TikTok, etc.) into analytics tools have two failure modes that go unnoticed:

1. **Silent failures** — jobs report "success" but pull zero records. No alerts fire.
2. **Latency drift** — pipeline durations creep up 30-40% over weeks. Nobody notices until a client complains.

PipelineGuard catches both automatically.

## How It Works

### Silent Failure Detection

```
POST /api/v1/tenants/{id}/pipelines/{pid}/executions
{
  "status": "SUCCEEDED",
  "startedAt": "2026-02-18T03:00:00Z",
  "finishedAt": "2026-02-18T03:02:05Z",
  "durationSeconds": 125.3,
  "recordsProcessed": 0
}
```

Response — silent failure auto-detected:

```json
{
  "id": "...",
  "pipelineId": "...",
  "status": "SILENT_FAILURE",
  "isSilentFailure": true,
  "recordsProcessed": 0,
  "durationSeconds": 125.3
}
```

A job is flagged as `SILENT_FAILURE` when:
- Status is `SUCCEEDED` but `records_processed == 0`
- Status is `SUCCEEDED` but `error_message` is non-empty

Generates a `CRITICAL` alert immediately.

### Latency Drift Detection

Compares each job's duration against the **p50 (median) baseline** from recent history. If the current duration exceeds p50 by more than **25%**, a `WARNING` alert is generated.

```
p50 baseline = 100s
current run  = 134s  (+34% above baseline)
→ WARNING: latency drift detected
```

A Celery task runs hourly to check all pipelines against their baselines.

### Consecutive Failure Alerting

Tracks the last N executions per pipeline. If consecutive failures reach the `failure_threshold` (default: 3), a `CRITICAL` alert fires.

### Weekly CTO Summary

Generated every Monday at 08:00 UTC (or on-demand via `POST /summary/generate`):

```
Weekly Pipeline Health Report (Feb 10 - Feb 17, 2026)

RELIABILITY: 94.2% success rate (847 jobs, 49 failures)
SILENT FAILURES: 3 job(s) failed without alerting anyone. This is your highest risk.
LATENCY DRIFT: 2 pipeline(s) are trending slower (avg +34.7% vs baseline).

TOP RISKS:
  1. 'Facebook Ads -> BigQuery' silent failure on Feb 14 at 03:15 UTC — 0 records.
  2. 'TikTok Ads -> BigQuery' is +41.2% slower than baseline.
  3. 'LinkedIn Ads -> Redshift' is +28.3% slower than baseline.

RECOMMENDATION: Investigate flagged pipelines before they impact downstream analytics.
```

## Integration

PipelineGuard drops into existing pipeline infrastructure via a single webhook on each job completion:

```bash
# 1. Register a pipeline
curl -X POST /api/v1/tenants/{id}/pipelines \
  -d '{"name": "Google Ads -> BigQuery", "source": "Google Ads", "destination": "BigQuery"}'

# 2. Report each job execution (add to your pipeline's post-run hook)
curl -X POST /api/v1/tenants/{id}/pipelines/{pid}/executions \
  -d '{"status": "SUCCEEDED", "startedAt": "...", "durationSeconds": 125.3, "recordsProcessed": 4821}'

# 3. Check alerts
curl /api/v1/tenants/{id}/alerts

# 4. Get weekly summary
curl /api/v1/tenants/{id}/summary
```

## Architecture

```
src/
  domain/           # Business rules, models, domain services (zero dependencies)
  application/      # Use cases, orchestration, Celery tasks
  infrastructure/   # Database, auth, observability, external adapters
  presentation/     # FastAPI endpoints, middleware, schemas
```

**Clean Architecture** with strict dependency inversion: `Presentation -> Application -> Domain <- Infrastructure`.

### Key Design Decisions

- **Schema-per-tenant PostgreSQL isolation** for data residency and GDPR compliance
- **RS256 JWT** (asymmetric) with 15-minute access tokens, 7-day refresh tokens
- **Argon2id** password hashing (OWASP recommended)
- **RFC 9457 Problem Details** for all error responses
- **Tamper-evident audit log** with SHA-256 hash chain
- **Cost anomaly detection** via z-score analysis (2.5 sigma threshold, 7-day rolling window)
- **Percentile-based drift detection** — p50 baseline with 25% threshold (robust against outliers, unlike z-score)

## Tech Stack

| Layer          | Technology                                  |
|----------------|---------------------------------------------|
| API Framework  | FastAPI 0.110+                              |
| Database       | PostgreSQL 16 (schema-per-tenant)           |
| ORM            | SQLAlchemy 2.0+ (async)                     |
| Migrations     | Alembic                                     |
| Task Queue     | Celery 5.3+ with Redis broker               |
| Auth           | python-jose (RS256), argon2-cffi            |
| Observability  | Prometheus, structlog (JSON), Loki, Grafana |
| Validation     | Pydantic v2                                 |
| Python         | 3.12+                                       |

## Quick Start

### Prerequisites

- Python 3.12+
- PostgreSQL 16+
- Redis 7+

### Local Development

```bash
# Install dependencies
pip install -e ".[dev]"

# Configure environment
export APP_POSTGRES_HOST=localhost
export APP_POSTGRES_USER=postgres
export APP_POSTGRES_PASSWORD=postgres
export APP_POSTGRES_DB=eu_multitenant
export APP_REDIS_URL=redis://localhost:6379/0
export APP_JWT_PRIVATE_KEY="$(cat private.pem)"
export APP_JWT_PUBLIC_KEY="$(cat public.pem)"

# Run database migrations
alembic upgrade head

# Start the API server
uvicorn presentation.main:app --reload --host 0.0.0.0 --port 8000

# Start Celery worker (separate terminal)
celery -A application.tasks.celery_app worker --loglevel=info -Q tenants,billing,gdpr,pipelines

# Start Celery beat scheduler (separate terminal)
celery -A application.tasks.celery_app beat --loglevel=info
```

### Docker

```bash
cd deploy/docker
docker compose up -d
```

Services: API (:8000), PostgreSQL (:5432), Redis (:6379), Prometheus (:9090), Grafana (:3000), Loki (:3100).

## API Endpoints

### PipelineGuard

| Method | Path                                              | Description           |
|--------|---------------------------------------------------|-----------------------|
| `POST` | `/api/v1/tenants/{id}/pipelines`                  | Register pipeline     |
| `GET`  | `/api/v1/tenants/{id}/pipelines`                  | List pipelines        |
| `GET`  | `/api/v1/tenants/{id}/pipelines/{pid}`            | Get pipeline detail   |
| `POST` | `/api/v1/tenants/{id}/pipelines/{pid}/executions` | Report job execution  |
| `GET`  | `/api/v1/tenants/{id}/pipelines/{pid}/executions` | List executions       |
| `GET`  | `/api/v1/tenants/{id}/pipelines/{pid}/latency`    | Latency history       |
| `GET`  | `/api/v1/tenants/{id}/alerts`                     | List alerts           |
| `POST` | `/api/v1/tenants/{id}/alerts/{aid}/acknowledge`   | Acknowledge alert     |
| `GET`  | `/api/v1/tenants/{id}/summary`                    | Latest weekly summary |
| `POST` | `/api/v1/tenants/{id}/summary/generate`           | Generate summary now  |

### Tenants

| Method   | Path                             | Description              |
|----------|----------------------------------|--------------------------|
| `POST`   | `/api/v1/tenants`                | Create tenant            |
| `GET`    | `/api/v1/tenants`                | List tenants (paginated) |
| `GET`    | `/api/v1/tenants/{id}`           | Get tenant details       |
| `PATCH`  | `/api/v1/tenants/{id}`           | Update tenant            |
| `POST`   | `/api/v1/tenants/{id}/suspend`   | Suspend tenant           |
| `POST`   | `/api/v1/tenants/{id}/activate`  | Reactivate tenant        |
| `DELETE` | `/api/v1/tenants/{id}`           | Deprovision tenant       |

### Authentication

| Method | Path                    | Description         |
|--------|-------------------------|---------------------|
| `POST` | `/api/v1/auth/register` | Register user       |
| `POST` | `/api/v1/auth/login`    | Login (get tokens)  |
| `POST` | `/api/v1/auth/refresh`  | Refresh tokens      |
| `POST` | `/api/v1/auth/logout`   | Logout              |
| `GET`  | `/api/v1/auth/me`       | Current user        |

### Billing

| Method | Path                                     | Description          |
|--------|------------------------------------------|----------------------|
| `GET`  | `/api/v1/tenants/{id}/costs`             | Cost breakdown       |
| `GET`  | `/api/v1/tenants/{id}/costs/current`     | Current period costs |
| `GET`  | `/api/v1/tenants/{id}/costs/projection`  | Monthly projection   |
| `GET`  | `/api/v1/tenants/{id}/invoices`          | List invoices        |
| `GET`  | `/api/v1/tenants/{id}/invoices/{inv_id}` | Invoice detail       |
| `GET`  | `/api/v1/tenants/{id}/anomalies`         | Cost anomalies       |

### GDPR Compliance

| Method | Path                                        | Description          |
|--------|---------------------------------------------|----------------------|
| `POST` | `/api/v1/tenants/{id}/gdpr/export`          | Request data export  |
| `GET`  | `/api/v1/tenants/{id}/gdpr/export/{job_id}` | Export status        |
| `POST` | `/api/v1/tenants/{id}/gdpr/erase`           | Right to erasure     |
| `GET`  | `/api/v1/tenants/{id}/gdpr/retention`       | Get retention policy |
| `PUT`  | `/api/v1/tenants/{id}/gdpr/retention`       | Update retention     |
| `GET`  | `/api/v1/tenants/{id}/audit-log`            | Audit trail          |

### Operations

| Method | Path       | Description  |
|--------|------------|--------------|
| `GET`  | `/health`  | Health check |
| `GET`  | `/metrics` | Prometheus   |

## Background Tasks

| Task                        | Queue      | Schedule         | Purpose                                     |
|-----------------------------|------------|------------------|---------------------------------------------|
| `scan_silent_failures`      | pipelines  | Every 15 min     | Re-scan recent jobs for silent failures     |
| `check_latency_drift`      | pipelines  | Hourly           | Compare all pipelines against baselines     |
| `generate_weekly_summaries` | pipelines  | Monday 08:00 UTC | Plain-English CTO summary per tenant        |
| `aggregate_daily_costs`     | billing    | Daily            | Calculate cost records for all tenants      |
| `detect_anomalies`          | billing    | Daily            | Z-score anomaly detection sweep             |
| `generate_monthly_invoices` | billing    | Monthly          | Generate invoices for previous month        |
| `run_retention_cleanup_all` | gdpr       | Daily            | Enforce data retention policies             |

## Database Schema

### Public Schema (shared)

| Table               | Purpose                                         |
|---------------------|-------------------------------------------------|
| `tenants`           | Tenant registry                                 |
| `audit_log`         | Tamper-evident hash-chained audit trail         |
| `pipelines`         | Registered async data pipelines                 |
| `job_executions`    | Individual job runs with silent failure flags   |
| `latency_records`   | Latency measurements with p50/p95 baselines     |
| `pipeline_alerts`   | Generated alerts (silent, drift, consecutive)   |
| `weekly_summaries`  | Weekly CTO reports stored for history           |

### Per-Tenant Schemas (`tenant_{slug}`)

| Table            | Purpose                        |
|------------------|--------------------------------|
| `users`          | Tenant users with RBAC roles   |
| `usage_records`  | Raw resource consumption data  |
| `cost_records`   | Aggregated cost line-items     |
| `invoices`       | Monthly invoices               |

## Tenant Lifecycle

```
PENDING -> PROVISIONING -> ACTIVE -> SUSPENDED -> DEPROVISIONING -> DELETED
                              |          ^
                              +----------+
```

Each transition is validated by the domain `TenantLifecycleService` and recorded in the tamper-evident audit log.

## GDPR Compliance

- **Article 17 (Right to Erasure)**: 7-step pipeline: freeze tenant, export backup, cascade delete data, drop schema, purge caches, create audit entry, transition to DELETED
- **Article 20 (Data Portability)**: Export all tenant data as JSON/CSV/XML archive with manifest
- **Retention Policies**: Configurable per-tenant with soft-delete grace periods and hard-delete enforcement

## Testing

```bash
# All tests
pytest -v

# Unit tests only
pytest tests/unit/ -v

# Integration tests
pytest tests/integration/ -v

# Contract tests (API schema validation)
pytest tests/contract/ -v

# Load tests
locust -f tests/load/locustfile.py --host http://localhost:8000

# Coverage report
pytest --cov=src --cov-report=term-missing
```

### Test Summary

| Category    | Count | Focus                                              |
|-------------|-------|----------------------------------------------------|
| Unit        | 271   | Domain models, services, infrastructure, pipelines  |
| Integration | 41    | Repositories, schema manager, lifecycle             |
| Contract    | 29    | OpenAPI schema, RFC 9457 validation, PipelineGuard  |
| **Total**   | **341** |                                                   |

## Code Quality

```bash
ruff check src/                        # Linting
black --check src/                     # Formatting
mypy src/ --ignore-missing-imports     # Type checking
bandit -r src/                         # Security scanning
```

## Deployment

### Kubernetes

```bash
kubectl apply -f deploy/k8s/namespace.yml
kubectl apply -f deploy/k8s/
```

### Terraform (Hetzner Cloud)

```bash
cd deploy/terraform
terraform init && terraform plan && terraform apply
```

## Configuration

All settings via environment variables with `APP_` prefix (see `src/infrastructure/settings.py`).

| Variable                       | Default                    | Description             |
|--------------------------------|----------------------------|-------------------------|
| `APP_POSTGRES_HOST`            | `localhost`                | PostgreSQL host         |
| `APP_POSTGRES_PORT`            | `5432`                     | PostgreSQL port         |
| `APP_POSTGRES_DB`              | `eu_multitenant`           | Database name           |
| `APP_REDIS_URL`                | `redis://localhost:6379/0` | Redis connection URL    |
| `APP_JWT_PRIVATE_KEY`          | -                          | RS256 private key (PEM) |
| `APP_JWT_PUBLIC_KEY`           | -                          | RS256 public key (PEM)  |
| `APP_JWT_ISSUER`               | `eu-multi-tenant-platform` | JWT issuer claim        |
| `APP_JWT_ACCESS_TOKEN_MINUTES` | `15`                       | Access token TTL        |
| `APP_JWT_REFRESH_TOKEN_DAYS`   | `7`                        | Refresh token TTL       |
| `APP_CELERY_BROKER_URL`        | `redis://localhost:6379/1` | Celery broker           |
| `APP_LOG_LEVEL`                | `INFO`                     | Log level               |

## Project Structure

```
src/
├── domain/
│   ├── models/          pipeline.py, tenant.py, user.py, billing.py, audit.py
│   ├── services/        drift_analyzer.py, summary_generator.py, tenant_lifecycle.py, cost_calculator.py
│   ├── events/          tenant_events.py
│   └── exceptions/      tenant_exceptions.py
├── application/
│   ├── services/        pipeline_service.py, tenant_service.py, auth_service.py, billing_service.py, gdpr_service.py
│   ├── tasks/           pipeline_tasks.py, tenant_tasks.py, billing_tasks.py, gdpr_tasks.py, celery_app.py
│   └── schemas/         pagination.py
├── infrastructure/
│   ├── database/        models.py, migrations/
│   ├── auth/            jwt_handler.py, password_handler.py
│   ├── observability/   metrics.py, logging_config.py
│   ├── adapters.py      In-memory repositories (swap for real DB in prod)
│   ├── container.py     Dependency injection container
│   └── settings.py      Environment-based configuration
└── presentation/
    ├── api/v1/          pipelines.py, tenants.py, auth.py, billing.py, gdpr.py, schemas.py
    ├── middleware/       tenant_context.py, request_logging.py
    └── main.py          FastAPI app factory

tests/
├── unit/                271 tests — domain models, services, infrastructure
├── integration/         41 tests — repositories, schema management
├── contract/            29 tests — API schemas, RFC 9457, PipelineGuard
└── load/                Locust performance tests
```

## License

Proprietary
