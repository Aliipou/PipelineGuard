"""
SQLAlchemy 2.0+ ORM models for the EU-Grade Multi-Tenant Cloud Platform.

Schema layout
-------------
* **public** schema  -- shared across all tenants
    - ``tenants``   -- one row per onboarded tenant
    - ``audit_log`` -- append-only, tamper-evident audit trail
* **tenant_{slug}** schemas  -- one schema per tenant
    - ``users``
    - ``usage_records``
    - ``cost_records``
    - ``invoices``
"""

from __future__ import annotations

import enum
import uuid
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
)

if TYPE_CHECKING:
    from datetime import date, datetime

# ---------------------------------------------------------------------------
# Base class
# ---------------------------------------------------------------------------


class Base(DeclarativeBase):  # type: ignore[misc]
    """Shared declarative base for every ORM model."""

    pass


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class TenantStatus(str, enum.Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    DEACTIVATED = "deactivated"
    PENDING = "pending"


class TenantTier(str, enum.Enum):
    FREE = "free"
    STARTER = "starter"
    PROFESSIONAL = "professional"
    ENTERPRISE = "enterprise"


class UserRole(str, enum.Enum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"


class InvoiceStatus(str, enum.Enum):
    DRAFT = "draft"
    ISSUED = "issued"
    PAID = "paid"
    OVERDUE = "overdue"
    CANCELLED = "cancelled"


class AuditAction(str, enum.Enum):
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    LOGIN = "login"
    LOGOUT = "logout"
    EXPORT = "export"
    BILLING = "billing"
    SCHEMA_CHANGE = "schema_change"
    COMPLIANCE = "compliance"


# ---------------------------------------------------------------------------
# PUBLIC SCHEMA -- TenantModel
# ---------------------------------------------------------------------------


class TenantModel(Base):
    """Represents a tenant (organisation) registered on the platform.

    Lives in the ``public`` schema and is shared across all tenants.
    """

    __tablename__ = "tenants"
    __table_args__ = (
        UniqueConstraint("slug", name="uq_tenants_slug"),
        Index("ix_tenants_status", "status"),
        Index("ix_tenants_created_at", "created_at"),
        {"schema": "public"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[TenantStatus] = mapped_column(
        Enum(TenantStatus, name="tenant_status", schema="public"),
        nullable=False,
        default=TenantStatus.PENDING,
    )
    tier: Mapped[TenantTier] = mapped_column(
        Enum(TenantTier, name="tenant_tier", schema="public"),
        nullable=False,
        default=TenantTier.FREE,
    )
    domain: Mapped[str | None] = mapped_column(String(255), nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=None)
    data_residency_region: Mapped[str] = mapped_column(
        String(10), nullable=False, default="eu-west-1"
    )
    max_users: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    is_gdpr_compliant: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Back-references (only useful inside public-schema queries)
    audit_logs: Mapped[list[AuditLogModel]] = relationship(back_populates="tenant", lazy="selectin")

    def __repr__(self) -> str:
        return f"<Tenant(id={self.id!r}, slug={self.slug!r}, status={self.status!r})>"


# ---------------------------------------------------------------------------
# TENANT SCHEMA -- UserModel
# ---------------------------------------------------------------------------


class UserModel(Base):
    """A user belonging to a specific tenant.

    This table is created inside each ``tenant_{slug}`` schema.
    """

    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("email", name="uq_users_email"),
        Index("ix_users_email", "email"),
        Index("ix_users_role", "role"),
        Index("ix_users_is_active", "is_active"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    hashed_password: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role", create_constraint=False),
        nullable=False,
        default=UserRole.MEMBER,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships within the tenant schema
    usage_records: Mapped[list[UsageRecordModel]] = relationship(
        back_populates="user", lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id!r}, email={self.email!r})>"


# ---------------------------------------------------------------------------
# TENANT SCHEMA -- UsageRecordModel
# ---------------------------------------------------------------------------


class UsageRecordModel(Base):
    """Tracks individual resource-usage events for billing purposes."""

    __tablename__ = "usage_records"
    __table_args__ = (
        Index("ix_usage_records_tenant_id", "tenant_id"),
        Index("ix_usage_records_user_id", "user_id"),
        Index("ix_usage_records_recorded_at", "recorded_at"),
        Index(
            "ix_usage_records_tenant_period",
            "tenant_id",
            "recorded_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    resource_type: Mapped[str] = mapped_column(String(100), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    unit: Mapped[str] = mapped_column(String(50), nullable=False)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    user: Mapped[UserModel | None] = relationship(back_populates="usage_records")

    def __repr__(self) -> str:
        return (
            f"<UsageRecord(id={self.id!r}, resource={self.resource_type!r}, "
            f"qty={self.quantity!r})>"
        )


# ---------------------------------------------------------------------------
# TENANT SCHEMA -- CostRecordModel
# ---------------------------------------------------------------------------


class CostRecordModel(Base):
    """Aggregated cost line-items derived from usage records."""

    __tablename__ = "cost_records"
    __table_args__ = (
        Index("ix_cost_records_tenant_id", "tenant_id"),
        Index("ix_cost_records_period", "period_start", "period_end"),
        Index(
            "ix_cost_records_tenant_period",
            "tenant_id",
            "period_start",
            "period_end",
        ),
        CheckConstraint("amount >= 0", name="ck_cost_records_amount_non_negative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(100), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="EUR")
    period_start: Mapped[date] = mapped_column(nullable=False)
    period_end: Mapped[date] = mapped_column(nullable=False)
    invoice_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("invoices.id", ondelete="SET NULL"),
        nullable=True,
    )
    metadata_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    invoice: Mapped[InvoiceModel | None] = relationship(back_populates="cost_records")

    def __repr__(self) -> str:
        return (
            f"<CostRecord(id={self.id!r}, type={self.resource_type!r}, "
            f"amount={self.amount!r} {self.currency})>"
        )


# ---------------------------------------------------------------------------
# TENANT SCHEMA -- InvoiceModel
# ---------------------------------------------------------------------------


class InvoiceModel(Base):
    """Monthly invoice issued to a tenant."""

    __tablename__ = "invoices"
    __table_args__ = (
        UniqueConstraint("invoice_number", name="uq_invoices_invoice_number"),
        Index("ix_invoices_tenant_id", "tenant_id"),
        Index("ix_invoices_status", "status"),
        Index("ix_invoices_issued_at", "issued_at"),
        CheckConstraint(
            "total_amount >= 0",
            name="ck_invoices_total_amount_non_negative",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    invoice_number: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[InvoiceStatus] = mapped_column(
        Enum(InvoiceStatus, name="invoice_status", create_constraint=False),
        nullable=False,
        default=InvoiceStatus.DRAFT,
    )
    total_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0.0000")
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="EUR")
    period_start: Mapped[date] = mapped_column(nullable=False)
    period_end: Mapped[date] = mapped_column(nullable=False)
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    cost_records: Mapped[list[CostRecordModel]] = relationship(
        back_populates="invoice", lazy="selectin"
    )

    def __repr__(self) -> str:
        return (
            f"<Invoice(id={self.id!r}, number={self.invoice_number!r}, " f"status={self.status!r})>"
        )


# ---------------------------------------------------------------------------
# PUBLIC SCHEMA -- AuditLogModel  (shared, append-only)
# ---------------------------------------------------------------------------


class AuditLogModel(Base):
    """Append-only, tamper-evident audit log stored in the public schema.

    Each entry contains a SHA-256 ``chain_hash`` that incorporates the
    hash of the previous entry, forming a hash-chain for integrity
    verification.
    """

    __tablename__ = "audit_log"
    __table_args__ = (
        Index("ix_audit_log_tenant_id", "tenant_id"),
        Index("ix_audit_log_action", "action"),
        Index("ix_audit_log_timestamp", "timestamp"),
        Index(
            "ix_audit_log_tenant_timestamp",
            "tenant_id",
            "timestamp",
        ),
        Index("ix_audit_log_actor_id", "actor_id"),
        {"schema": "public"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("public.tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    action: Mapped[AuditAction] = mapped_column(
        Enum(AuditAction, name="audit_action", schema="public"),
        nullable=False,
    )
    resource_type: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    chain_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    previous_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    tenant: Mapped[TenantModel] = relationship(back_populates="audit_logs")

    def __repr__(self) -> str:
        return (
            f"<AuditLog(id={self.id!r}, action={self.action!r}, " f"tenant_id={self.tenant_id!r})>"
        )


# ---------------------------------------------------------------------------
# PipelineGuard Enumerations
# ---------------------------------------------------------------------------


class PipelineStatusDB(str, enum.Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    DISABLED = "disabled"


class JobStatusDB(str, enum.Enum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SILENT_FAILURE = "silent_failure"


class AlertSeverityDB(str, enum.Enum):
    WARNING = "warning"
    CRITICAL = "critical"


class AlertTypeDB(str, enum.Enum):
    SILENT_FAILURE = "silent_failure"
    LATENCY_DRIFT = "latency_drift"
    CONSECUTIVE_FAILURES = "consecutive_failures"


# ---------------------------------------------------------------------------
# PUBLIC SCHEMA -- PipelineModel
# ---------------------------------------------------------------------------


class PipelineModel(Base):
    """Registered async data pipeline for monitoring."""

    __tablename__ = "pipelines"
    __table_args__ = (
        Index("ix_pipelines_tenant_id", "tenant_id"),
        Index("ix_pipelines_status", "status"),
        {"schema": "public"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("public.tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    source: Mapped[str] = mapped_column(String(255), nullable=False)
    destination: Mapped[str] = mapped_column(String(255), nullable=False)
    schedule_cron: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    status: Mapped[PipelineStatusDB] = mapped_column(
        Enum(PipelineStatusDB, name="pipeline_status", schema="public"),
        nullable=False,
        default=PipelineStatusDB.ACTIVE,
    )
    expected_duration_seconds: Mapped[float] = mapped_column(
        Numeric(12, 2), nullable=False, default=0.0
    )
    timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=3600)
    failure_threshold: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    job_executions: Mapped[list[JobExecutionModel]] = relationship(
        back_populates="pipeline", lazy="selectin"
    )
    latency_records: Mapped[list[LatencyRecordModel]] = relationship(
        back_populates="pipeline", lazy="selectin"
    )
    alerts: Mapped[list[PipelineAlertModel]] = relationship(
        back_populates="pipeline", lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<Pipeline(id={self.id!r}, name={self.name!r}, status={self.status!r})>"


# ---------------------------------------------------------------------------
# PUBLIC SCHEMA -- JobExecutionModel
# ---------------------------------------------------------------------------


class JobExecutionModel(Base):
    """Individual job run with silent failure detection."""

    __tablename__ = "job_executions"
    __table_args__ = (
        Index("ix_job_executions_pipeline_id", "pipeline_id"),
        Index("ix_job_executions_tenant_id", "tenant_id"),
        Index("ix_job_executions_status", "status"),
        Index("ix_job_executions_started_at", "started_at"),
        {"schema": "public"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    pipeline_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("public.pipelines.id", ondelete="CASCADE"),
        nullable=False,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    status: Mapped[JobStatusDB] = mapped_column(
        Enum(JobStatusDB, name="job_status", schema="public"),
        nullable=False,
        default=JobStatusDB.RUNNING,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0.0)
    records_processed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    is_silent_failure: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    pipeline: Mapped[PipelineModel] = relationship(back_populates="job_executions")

    def __repr__(self) -> str:
        return f"<JobExecution(id={self.id!r}, status={self.status!r})>"


# ---------------------------------------------------------------------------
# PUBLIC SCHEMA -- LatencyRecordModel
# ---------------------------------------------------------------------------


class LatencyRecordModel(Base):
    """Latency measurement for drift tracking."""

    __tablename__ = "latency_records"
    __table_args__ = (
        Index("ix_latency_records_pipeline_id", "pipeline_id"),
        Index("ix_latency_records_tenant_id", "tenant_id"),
        Index("ix_latency_records_measured_at", "measured_at"),
        {"schema": "public"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    pipeline_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("public.pipelines.id", ondelete="CASCADE"),
        nullable=False,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    measured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    duration_seconds: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0.0)
    p50_baseline_seconds: Mapped[float] = mapped_column(
        Numeric(12, 2), nullable=False, default=0.0
    )
    p95_baseline_seconds: Mapped[float] = mapped_column(
        Numeric(12, 2), nullable=False, default=0.0
    )
    drift_percentage: Mapped[float] = mapped_column(Numeric(8, 2), nullable=False, default=0.0)

    pipeline: Mapped[PipelineModel] = relationship(back_populates="latency_records")

    def __repr__(self) -> str:
        return (
            f"<LatencyRecord(id={self.id!r}, duration={self.duration_seconds!r}, "
            f"drift={self.drift_percentage!r}%)>"
        )


# ---------------------------------------------------------------------------
# PUBLIC SCHEMA -- PipelineAlertModel
# ---------------------------------------------------------------------------


class PipelineAlertModel(Base):
    """Generated alert for pipeline issues."""

    __tablename__ = "pipeline_alerts"
    __table_args__ = (
        Index("ix_pipeline_alerts_tenant_id", "tenant_id"),
        Index("ix_pipeline_alerts_pipeline_id", "pipeline_id"),
        Index("ix_pipeline_alerts_severity", "severity"),
        Index("ix_pipeline_alerts_created_at", "created_at"),
        {"schema": "public"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    pipeline_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("public.pipelines.id", ondelete="CASCADE"),
        nullable=False,
    )
    severity: Mapped[AlertSeverityDB] = mapped_column(
        Enum(AlertSeverityDB, name="alert_severity", schema="public"),
        nullable=False,
    )
    alert_type: Mapped[AlertTypeDB] = mapped_column(
        Enum(AlertTypeDB, name="alert_type", schema="public"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    acknowledged: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    acknowledged_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    acknowledged_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    pipeline: Mapped[PipelineModel] = relationship(back_populates="alerts")

    def __repr__(self) -> str:
        return (
            f"<PipelineAlert(id={self.id!r}, type={self.alert_type!r}, "
            f"severity={self.severity!r})>"
        )


# ---------------------------------------------------------------------------
# PUBLIC SCHEMA -- WeeklySummaryModel
# ---------------------------------------------------------------------------


class WeeklySummaryModel(Base):
    """Weekly CTO report stored for history."""

    __tablename__ = "weekly_summaries"
    __table_args__ = (
        Index("ix_weekly_summaries_tenant_id", "tenant_id"),
        Index("ix_weekly_summaries_week_start", "week_start"),
        {"schema": "public"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    week_start: Mapped[date] = mapped_column(nullable=False)
    week_end: Mapped[date] = mapped_column(nullable=False)
    total_jobs: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_jobs: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    silent_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pipelines_with_drift: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    avg_drift_percentage: Mapped[float] = mapped_column(Numeric(8, 2), nullable=False, default=0.0)
    top_risks: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    plain_english_summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
