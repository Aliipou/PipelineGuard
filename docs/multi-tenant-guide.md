# Multi-Tenant Deployment

PipelineGuard supports multiple teams sharing one installation with full data isolation.

## Creating Tenants

```bash
POST /api/admin/tenants
Authorization: Bearer <admin-token>

{
  "name": "data-team",
  "display_name": "Data Engineering",
  "quota": {
    "max_pipelines": 50,
    "max_alerts": 100,
    "retention_days": 90
  }
}
```

## Tenant API Keys

```bash
POST /api/admin/tenants/data-team/api-keys

{"name": "production", "expires_in_days": 365}
```

## Data Isolation

- Each tenant's pipelines, executions, and alerts are fully isolated
- Tenants cannot see each other's data
- Admin token required to create/delete tenants
- Per-tenant quotas enforced at API level

## SDK Configuration

```python
from pipelineguard import guard

@guard(
    pipeline="etl-daily",
    api_url="https://pipelineguard.internal",
    api_key="tenant-specific-key",  # isolates to your tenant
)
def my_job():
    ...
```

## Audit Log

All admin actions (create/delete tenant, key rotation) are logged to an immutable audit trail.
