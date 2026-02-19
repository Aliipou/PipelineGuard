# Architecture Overview

## System Architecture

The EU Multi-Tenant Cloud Platform follows **Clean Architecture** with four concentric layers:

```
+-------------------------------------------------------------+
|                    Presentation Layer                        |
|   FastAPI endpoints, middleware, Pydantic schemas            |
+-------------------------------------------------------------+
|                    Application Layer                         |
|   Use-case orchestration, Celery tasks, pagination          |
+-------------------------------------------------------------+
|                      Domain Layer                            |
|   Models, services, events, exceptions (zero dependencies)  |
+-------------------------------------------------------------+
|                   Infrastructure Layer                       |
|   DB repos, auth, GDPR handlers, observability              |
+-------------------------------------------------------------+
```

**Dependency Rule**: Dependencies point inward. The domain layer has zero external dependencies. Infrastructure implements domain-defined ports (Protocol classes).

## Multi-Tenancy Model

Each tenant receives a dedicated PostgreSQL schema (`tenant_{slug}`), providing:

- **Data isolation** at the database level
- **Independent migrations** per tenant
- **GDPR-compliant erasure** via `DROP SCHEMA ... CASCADE`
- **Per-tenant resource accounting** for billing

Shared data (tenant registry, audit log, pipeline monitoring) lives in the `public` schema.

```
PostgreSQL
├── public
│   ├── tenants          (tenant registry)
│   ├── audit_log        (hash-chained audit trail)
│   ├── pipelines        (PipelineGuard: registered pipelines)
│   ├── job_executions   (PipelineGuard: job runs + silent failure flags)
│   ├── latency_records  (PipelineGuard: latency measurements)
│   ├── pipeline_alerts  (PipelineGuard: generated alerts)
│   └── weekly_summaries (PipelineGuard: CTO reports)
├── tenant_acme_gmbh
│   ├── users
│   ├── usage_records
│   ├── cost_records
│   └── invoices
└── tenant_other_corp
    ├── users
    ├── usage_records
    ├── cost_records
    └── invoices
```

## Request Flow

```
Client
  │
  ▼
FastAPI (uvicorn)
  │
  ├── TenantContextMiddleware   → resolves tenant from JWT/header
  ├── RequestLoggingMiddleware   → structured JSON logging
  │
  ▼
API Router (presentation)
  │
  ▼
Application Service            → orchestrates domain + infrastructure
  │
  ├── Domain Service            → business rules (stateless)
  ├── Domain Model              → aggregates, value objects
  └── Infrastructure Port       → Protocol-based dependency inversion
        │
        ▼
      Repository / Adapter      → PostgreSQL, Redis, external services
```

## Authentication Flow

1. User registers via `/api/v1/auth/register` (password hashed with Argon2id)
2. User authenticates via `/api/v1/auth/login` (returns RS256 JWT pair)
3. Access token (15 min) carries: `sub`, `tenant_id`, `role`, `email`
4. Refresh token (7 days) is an opaque token stored server-side
5. Token rotation: old refresh token revoked on each refresh

## Billing Pipeline

```
Usage Recording → Daily Aggregation → Cost Calculation → Anomaly Detection → Invoice Generation
     (API)          (Celery beat)       (Domain svc)       (z-score 2.5σ)      (Monthly task)
```

Pricing rates are configurable per resource type (CPU, memory, storage, network, API calls) in EUR.

## GDPR Compliance Architecture

### Right to Erasure (Article 17)

Seven-step pipeline executed as a Celery task:

1. Freeze tenant (transition to DEPROVISIONING)
2. Export backup (for legal retention)
3. Cascade delete all tenant data
4. Drop PostgreSQL schema
5. Purge Redis caches
6. Create audit entry
7. Transition to DELETED

### Data Portability (Article 20)

- Export all tenant data as JSON/CSV/XML
- Package as tar.gz with SHA-256 manifest
- Signed download URL (72-hour expiry)

### Retention Engine

- Per-tenant retention policies with configurable periods
- Soft-delete with grace period before hard-delete
- Per-category overrides (audit logs, PII, backups)

## Observability

| Component  | Technology       | Purpose                    |
|------------|------------------|----------------------------|
| Metrics    | Prometheus       | Request latency, counts    |
| Logging    | structlog (JSON) | Structured log aggregation |
| Dashboards | Grafana          | Visualization              |
| Logs Store | Loki             | Log indexing and querying  |

Custom Prometheus metrics:
- `api_requests_total` (method, endpoint, status, tenant_id)
- `api_request_duration_seconds` (histogram with custom buckets)
- `tenant_count` (by status)
- `tenant_resource_usage` (by tenant and resource type)
- `cost_anomalies_total` (by tenant and resource type)
- `pipeline_silent_failures_total` (by tenant and pipeline)
- `pipeline_latency_drift_detected` (by tenant and pipeline)
- `pipeline_alerts_active` (by tenant and severity)

## PipelineGuard Architecture

PipelineGuard is a vertical slice that monitors async data pipelines for silent failures and latency drift.

### Data Flow

```
External Pipeline
  │
  │  POST /api/v1/tenants/{id}/pipelines/{pid}/executions
  │  (webhook on each job completion)
  ▼
PipelineService.record_execution()
  │
  ├── Silent Failure Detection
  │     status=SUCCEEDED + records_processed=0 → SILENT_FAILURE
  │     → Creates CRITICAL alert
  │
  ├── Consecutive Failure Check
  │     last N failures >= threshold → CRITICAL alert
  │
  └── Latency Tracking
        DriftAnalyzer.analyze(current, historical)
        → Records LatencyRecord with p50/p95 baselines
```

### Drift Detection Algorithm

```
historical_durations = last 100 measurements (14-day window)
p50 = median(historical_durations)
threshold = p50 * 1.25  (25% above baseline)

if current_duration > threshold:
    alert(WARNING, "latency drift detected")
```

### Background Task Schedule

```
Every 15 min:  scan_silent_failures   → re-scan recent SUCCEEDED jobs
Every hour:    check_latency_drift    → compare all pipelines against baselines
Monday 08:00:  generate_weekly_summaries → plain-English CTO report per tenant
```

### Prometheus Metrics

- `pipeline_silent_failures_total` (tenant_id, pipeline_id)
- `pipeline_latency_drift_detected` (tenant_id, pipeline_id)
- `pipeline_alerts_active` (tenant_id, severity)

## Deployment Topology

```
                    ┌──────────────┐
                    │   Ingress    │
                    └──────┬───────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
         ┌────────┐  ┌────────┐  ┌────────┐
         │ API x2 │  │ Worker │  │  Beat  │
         └───┬────┘  └───┬────┘  └───┬────┘
             │            │            │
    ┌────────┴────────────┴────────────┴────────┐
    │                  Redis                     │
    └────────────────────────────────────────────┘
    ┌────────────────────────────────────────────┐
    │              PostgreSQL 16                 │
    └────────────────────────────────────────────┘
    ┌────────────────────────────────────────────┐
    │     Prometheus → Grafana → Loki            │
    └────────────────────────────────────────────┘
```

Infrastructure-as-Code: Terraform (Hetzner Cloud) + Kubernetes manifests.
