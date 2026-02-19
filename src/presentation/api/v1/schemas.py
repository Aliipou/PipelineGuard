"""
Pydantic v2 request/response schemas for the EU Multi-Tenant Cloud Platform API.

All models use strict validation, include OpenAPI examples, and follow
RFC 9457 Problem Details for error responses.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    SecretStr,
    field_validator,
)

# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class TenantStatus(str, Enum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    PENDING = "PENDING"
    DEPROVISIONING = "DEPROVISIONING"


class TenantTier(str, Enum):
    FREE = "FREE"
    STARTER = "STARTER"
    PROFESSIONAL = "PROFESSIONAL"
    ENTERPRISE = "ENTERPRISE"


class GDPRExportState(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    EXPIRED = "EXPIRED"


class AnomalySeverity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class InvoiceStatus(str, Enum):
    DRAFT = "DRAFT"
    ISSUED = "ISSUED"
    PAID = "PAID"
    OVERDUE = "OVERDUE"
    VOID = "VOID"


class AuditAction(str, Enum):
    CREATE = "CREATE"
    READ = "READ"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    LOGIN = "LOGIN"
    LOGOUT = "LOGOUT"
    EXPORT = "EXPORT"
    ERASE = "ERASE"


# ---------------------------------------------------------------------------
# Base / shared
# ---------------------------------------------------------------------------


class _CamelModel(BaseModel):
    """Base model with camelCase alias generation disabled -- we use snake_case
    throughout for consistency with Python conventions."""

    model_config = ConfigDict(
        populate_by_name=True,
        from_attributes=True,
        json_schema_extra={"$schema": "https://json-schema.org/draft/2020-12/schema"},
    )


class PaginationParams(BaseModel):
    """Query parameters shared by all paginated list endpoints."""

    page: int = Field(default=1, ge=1, description="Page number (1-indexed).")
    page_size: int = Field(default=20, ge=1, le=100, description="Items per page (max 100).")


class PaginationMeta(BaseModel):
    """Pagination metadata included in every list response."""

    page: int = Field(..., description="Current page number.")
    page_size: int = Field(..., description="Requested page size.")
    total_items: int = Field(..., description="Total number of items.")
    total_pages: int = Field(..., description="Total number of pages.")


# ---------------------------------------------------------------------------
# RFC 9457 Problem Details error response
# ---------------------------------------------------------------------------


class ErrorResponse(_CamelModel):
    """Error response following RFC 9457 Problem Details for HTTP APIs.

    See https://www.rfc-editor.org/rfc/rfc9457
    """

    type: str = Field(
        default="about:blank",
        description="A URI reference that identifies the problem type.",
        examples=["https://api.example.com/problems/tenant-not-found"],
    )
    title: str = Field(
        ...,
        description="A short, human-readable summary of the problem type.",
        examples=["Tenant Not Found"],
    )
    status: int = Field(
        ...,
        description="The HTTP status code.",
        examples=[404],
    )
    detail: str = Field(
        ...,
        description="A human-readable explanation specific to this occurrence.",
        examples=["Tenant with id '550e8400-e29b-41d4-a716-446655440000' does not exist."],
    )
    instance: str | None = Field(
        default=None,
        description="A URI reference that identifies the specific occurrence.",
        examples=["/api/v1/tenants/550e8400-e29b-41d4-a716-446655440000"],
    )
    errors: list[dict[str, Any]] | None = Field(
        default=None,
        description="Validation error details (when status is 422).",
    )


# ---------------------------------------------------------------------------
# Tenant schemas
# ---------------------------------------------------------------------------


class TenantCreate(_CamelModel):
    """Request body for creating a new tenant."""

    name: str = Field(
        ...,
        min_length=2,
        max_length=128,
        description="Human-readable tenant name.",
        examples=["Acme GmbH"],
    )
    slug: str = Field(
        ...,
        min_length=2,
        max_length=64,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
        description="URL-safe slug (lowercase, hyphens only).",
        examples=["acme-gmbh"],
    )
    tier: TenantTier = Field(
        default=TenantTier.FREE,
        description="Subscription tier.",
        examples=["PROFESSIONAL"],
    )
    admin_email: EmailStr = Field(
        ...,
        description="Email of the initial tenant admin / owner.",
        examples=["admin@acme.example"],
    )
    data_residency_region: str = Field(
        default="eu-central-1",
        description="EU data residency region for GDPR compliance.",
        examples=["eu-central-1"],
    )
    metadata: dict[str, Any] | None = Field(
        default=None,
        description="Arbitrary key-value metadata.",
    )


class TenantUpdate(_CamelModel):
    """Request body for partially updating tenant settings."""

    name: str | None = Field(
        default=None,
        min_length=2,
        max_length=128,
        description="Updated tenant name.",
    )
    tier: TenantTier | None = Field(default=None, description="Updated tier.")
    metadata: dict[str, Any] | None = Field(default=None, description="Merged metadata.")
    settings: dict[str, Any] | None = Field(default=None, description="Tenant-level settings.")


class TenantResponse(_CamelModel):
    """Representation of a tenant returned by the API."""

    id: uuid.UUID = Field(
        ...,
        description="Unique tenant identifier.",
        examples=["550e8400-e29b-41d4-a716-446655440000"],
    )
    name: str = Field(..., examples=["Acme GmbH"])
    slug: str = Field(..., examples=["acme-gmbh"])
    status: TenantStatus = Field(..., examples=["ACTIVE"])
    tier: TenantTier = Field(..., examples=["PROFESSIONAL"])
    schema_name: str = Field(
        ..., description="Postgres schema name.", examples=["tenant_acme_gmbh"]
    )
    data_residency_region: str = Field(..., examples=["eu-central-1"])
    admin_email: EmailStr = Field(..., examples=["admin@acme.example"])
    metadata: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime


class TenantListResponse(_CamelModel):
    """Paginated list of tenants."""

    items: list[TenantResponse]
    pagination: PaginationMeta


# ---------------------------------------------------------------------------
# Auth / User schemas
# ---------------------------------------------------------------------------


class UserRegister(_CamelModel):
    """Request body for registering a new user within a tenant."""

    email: EmailStr = Field(..., description="User email.", examples=["alice@acme.example"])
    password: SecretStr = Field(
        ...,
        min_length=10,
        max_length=128,
        description="Password (min 10 chars, must include upper, lower, digit, special).",
    )
    full_name: str = Field(
        ...,
        min_length=1,
        max_length=256,
        description="Full display name.",
        examples=["Alice Wonderland"],
    )

    @field_validator("password")
    @classmethod
    def _validate_password_strength(cls, v: SecretStr) -> SecretStr:
        raw = v.get_secret_value()
        checks = [
            any(c.isupper() for c in raw),
            any(c.islower() for c in raw),
            any(c.isdigit() for c in raw),
            any(not c.isalnum() for c in raw),
        ]
        if not all(checks):
            raise ValueError(
                "Password must contain at least one uppercase letter, one lowercase "
                "letter, one digit, and one special character."
            )
        return v


class UserLogin(_CamelModel):
    """Request body for logging in."""

    email: EmailStr = Field(..., examples=["alice@acme.example"])
    password: SecretStr = Field(..., min_length=1)


class TokenResponse(_CamelModel):
    """JWT token pair returned after login or refresh."""

    access_token: str = Field(..., description="Short-lived JWT access token.")
    refresh_token: str = Field(..., description="Long-lived opaque refresh token.")
    token_type: str = Field(default="Bearer")
    expires_in: int = Field(
        ...,
        description="Access token lifetime in seconds.",
        examples=[3600],
    )


class UserResponse(_CamelModel):
    """Public user profile."""

    id: uuid.UUID = Field(..., examples=["660e8400-e29b-41d4-a716-446655440001"])
    tenant_id: uuid.UUID
    email: EmailStr = Field(..., examples=["alice@acme.example"])
    full_name: str = Field(..., examples=["Alice Wonderland"])
    role: str = Field(..., description="RBAC role within the tenant.", examples=["OWNER"])
    is_active: bool = True
    created_at: datetime
    last_login_at: datetime | None = None


# ---------------------------------------------------------------------------
# Billing / Cost schemas
# ---------------------------------------------------------------------------


class CostLineItem(BaseModel):
    """Single cost item within a breakdown."""

    service: str = Field(..., examples=["compute"])
    amount: Decimal = Field(..., ge=0, decimal_places=4, examples=[42.1234])
    currency: str = Field(default="EUR", examples=["EUR"])
    unit: str = Field(..., examples=["vCPU-hours"])
    quantity: Decimal = Field(..., ge=0, examples=[120.5])


class CostBreakdown(_CamelModel):
    """Cost breakdown for a requested date range."""

    tenant_id: uuid.UUID
    period_start: date
    period_end: date
    total_amount: Decimal = Field(..., ge=0, examples=[1234.56])
    currency: str = Field(default="EUR")
    line_items: list[CostLineItem]


class CostProjection(_CamelModel):
    """Projected costs for the current billing period."""

    tenant_id: uuid.UUID
    billing_period_start: date
    billing_period_end: date
    actual_to_date: Decimal = Field(..., ge=0)
    projected_total: Decimal = Field(..., ge=0)
    confidence_interval_low: Decimal = Field(..., ge=0)
    confidence_interval_high: Decimal = Field(..., ge=0)
    currency: str = Field(default="EUR")


class InvoiceResponse(_CamelModel):
    """Invoice details."""

    id: uuid.UUID
    tenant_id: uuid.UUID
    invoice_number: str = Field(..., examples=["INV-2026-000042"])
    status: InvoiceStatus
    period_start: date
    period_end: date
    subtotal: Decimal = Field(..., ge=0)
    tax_amount: Decimal = Field(..., ge=0)
    total_amount: Decimal = Field(..., ge=0)
    currency: str = Field(default="EUR")
    issued_at: datetime | None = None
    due_date: date | None = None
    paid_at: datetime | None = None
    pdf_url: str | None = Field(default=None, description="Signed URL for PDF download.")


class InvoiceListResponse(_CamelModel):
    """Paginated list of invoices."""

    items: list[InvoiceResponse]
    pagination: PaginationMeta


class AnomalyResponse(_CamelModel):
    """A detected cost anomaly."""

    id: uuid.UUID
    tenant_id: uuid.UUID
    detected_at: datetime
    severity: AnomalySeverity
    service: str = Field(..., examples=["compute"])
    expected_amount: Decimal
    actual_amount: Decimal
    deviation_pct: Decimal = Field(..., description="Percentage deviation from expected.")
    description: str
    acknowledged: bool = False
    acknowledged_by: uuid.UUID | None = None


class AnomalyListResponse(_CamelModel):
    """Paginated list of cost anomalies."""

    items: list[AnomalyResponse]
    pagination: PaginationMeta


# ---------------------------------------------------------------------------
# GDPR schemas
# ---------------------------------------------------------------------------


class GDPRExportRequest(_CamelModel):
    """Request body for initiating a GDPR data export (Article 20)."""

    data_subjects: list[str] | None = Field(
        default=None,
        description="Specific user IDs to export. Omit for full tenant export.",
    )
    format: str = Field(
        default="json",
        pattern=r"^(json|csv|xml)$",
        description="Export file format.",
        examples=["json"],
    )
    include_audit_logs: bool = Field(
        default=False,
        description="Include audit-log entries in the export.",
    )


class GDPRExportStatus(_CamelModel):
    """Status of a GDPR data export job."""

    job_id: uuid.UUID
    tenant_id: uuid.UUID
    status: GDPRExportState
    requested_at: datetime
    completed_at: datetime | None = None
    expires_at: datetime | None = Field(
        default=None,
        description="Download link expiry (72 h after completion).",
    )
    download_url: str | None = Field(
        default=None,
        description="Signed download URL (available when COMPLETED).",
    )
    error_message: str | None = None


class GDPRErasureRequest(_CamelModel):
    """Request body for right-to-erasure (Article 17)."""

    data_subject_id: uuid.UUID = Field(
        ..., description="The user whose personal data should be erased."
    )
    reason: str | None = Field(
        default=None,
        max_length=1024,
        description="Optional reason for the erasure request.",
    )


class GDPRErasureResponse(_CamelModel):
    """Acknowledgement of a right-to-erasure request."""

    job_id: uuid.UUID
    tenant_id: uuid.UUID
    data_subject_id: uuid.UUID
    status: str = Field(default="ACCEPTED", examples=["ACCEPTED"])
    estimated_completion: datetime | None = None


class RetentionPolicyRequest(_CamelModel):
    """Request body for creating or updating a data retention policy."""

    default_retention_days: int = Field(
        ...,
        ge=1,
        le=3650,
        description="Default retention period in days.",
        examples=[365],
    )
    audit_log_retention_days: int = Field(
        ...,
        ge=30,
        le=3650,
        description="Audit log retention (minimum 30 days per regulation).",
        examples=[730],
    )
    backup_retention_days: int = Field(
        ...,
        ge=7,
        le=365,
        description="Backup retention period in days.",
        examples=[90],
    )
    pii_retention_days: int | None = Field(
        default=None,
        ge=1,
        le=3650,
        description="Separate PII retention override (if stricter than default).",
    )


class RetentionPolicyResponse(_CamelModel):
    """Current retention policy for a tenant."""

    tenant_id: uuid.UUID
    default_retention_days: int
    audit_log_retention_days: int
    backup_retention_days: int
    pii_retention_days: int | None = None
    updated_at: datetime
    updated_by: uuid.UUID


class AuditLogEntry(BaseModel):
    """Single audit-log entry."""

    id: uuid.UUID
    tenant_id: uuid.UUID
    user_id: uuid.UUID | None = None
    action: AuditAction
    resource_type: str = Field(..., examples=["tenant"])
    resource_id: str = Field(..., examples=["550e8400-e29b-41d4-a716-446655440000"])
    changes: dict[str, Any] | None = None
    ip_address: str | None = None
    user_agent: str | None = None
    timestamp: datetime


class AuditLogResponse(_CamelModel):
    """Paginated audit-log response."""

    items: list[AuditLogEntry]
    pagination: PaginationMeta


# ---------------------------------------------------------------------------
# PipelineGuard schemas
# ---------------------------------------------------------------------------


class PipelineStatus(str, Enum):
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    DISABLED = "DISABLED"


class JobStatus(str, Enum):
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    SILENT_FAILURE = "SILENT_FAILURE"


class AlertSeverity(str, Enum):
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class AlertType(str, Enum):
    SILENT_FAILURE = "SILENT_FAILURE"
    LATENCY_DRIFT = "LATENCY_DRIFT"
    CONSECUTIVE_FAILURES = "CONSECUTIVE_FAILURES"


class PipelineCreate(_CamelModel):
    """Request body for registering a new pipeline."""

    name: str = Field(
        ...,
        min_length=2,
        max_length=255,
        description="Pipeline name.",
        examples=["Google Ads -> BigQuery"],
    )
    source: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Data source platform.",
        examples=["Google Ads"],
    )
    destination: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Data destination.",
        examples=["BigQuery"],
    )
    schedule_cron: str = Field(
        default="",
        max_length=100,
        description="Cron schedule expression.",
        examples=["0 3 * * *"],
    )
    expected_duration_seconds: float = Field(
        default=0.0,
        ge=0,
        description="Expected job duration in seconds.",
    )
    timeout_seconds: int = Field(
        default=3600,
        ge=60,
        description="Job timeout in seconds.",
    )
    failure_threshold: int = Field(
        default=3,
        ge=1,
        le=100,
        description="Consecutive failures before CRITICAL alert.",
    )
    metadata: dict[str, Any] | None = None


class PipelineResponse(_CamelModel):
    """Pipeline representation returned by the API."""

    id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    source: str
    destination: str
    schedule_cron: str
    status: PipelineStatus
    expected_duration_seconds: float
    timeout_seconds: int
    failure_threshold: int
    metadata: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime


class PipelineListResponse(_CamelModel):
    """Paginated list of pipelines."""

    items: list[PipelineResponse]
    pagination: PaginationMeta


class JobExecutionCreate(_CamelModel):
    """Request body for reporting a job execution."""

    status: str = Field(
        ...,
        description="Job status as reported by the pipeline.",
        examples=["SUCCEEDED"],
    )
    started_at: datetime = Field(
        ...,
        description="When the job started.",
    )
    finished_at: datetime | None = Field(
        default=None,
        description="When the job finished.",
    )
    duration_seconds: float = Field(
        default=0.0,
        ge=0,
        description="Job duration in seconds.",
        examples=[125.3],
    )
    records_processed: int = Field(
        default=0,
        ge=0,
        description="Number of records processed.",
        examples=[0],
    )
    error_message: str = Field(
        default="",
        max_length=5000,
        description="Error message if any.",
    )
    metadata: dict[str, Any] | None = None


class JobExecutionResponse(_CamelModel):
    """Job execution representation returned by the API."""

    id: uuid.UUID
    pipeline_id: uuid.UUID
    tenant_id: uuid.UUID
    status: JobStatus
    started_at: datetime
    finished_at: datetime | None = None
    duration_seconds: float
    records_processed: int
    error_message: str = ""
    is_silent_failure: bool = False
    metadata: dict[str, Any] | None = None


class JobExecutionListResponse(_CamelModel):
    """Paginated list of job executions."""

    items: list[JobExecutionResponse]
    pagination: PaginationMeta


class LatencyResponse(_CamelModel):
    """Latency measurement record."""

    id: uuid.UUID
    pipeline_id: uuid.UUID
    tenant_id: uuid.UUID
    measured_at: datetime
    duration_seconds: float
    p50_baseline_seconds: float
    p95_baseline_seconds: float
    drift_percentage: float


class LatencyListResponse(_CamelModel):
    """Paginated latency history."""

    items: list[LatencyResponse]
    pagination: PaginationMeta


class AlertResponse(_CamelModel):
    """Pipeline alert representation."""

    id: uuid.UUID
    tenant_id: uuid.UUID
    pipeline_id: uuid.UUID
    severity: AlertSeverity
    alert_type: AlertType
    title: str
    description: str
    acknowledged: bool = False
    acknowledged_by: uuid.UUID | None = None
    acknowledged_at: datetime | None = None
    created_at: datetime


class AlertListResponse(_CamelModel):
    """Paginated list of alerts."""

    items: list[AlertResponse]
    pagination: PaginationMeta


class AlertAcknowledge(_CamelModel):
    """Request body for acknowledging an alert."""

    acknowledged_by: uuid.UUID = Field(
        ...,
        description="User ID acknowledging the alert.",
    )


class WeeklySummaryResponse(_CamelModel):
    """Weekly pipeline health summary."""

    id: uuid.UUID
    tenant_id: uuid.UUID
    week_start: date
    week_end: date
    total_jobs: int
    failed_jobs: int
    silent_failures: int
    pipelines_with_drift: int
    avg_drift_percentage: float
    top_risks: list[dict[str, Any]] | None = None
    plain_english_summary: str
    generated_at: datetime
