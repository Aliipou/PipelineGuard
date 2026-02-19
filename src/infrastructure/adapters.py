"""Adapter implementations bridging infrastructure to application-layer ports.

Provides concrete repository adapters, a Redis-backed refresh token store,
and a Redis-backed cache manager.
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from uuid import UUID

    from domain.models.audit import AuditEntry
    from domain.models.billing import CostAnomaly, CostRecord, Invoice, UsageRecord
    from domain.models.pipeline import (
        JobExecution,
        LatencyRecord,
        Pipeline,
        PipelineAlert,
        WeeklySummary,
    )
    from domain.models.tenant import Tenant, TenantStatus
    from domain.models.user import User

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# In-memory repository adapters (swap for real DB repos in production)
# ---------------------------------------------------------------------------


class InMemoryTenantRepository:
    """Synchronous in-memory tenant store for wiring validation."""

    def __init__(self) -> None:
        self._store: dict[UUID, Tenant] = {}
        self._by_slug: dict[str, UUID] = {}

    def get_by_id(self, tenant_id: UUID) -> Tenant | None:
        return self._store.get(tenant_id)

    def get_by_slug(self, slug: str) -> Tenant | None:
        tid = self._by_slug.get(slug)
        return self._store.get(tid) if tid else None

    def list_tenants(
        self,
        offset: int = 0,
        limit: int = 20,
        status_filter: TenantStatus | None = None,
    ) -> tuple[list[Tenant], int]:
        items = list(self._store.values())
        if status_filter:
            items = [t for t in items if t.status == status_filter]
        total = len(items)
        return items[offset : offset + limit], total

    def save(self, tenant: Tenant) -> Tenant:
        self._store[tenant.id] = tenant
        self._by_slug[tenant.slug] = tenant.id
        return tenant

    def update(self, tenant: Tenant) -> Tenant:
        self._store[tenant.id] = tenant
        return tenant


class InMemoryUserRepository:
    """Synchronous in-memory user store."""

    def __init__(self) -> None:
        self._store: dict[UUID, User] = {}
        self._by_email: dict[str, UUID] = {}

    def get_by_id(self, user_id: UUID) -> User | None:
        return self._store.get(user_id)

    def get_by_email(self, email: str) -> User | None:
        uid = self._by_email.get(email)
        return self._store.get(uid) if uid else None

    def count_by_tenant(self, tenant_id: UUID) -> int:
        return sum(1 for u in self._store.values() if u.tenant_id == tenant_id)

    def save(self, user: User) -> User:
        self._store[user.id] = user
        self._by_email[user.email] = user.id
        return user

    def update(self, user: User) -> User:
        self._store[user.id] = user
        return user


class InMemoryAuditRepository:
    """Synchronous in-memory audit store."""

    def __init__(self) -> None:
        self._entries: list[AuditEntry] = []

    def get_latest_entry(self, tenant_id: UUID) -> AuditEntry | None:
        for entry in reversed(self._entries):
            if entry.tenant_id == tenant_id:
                return entry
        return None

    def save(self, entry: AuditEntry) -> AuditEntry:
        self._entries.append(entry)
        return entry


class InMemoryUsageRepository:
    """In-memory usage record store."""

    def __init__(self) -> None:
        self._records: list[UsageRecord] = []

    def save(self, record: UsageRecord) -> UsageRecord:
        self._records.append(record)
        return record

    def get_by_tenant_and_date(self, tenant_id: UUID, target_date: date) -> list[UsageRecord]:
        return [
            r
            for r in self._records
            if r.tenant_id == tenant_id and r.recorded_at.date() == target_date
        ]

    def get_by_tenant_and_range(
        self, tenant_id: UUID, start_date: date, end_date: date
    ) -> list[UsageRecord]:
        return [
            r
            for r in self._records
            if r.tenant_id == tenant_id and start_date <= r.recorded_at.date() <= end_date
        ]


class InMemoryCostRepository:
    """In-memory cost record store."""

    def __init__(self) -> None:
        self._records: list[CostRecord] = []

    def save(self, record: CostRecord) -> CostRecord:
        self._records.append(record)
        return record

    def save_many(self, records: list[CostRecord]) -> list[CostRecord]:
        self._records.extend(records)
        return records

    def get_by_tenant_and_date(self, tenant_id: UUID, target_date: date) -> list[CostRecord]:
        return [r for r in self._records if r.tenant_id == tenant_id and r.date == target_date]

    def get_by_tenant_and_range(
        self, tenant_id: UUID, start_date: date, end_date: date
    ) -> list[CostRecord]:
        return [
            r
            for r in self._records
            if r.tenant_id == tenant_id and start_date <= r.date <= end_date
        ]


class InMemoryInvoiceRepository:
    """In-memory invoice store."""

    def __init__(self) -> None:
        self._invoices: dict[UUID, Invoice] = {}

    def save(self, invoice: Invoice) -> Invoice:
        self._invoices[invoice.id] = invoice
        return invoice

    def get_by_tenant_and_period(
        self, tenant_id: UUID, period_start: date, period_end: date
    ) -> Invoice | None:
        for inv in self._invoices.values():
            if (
                inv.tenant_id == tenant_id
                and inv.period_start == period_start
                and inv.period_end == period_end
            ):
                return inv
        return None


class InMemoryAnomalyRepository:
    """In-memory anomaly store."""

    def __init__(self) -> None:
        self._anomalies: list[CostAnomaly] = []

    def save(self, anomaly: CostAnomaly) -> CostAnomaly:
        self._anomalies.append(anomaly)
        return anomaly

    def save_many(self, anomalies: list[CostAnomaly]) -> list[CostAnomaly]:
        self._anomalies.extend(anomalies)
        return anomalies

    def get_recent_by_tenant(self, tenant_id: UUID, days: int = 7) -> list[CostAnomaly]:
        cutoff = datetime.now(UTC) - timedelta(days=days)
        return [a for a in self._anomalies if a.tenant_id == tenant_id and a.detected_at >= cutoff]


# ---------------------------------------------------------------------------
# Refresh token store (in-memory, swap for Redis in production)
# ---------------------------------------------------------------------------


class InMemoryRefreshTokenStore:
    """In-memory refresh token store."""

    def __init__(self) -> None:
        self._tokens: dict[str, tuple[UUID, datetime]] = {}

    def store(self, token_id: str, user_id: UUID, expires_at: datetime) -> None:
        self._tokens[token_id] = (user_id, expires_at)

    def validate(self, token_id: str) -> UUID | None:
        entry = self._tokens.get(token_id)
        if entry is None:
            return None
        user_id, expires_at = entry
        if datetime.now(UTC) > expires_at:
            del self._tokens[token_id]
            return None
        return user_id

    def revoke(self, token_id: str) -> None:
        self._tokens.pop(token_id, None)


# ---------------------------------------------------------------------------
# Cache manager
# ---------------------------------------------------------------------------


class InMemoryCacheManager:
    """Simple in-memory cache manager."""

    def __init__(self) -> None:
        self._cache: dict[str, Any] = {}

    def purge_tenant(self, tenant_id: UUID) -> None:
        prefix = str(tenant_id)
        keys_to_remove = [k for k in self._cache if k.startswith(prefix)]
        for k in keys_to_remove:
            del self._cache[k]


# ---------------------------------------------------------------------------
# Export job repository
# ---------------------------------------------------------------------------


class InMemoryExportJobRepository:
    """In-memory export job tracking."""

    def __init__(self) -> None:
        self._jobs: dict[str, dict[str, Any]] = {}

    def save(self, job_id: str, tenant_id: UUID, status: Any) -> None:
        self._jobs[job_id] = {
            "job_id": job_id,
            "tenant_id": tenant_id,
            "status": status,
            "download_url": None,
            "error": None,
            "created_at": datetime.now(UTC),
            "completed_at": None,
        }

    def get_status(self, job_id: str) -> Any | None:
        return self._jobs.get(job_id)

    def update_status(
        self,
        job_id: str,
        status: Any,
        download_url: str | None = None,
        error: str | None = None,
    ) -> None:
        if job_id in self._jobs:
            self._jobs[job_id]["status"] = status
            if download_url:
                self._jobs[job_id]["download_url"] = download_url
            if error:
                self._jobs[job_id]["error"] = error


# ---------------------------------------------------------------------------
# Retention repository
# ---------------------------------------------------------------------------


class InMemoryRetentionRepository:
    """In-memory retention policy and record tracking."""

    def __init__(self) -> None:
        self._policies: dict[UUID, Any] = {}

    def get_policy(self, tenant_id: UUID) -> Any | None:
        return self._policies.get(tenant_id)

    def save_policy(self, policy: Any) -> Any:
        self._policies[policy.tenant_id] = policy
        return policy

    def find_expired_records(self, tenant_id: UUID, threshold_date: date) -> list[UUID]:
        return []

    def soft_delete_records(self, record_ids: list[UUID]) -> int:
        return len(record_ids)

    def find_soft_deleted_past_grace(self, tenant_id: UUID, grace_date: date) -> list[UUID]:
        return []

    def hard_delete_records(self, record_ids: list[UUID]) -> int:
        return len(record_ids)


# ---------------------------------------------------------------------------
# Tenant data repository (for GDPR erasure)
# ---------------------------------------------------------------------------


class InMemoryTenantDataRepository:
    """In-memory tenant data repo for cascade delete."""

    def cascade_delete_all(self, tenant_id: UUID) -> int:
        logger.info("Cascade delete all data for tenant %s", tenant_id)
        return 0


# ---------------------------------------------------------------------------
# PipelineGuard in-memory repositories
# ---------------------------------------------------------------------------


class InMemoryPipelineRepository:
    """In-memory pipeline store."""

    def __init__(self) -> None:
        self._store: dict[UUID, Pipeline] = {}

    def get_by_id(self, pipeline_id: UUID) -> Pipeline | None:
        return self._store.get(pipeline_id)

    def list_by_tenant(
        self,
        tenant_id: UUID,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[Pipeline], int]:
        items = [p for p in self._store.values() if p.tenant_id == tenant_id]
        total = len(items)
        return items[offset : offset + limit], total

    def save(self, pipeline: Pipeline) -> Pipeline:
        self._store[pipeline.id] = pipeline
        return pipeline

    def update(self, pipeline: Pipeline) -> Pipeline:
        self._store[pipeline.id] = pipeline
        return pipeline


class InMemoryJobExecutionRepository:
    """In-memory job execution store."""

    def __init__(self) -> None:
        self._store: list[JobExecution] = []

    def get_by_id(self, execution_id: UUID) -> JobExecution | None:
        for ex in self._store:
            if ex.id == execution_id:
                return ex
        return None

    def list_by_pipeline(
        self,
        pipeline_id: UUID,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[JobExecution], int]:
        items = [ex for ex in self._store if ex.pipeline_id == pipeline_id]
        total = len(items)
        return items[offset : offset + limit], total

    def list_recent_by_pipeline(
        self,
        pipeline_id: UUID,
        limit: int = 10,
    ) -> list[JobExecution]:
        items = [ex for ex in self._store if ex.pipeline_id == pipeline_id]
        return items[-limit:]

    def list_recent_by_tenant(
        self,
        tenant_id: UUID,
        limit: int = 100,
    ) -> list[JobExecution]:
        items = [ex for ex in self._store if ex.tenant_id == tenant_id]
        return items[-limit:]

    def save(self, execution: JobExecution) -> JobExecution:
        self._store.append(execution)
        return execution


class InMemoryLatencyRecordRepository:
    """In-memory latency record store."""

    def __init__(self) -> None:
        self._store: list[LatencyRecord] = []

    def list_by_pipeline(
        self,
        pipeline_id: UUID,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[LatencyRecord], int]:
        items = [r for r in self._store if r.pipeline_id == pipeline_id]
        total = len(items)
        return items[offset : offset + limit], total

    def get_recent_durations(
        self,
        pipeline_id: UUID,
        limit: int = 100,
    ) -> list[float]:
        items = [r for r in self._store if r.pipeline_id == pipeline_id]
        return [r.duration_seconds for r in items[-limit:]]

    def save(self, record: LatencyRecord) -> LatencyRecord:
        self._store.append(record)
        return record


class InMemoryPipelineAlertRepository:
    """In-memory pipeline alert store."""

    def __init__(self) -> None:
        self._store: dict[UUID, PipelineAlert] = {}

    def get_by_id(self, alert_id: UUID) -> PipelineAlert | None:
        return self._store.get(alert_id)

    def list_by_tenant(
        self,
        tenant_id: UUID,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[PipelineAlert], int]:
        items = [a for a in self._store.values() if a.tenant_id == tenant_id]
        total = len(items)
        return items[offset : offset + limit], total

    def save(self, alert: PipelineAlert) -> PipelineAlert:
        self._store[alert.id] = alert
        return alert

    def update(self, alert: PipelineAlert) -> PipelineAlert:
        self._store[alert.id] = alert
        return alert


class InMemoryWeeklySummaryRepository:
    """In-memory weekly summary store."""

    def __init__(self) -> None:
        self._store: list[WeeklySummary] = []

    def get_latest_by_tenant(self, tenant_id: UUID) -> WeeklySummary | None:
        for summary in reversed(self._store):
            if summary.tenant_id == tenant_id:
                return summary
        return None

    def save(self, summary: WeeklySummary) -> WeeklySummary:
        self._store.append(summary)
        return summary


# ---------------------------------------------------------------------------
# Schema manager adapter
# ---------------------------------------------------------------------------


class NoOpSchemaManager:
    """Schema manager that logs but doesn't execute SQL."""

    def create_schema(self, schema_name: str) -> None:
        logger.info("Would create schema: %s", schema_name)

    def run_migrations(self, schema_name: str) -> None:
        logger.info("Would run migrations for: %s", schema_name)

    def drop_schema(self, schema_name: str) -> None:
        logger.info("Would drop schema: %s", schema_name)


# ---------------------------------------------------------------------------
# Event publisher
# ---------------------------------------------------------------------------


class LoggingEventPublisher:
    """Event publisher that logs events."""

    def publish(self, event: Any) -> None:
        logger.info("Domain event: %s", event)
