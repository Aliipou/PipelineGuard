# PipelineGuard

Your pipeline said **SUCCESS**. It processed zero records. You found out three days later when the weekly report was wrong.

PipelineGuard catches that in 30 seconds.

[![CI](https://github.com/Aliipou/PipelineGuard/actions/workflows/ci.yml/badge.svg)](https://github.com/Aliipou/PipelineGuard/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat&logo=python)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green?style=flat)](LICENSE)

> **Status: Early-stage / Demo.**
> The core detection logic (silent failures, latency drift, consecutive failure tracking) is implemented and tested.
> However, the default setup runs entirely with **in-memory repositories** -- data is lost on restart.
> SQL-backed repository implementations exist (see `src/infrastructure/database/pipeline_repositories.py`) but are not wired into the DI container yet.
> Slack and webhook notification classes exist but are **not connected** to the alert pipeline -- alerts are persisted but not delivered externally.

## The Problem

Data pipelines lie. A pipeline that reports `status: SUCCEEDED` with `records_processed: 0` is a **silent failure** -- the most expensive kind. No error, no alert, no pager. Just wrong data downstream for however long it takes someone to notice.

Latency drift is quieter still. Your nightly ETL job used to finish in 40 minutes. Now it takes 70. Each individual run looks fine. Trend-blind monitoring misses it entirely.

## What PipelineGuard Does

**Silent failure detection** -- Any execution that reports success but processed zero records, or succeeded alongside an error message, is immediately flagged as `SILENT_FAILURE` and generates a CRITICAL alert.

**Latency drift detection** -- Every execution duration is compared against a rolling percentile baseline (p50 + p95) and scored with a z-score. When a pipeline consistently runs 25% above its p50 baseline, a WARNING alert fires before the problem becomes a crisis.

**Consecutive failure tracking** -- Configurable failure thresholds per pipeline. Three consecutive failures (or silent failures) generates a CRITICAL alert regardless of individual severity.

**Weekly health summaries** -- Every Monday, a plain-English summary: how many jobs ran, how many silently failed, which pipelines are drifting, and the top 5 risks. Readable by engineers and CTOs alike.

### Not Yet Wired Up

- **Slack notifications** -- `SlackNotifier` class exists (`src/infrastructure/notifications/slack.py`) with Block Kit formatting, but is not called from the alert pipeline. Alerts are stored in the database only.
- **Webhook notifications** -- `WebhookNotifier` class exists with HMAC-SHA256 signing, but is not connected.
- **SQL persistence** -- SQL repository implementations exist for pipelines, executions, latency records, and alerts. The DI container currently uses in-memory replacements. See TODO comments in `src/infrastructure/container.py`.
- **Alert deduplication** -- `AlertDeduplicator` exists but is not integrated into `PipelineService._create_alert()`.

## Quick Start

```bash
git clone https://github.com/Aliipou/PipelineGuard
cd PipelineGuard
cp deploy/docker/.env.example deploy/docker/.env
docker compose -f deploy/docker/docker-compose.yml up -d
```

The API is at `http://localhost:8000`. Interactive docs at `http://localhost:8000/docs`.

### Register a Pipeline

```bash
curl -s -X POST http://localhost:8000/api/v1/tenants/{tenant_id}/pipelines \
  -H "Content-Type: application/json" \
  -d '{
    "name": "nightly-user-sync",
    "source": "postgres://crm",
    "destination": "bigquery://warehouse",
    "schedule_cron": "0 2 * * *",
    "expected_duration_seconds": 1800,
    "failure_threshold": 3
  }'
```

### Report an Execution (Python SDK)

```python
from pipelineguard import guard

@guard(
    pipeline_id="<pipeline-uuid>",
    tenant_id="<tenant-uuid>",
    api_url="http://localhost:8000",
    api_key="pg_live_...",
)
def nightly_user_sync() -> int:
    users = fetch_users_from_crm()
    upsert_to_warehouse(users)
    return len(users)  # auto-reported as records_processed

# If this returns 0 -> CRITICAL alert fires immediately
nightly_user_sync()
```

### Report from Any Language

```bash
curl -s -X POST http://localhost:8000/api/v1/tenants/{tenant_id}/pipelines/{pipeline_id}/executions \
  -H "Content-Type: application/json" \
  -d '{
    "status": "SUCCEEDED",
    "started_at": "2024-01-15T02:00:00Z",
    "finished_at": "2024-01-15T02:31:00Z",
    "duration_seconds": 1860,
    "records_processed": 0
  }'
# -> silent failure detected, CRITICAL alert stored
```

## Architecture

```
                      Your pipelines
                      (Airflow / cron / Celery / K8s jobs)
                              |
                    POST /executions
                              |
                     +--------v---------+
                     |   PipelineGuard  |
                     |      API         |
                     +--------+---------+
                              |
            +-----------------+------------------+
            |                 |                  |
   +--------v-------+ +------v--------+ +-------v---------+
   |  Silent Failure| |  Drift        | |  Consecutive    |
   |  Detector      | |  Analyzer     | |  Failure Check  |
   +--------+-------+ +------+--------+ +-------+---------+
            |                 |                  |
            +-----------------+------------------+
                              |
                    +---------v----------+
                    |   Alert Storage    |
                    |   (In-Memory /     |
                    |    Postgres)       |
                    +--------------------+
```

## Detection Logic

### Silent Failure

A job execution is classified `SILENT_FAILURE` when:
- `status == SUCCEEDED` AND `records_processed == 0`
- `status == SUCCEEDED` AND `error_message != ""`

This catches the most common real-world failure mode: upstream data source returns empty, pipeline exits cleanly, downstream reports are silently stale.

### Latency Drift (DriftAnalyzer)

For each execution, PipelineGuard computes:

```
rolling_window = last 100 durations for this pipeline
p50            = median(rolling_window)
z_score        = (current - mean) / stdev

is_drifting    = current > p50 * 1.25          # 25% above baseline
is_anomaly     = |z_score| > 2.5               # 2.5 standard deviations
```

The combination of percentile drift (trend detection) and z-score (spike detection) catches both gradual slowdowns and sudden outliers with a very low false positive rate.

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check |
| POST | `/api/v1/tenants/{tid}/pipelines` | Register pipeline |
| GET | `/api/v1/tenants/{tid}/pipelines` | List pipelines |
| POST | `/api/v1/tenants/{tid}/pipelines/{pid}/executions` | Report execution |
| GET | `/api/v1/tenants/{tid}/pipelines/{pid}/executions` | Execution history |
| GET | `/api/v1/tenants/{tid}/pipelines/{pid}/latency` | Latency + drift data |
| GET | `/api/v1/tenants/{tid}/alerts` | Active alerts |
| POST | `/api/v1/tenants/{tid}/alerts/{aid}/acknowledge` | Acknowledge alert |
| GET | `/api/v1/tenants/{tid}/summary` | Latest weekly summary |
| POST | `/api/v1/tenants/{tid}/summary/generate` | Generate summary now |

Full OpenAPI spec at `/docs` (Swagger UI) or `/redoc`.

## Configuration

```bash
# deploy/docker/.env
APP_POSTGRES_HOST=postgres
APP_POSTGRES_PASSWORD=your_password
APP_REDIS_URL=redis://redis:6379/0
APP_SLACK_WEBHOOK_URL=https://hooks.slack.com/services/T.../B.../...   # not yet wired
APP_JWT_PRIVATE_KEY=...   # RS256 -- generate with scripts/generate_keys.py
```

## Running Tests

```bash
pip install -e ".[dev]"
make test          # unit + integration
make test-unit     # unit only (no database required)
make lint          # ruff + mypy
```

## Production Deployment

See [deploy/k8s/](deploy/k8s/) for Kubernetes manifests with:
- API deployment + HPA
- Celery worker deployment
- PostgreSQL StatefulSet
- Redis deployment
- Prometheus + Grafana + Loki observability stack
- Network policies (deny-all default, allow-list per service)

See [deploy/terraform/](deploy/terraform/) for AWS infrastructure modules (ECS, RDS, ElastiCache, VPC).

## License

MIT
