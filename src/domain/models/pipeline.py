from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID, uuid4


class PipelineStatus(enum.Enum):
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    DISABLED = "DISABLED"


class JobStatus(enum.Enum):
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    SILENT_FAILURE = "SILENT_FAILURE"


class AlertSeverity(enum.Enum):
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class AlertType(enum.Enum):
    SILENT_FAILURE = "SILENT_FAILURE"
    LATENCY_DRIFT = "LATENCY_DRIFT"
    CONSECUTIVE_FAILURES = "CONSECUTIVE_FAILURES"


@dataclass
class Pipeline:
    id: UUID = field(default_factory=uuid4)
    tenant_id: UUID = field(default_factory=uuid4)
    name: str = ""
    source: str = ""
    destination: str = ""
    schedule_cron: str = ""
    status: PipelineStatus = PipelineStatus.ACTIVE
    expected_duration_seconds: float = 0.0
    timeout_seconds: int = 3600
    failure_threshold: int = 3
    metadata_json: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class JobExecution:
    id: UUID = field(default_factory=uuid4)
    pipeline_id: UUID = field(default_factory=uuid4)
    tenant_id: UUID = field(default_factory=uuid4)
    status: JobStatus = JobStatus.RUNNING
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    finished_at: datetime | None = None
    duration_seconds: float = 0.0
    records_processed: int = 0
    error_message: str = ""
    is_silent_failure: bool = False
    metadata_json: dict[str, Any] = field(default_factory=dict)


@dataclass
class LatencyRecord:
    id: UUID = field(default_factory=uuid4)
    pipeline_id: UUID = field(default_factory=uuid4)
    tenant_id: UUID = field(default_factory=uuid4)
    measured_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    duration_seconds: float = 0.0
    p50_baseline_seconds: float = 0.0
    p95_baseline_seconds: float = 0.0
    drift_percentage: float = 0.0


@dataclass
class PipelineAlert:
    id: UUID = field(default_factory=uuid4)
    tenant_id: UUID = field(default_factory=uuid4)
    pipeline_id: UUID = field(default_factory=uuid4)
    severity: AlertSeverity = AlertSeverity.WARNING
    alert_type: AlertType = AlertType.SILENT_FAILURE
    title: str = ""
    description: str = ""
    acknowledged: bool = False
    acknowledged_by: UUID | None = None
    acknowledged_at: datetime | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class WeeklySummary:
    id: UUID = field(default_factory=uuid4)
    tenant_id: UUID = field(default_factory=uuid4)
    week_start: date = field(default_factory=date.today)
    week_end: date = field(default_factory=date.today)
    total_jobs: int = 0
    failed_jobs: int = 0
    silent_failures: int = 0
    pipelines_with_drift: int = 0
    avg_drift_percentage: float = 0.0
    top_risks: list[dict[str, Any]] = field(default_factory=list)
    plain_english_summary: str = ""
    generated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
