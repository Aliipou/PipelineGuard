"""Application service that orchestrates pipeline monitoring operations.

``PipelineService`` coordinates silent failure detection, latency drift
tracking, alert generation, and weekly summary production for the
PipelineGuard vertical.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import UUID, uuid4

from application.schemas.pagination import PaginatedResponse, PaginationParams
from domain.models.pipeline import (
    AlertSeverity,
    AlertType,
    JobExecution,
    JobStatus,
    LatencyRecord,
    Pipeline,
    PipelineAlert,
    PipelineStatus,
    WeeklySummary,
)
from domain.services.drift_analyzer import DriftAnalyzer
from domain.services.summary_generator import SummaryGenerator, SummaryInput

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Repository port interfaces (dependency-inversion)
# ---------------------------------------------------------------------------


class PipelineRepository(Protocol):
    """Port: persistence for Pipeline aggregates."""

    def get_by_id(self, pipeline_id: UUID) -> Pipeline | None: ...

    def list_by_tenant(
        self,
        tenant_id: UUID,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[Pipeline], int]: ...

    def save(self, pipeline: Pipeline) -> Pipeline: ...

    def update(self, pipeline: Pipeline) -> Pipeline: ...


class JobExecutionRepository(Protocol):
    """Port: persistence for job execution records."""

    def get_by_id(self, execution_id: UUID) -> JobExecution | None: ...

    def list_by_pipeline(
        self,
        pipeline_id: UUID,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[JobExecution], int]: ...

    def list_recent_by_pipeline(
        self,
        pipeline_id: UUID,
        limit: int = 10,
    ) -> list[JobExecution]: ...

    def list_recent_by_tenant(
        self,
        tenant_id: UUID,
        limit: int = 100,
    ) -> list[JobExecution]: ...

    def save(self, execution: JobExecution) -> JobExecution: ...


class LatencyRecordRepository(Protocol):
    """Port: persistence for latency measurements."""

    def list_by_pipeline(
        self,
        pipeline_id: UUID,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[LatencyRecord], int]: ...

    def get_recent_durations(
        self,
        pipeline_id: UUID,
        limit: int = 100,
    ) -> list[float]: ...

    def save(self, record: LatencyRecord) -> LatencyRecord: ...


class PipelineAlertRepository(Protocol):
    """Port: persistence for pipeline alerts."""

    def get_by_id(self, alert_id: UUID) -> PipelineAlert | None: ...

    def list_by_tenant(
        self,
        tenant_id: UUID,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[PipelineAlert], int]: ...

    def save(self, alert: PipelineAlert) -> PipelineAlert: ...

    def update(self, alert: PipelineAlert) -> PipelineAlert: ...


class WeeklySummaryRepository(Protocol):
    """Port: persistence for weekly summaries."""

    def get_latest_by_tenant(self, tenant_id: UUID) -> WeeklySummary | None: ...

    def save(self, summary: WeeklySummary) -> WeeklySummary: ...


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class PipelineService:
    """Orchestrates pipeline monitoring, alerting, and reporting."""

    def __init__(
        self,
        pipeline_repo: PipelineRepository,
        execution_repo: JobExecutionRepository,
        latency_repo: LatencyRecordRepository,
        alert_repo: PipelineAlertRepository,
        summary_repo: WeeklySummaryRepository,
        drift_analyzer: DriftAnalyzer,
        summary_generator: SummaryGenerator,
    ) -> None:
        self._pipeline_repo = pipeline_repo
        self._execution_repo = execution_repo
        self._latency_repo = latency_repo
        self._alert_repo = alert_repo
        self._summary_repo = summary_repo
        self._drift_analyzer = drift_analyzer
        self._summary_generator = summary_generator

    # -- Pipeline CRUD ----------------------------------------------------

    def register_pipeline(
        self,
        tenant_id: UUID,
        name: str,
        source: str,
        destination: str,
        schedule_cron: str = "",
        expected_duration_seconds: float = 0.0,
        timeout_seconds: int = 3600,
        failure_threshold: int = 3,
        metadata_json: dict[str, Any] | None = None,
    ) -> Pipeline:
        """Register a new data pipeline for monitoring."""
        pipeline = Pipeline(
            id=uuid4(),
            tenant_id=tenant_id,
            name=name,
            source=source,
            destination=destination,
            schedule_cron=schedule_cron,
            status=PipelineStatus.ACTIVE,
            expected_duration_seconds=expected_duration_seconds,
            timeout_seconds=timeout_seconds,
            failure_threshold=failure_threshold,
            metadata_json=metadata_json or {},
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        pipeline = self._pipeline_repo.save(pipeline)
        logger.info("Pipeline %s registered for tenant %s", pipeline.id, tenant_id)
        return pipeline

    def get_pipeline(self, pipeline_id: UUID) -> Pipeline:
        """Retrieve a single pipeline by ID."""
        pipeline = self._pipeline_repo.get_by_id(pipeline_id)
        if pipeline is None:
            raise PipelineNotFoundError(pipeline_id=str(pipeline_id))
        return pipeline

    def list_pipelines(
        self,
        tenant_id: UUID,
        page: int = 1,
        size: int = 20,
    ) -> PaginatedResponse[Pipeline]:
        """Return a paginated list of pipelines for a tenant."""
        params = PaginationParams(page=page, size=size)
        items, total = self._pipeline_repo.list_by_tenant(
            tenant_id=tenant_id,
            offset=params.offset,
            limit=params.size,
        )
        return PaginatedResponse[Pipeline](
            items=items,
            total=total,
            page=params.page,
            size=params.size,
        )

    # -- Job Execution + Silent Failure Detection -------------------------

    def record_execution(
        self,
        pipeline_id: UUID,
        tenant_id: UUID,
        status: str,
        started_at: datetime,
        finished_at: datetime | None = None,
        duration_seconds: float = 0.0,
        records_processed: int = 0,
        error_message: str = "",
        metadata_json: dict[str, Any] | None = None,
    ) -> JobExecution:
        """Record a job execution and auto-detect silent failures."""
        pipeline = self.get_pipeline(pipeline_id)

        job_status = JobStatus(status)
        is_silent_failure = False

        # Silent failure detection
        if job_status == JobStatus.SUCCEEDED:
            if records_processed == 0 or error_message:
                is_silent_failure = True
                job_status = JobStatus.SILENT_FAILURE

        execution = JobExecution(
            id=uuid4(),
            pipeline_id=pipeline_id,
            tenant_id=tenant_id,
            status=job_status,
            started_at=started_at,
            finished_at=finished_at,
            duration_seconds=duration_seconds,
            records_processed=records_processed,
            error_message=error_message,
            is_silent_failure=is_silent_failure,
            metadata_json=metadata_json or {},
        )
        execution = self._execution_repo.save(execution)

        # Generate alert on silent failure
        if is_silent_failure:
            self._create_alert(
                tenant_id=tenant_id,
                pipeline_id=pipeline_id,
                severity=AlertSeverity.CRITICAL,
                alert_type=AlertType.SILENT_FAILURE,
                title=f"Silent failure: {pipeline.name}",
                description=(
                    f"Pipeline '{pipeline.name}' ({pipeline.source} -> "
                    f"{pipeline.destination}) reported success but "
                    f"processed {records_processed} records."
                    + (f" Error: {error_message}" if error_message else "")
                ),
            )

        # Check consecutive failures
        if job_status in (JobStatus.FAILED, JobStatus.SILENT_FAILURE):
            self._check_consecutive_failures(pipeline, tenant_id)

        # Track latency
        if duration_seconds > 0:
            self._track_latency(pipeline_id, tenant_id, duration_seconds)

        return execution

    def list_executions(
        self,
        pipeline_id: UUID,
        page: int = 1,
        size: int = 20,
    ) -> PaginatedResponse[JobExecution]:
        """Return paginated job executions for a pipeline."""
        params = PaginationParams(page=page, size=size)
        items, total = self._execution_repo.list_by_pipeline(
            pipeline_id=pipeline_id,
            offset=params.offset,
            limit=params.size,
        )
        return PaginatedResponse[JobExecution](
            items=items,
            total=total,
            page=params.page,
            size=params.size,
        )

    # -- Latency Drift Tracking -------------------------------------------

    def _track_latency(
        self,
        pipeline_id: UUID,
        tenant_id: UUID,
        duration_seconds: float,
    ) -> LatencyRecord:
        """Record latency and compute drift against baseline."""
        historical = self._latency_repo.get_recent_durations(
            pipeline_id=pipeline_id,
            limit=100,
        )

        result = self._drift_analyzer.analyze(duration_seconds, historical)

        record = LatencyRecord(
            id=uuid4(),
            pipeline_id=pipeline_id,
            tenant_id=tenant_id,
            measured_at=datetime.now(UTC),
            duration_seconds=duration_seconds,
            p50_baseline_seconds=result.p50_baseline,
            p95_baseline_seconds=result.p95_baseline,
            drift_percentage=result.drift_percentage,
        )
        return self._latency_repo.save(record)

    def get_latency_history(
        self,
        pipeline_id: UUID,
        page: int = 1,
        size: int = 50,
    ) -> PaginatedResponse[LatencyRecord]:
        """Return paginated latency history for a pipeline."""
        params = PaginationParams(page=page, size=size)
        items, total = self._latency_repo.list_by_pipeline(
            pipeline_id=pipeline_id,
            offset=params.offset,
            limit=params.size,
        )
        return PaginatedResponse[LatencyRecord](
            items=items,
            total=total,
            page=params.page,
            size=params.size,
        )

    def check_latency_drift(self, pipeline_id: UUID) -> bool:
        """Check a pipeline for latency drift and generate alert if drifting."""
        pipeline = self.get_pipeline(pipeline_id)
        historical = self._latency_repo.get_recent_durations(
            pipeline_id=pipeline_id,
            limit=100,
        )

        if len(historical) < 2:
            return False

        current = historical[-1]
        result = self._drift_analyzer.analyze(current, historical[:-1])

        if result.is_drifting:
            self._create_alert(
                tenant_id=pipeline.tenant_id,
                pipeline_id=pipeline_id,
                severity=AlertSeverity.WARNING,
                alert_type=AlertType.LATENCY_DRIFT,
                title=f"Latency drift: {pipeline.name}",
                description=(
                    f"Pipeline '{pipeline.name}' is +{result.drift_percentage:.1f}% "
                    f"slower than baseline (p50: {result.p50_baseline}s, "
                    f"current: {result.current_duration}s)."
                ),
            )
            return True

        return False

    # -- Consecutive Failure Detection ------------------------------------

    def _check_consecutive_failures(
        self,
        pipeline: Pipeline,
        tenant_id: UUID,
    ) -> None:
        """Check if consecutive failures have reached the threshold."""
        recent = self._execution_repo.list_recent_by_pipeline(
            pipeline_id=pipeline.id,
            limit=pipeline.failure_threshold,
        )

        if len(recent) < pipeline.failure_threshold:
            return

        all_failed = all(
            ex.status in (JobStatus.FAILED, JobStatus.SILENT_FAILURE)
            for ex in recent
        )

        if all_failed:
            self._create_alert(
                tenant_id=tenant_id,
                pipeline_id=pipeline.id,
                severity=AlertSeverity.CRITICAL,
                alert_type=AlertType.CONSECUTIVE_FAILURES,
                title=f"Consecutive failures: {pipeline.name}",
                description=(
                    f"Pipeline '{pipeline.name}' has failed "
                    f"{pipeline.failure_threshold} consecutive times."
                ),
            )

    # -- Alerts -----------------------------------------------------------

    def _create_alert(
        self,
        tenant_id: UUID,
        pipeline_id: UUID,
        severity: AlertSeverity,
        alert_type: AlertType,
        title: str,
        description: str,
    ) -> PipelineAlert:
        """Create and persist a pipeline alert."""
        alert = PipelineAlert(
            id=uuid4(),
            tenant_id=tenant_id,
            pipeline_id=pipeline_id,
            severity=severity,
            alert_type=alert_type,
            title=title,
            description=description,
            created_at=datetime.now(UTC),
        )
        alert = self._alert_repo.save(alert)
        logger.warning("Alert created: [%s] %s", severity.value, title)
        return alert

    def list_alerts(
        self,
        tenant_id: UUID,
        page: int = 1,
        size: int = 20,
    ) -> PaginatedResponse[PipelineAlert]:
        """Return paginated alerts for a tenant."""
        params = PaginationParams(page=page, size=size)
        items, total = self._alert_repo.list_by_tenant(
            tenant_id=tenant_id,
            offset=params.offset,
            limit=params.size,
        )
        return PaginatedResponse[PipelineAlert](
            items=items,
            total=total,
            page=params.page,
            size=params.size,
        )

    def acknowledge_alert(
        self,
        alert_id: UUID,
        acknowledged_by: UUID,
    ) -> PipelineAlert:
        """Mark an alert as acknowledged."""
        alert = self._alert_repo.get_by_id(alert_id)
        if alert is None:
            raise AlertNotFoundError(alert_id=str(alert_id))

        alert.acknowledged = True
        alert.acknowledged_by = acknowledged_by
        alert.acknowledged_at = datetime.now(UTC)
        return self._alert_repo.update(alert)

    # -- Weekly Summary ---------------------------------------------------

    def get_latest_summary(self, tenant_id: UUID) -> WeeklySummary | None:
        """Return the most recent weekly summary for a tenant."""
        return self._summary_repo.get_latest_by_tenant(tenant_id)

    def generate_summary(self, tenant_id: UUID) -> WeeklySummary:
        """Generate a weekly pipeline health summary for a tenant."""
        now = datetime.now(UTC)
        from datetime import timedelta

        week_end = now.date()
        week_start = week_end - timedelta(days=7)

        recent_executions = self._execution_repo.list_recent_by_tenant(
            tenant_id=tenant_id,
            limit=10000,
        )

        total_jobs = len(recent_executions)
        failed_jobs = sum(
            1
            for ex in recent_executions
            if ex.status in (JobStatus.FAILED, JobStatus.SILENT_FAILURE)
        )
        silent_failures = sum(
            1 for ex in recent_executions if ex.is_silent_failure
        )

        # Check pipelines for drift
        pipelines, _ = self._pipeline_repo.list_by_tenant(
            tenant_id=tenant_id,
            offset=0,
            limit=1000,
        )

        drift_percentages: list[float] = []
        for pipeline in pipelines:
            historical = self._latency_repo.get_recent_durations(
                pipeline_id=pipeline.id,
                limit=100,
            )
            if len(historical) >= 2:
                result = self._drift_analyzer.analyze(
                    historical[-1], historical[:-1]
                )
                if result.is_drifting:
                    drift_percentages.append(result.drift_percentage)

        pipelines_with_drift = len(drift_percentages)
        avg_drift = (
            sum(drift_percentages) / len(drift_percentages)
            if drift_percentages
            else 0.0
        )

        # Build top risks
        top_risks: list[dict[str, Any]] = []
        for ex in recent_executions:
            if ex.is_silent_failure:
                pipeline = self._pipeline_repo.get_by_id(ex.pipeline_id)
                name = pipeline.name if pipeline else "Unknown"
                top_risks.append({
                    "type": "silent_failure",
                    "pipeline": name,
                    "description": (
                        f"'{name}' silent failure on "
                        f"{ex.started_at.strftime('%b %d')} at "
                        f"{ex.started_at.strftime('%H:%M')} UTC "
                        f"— {ex.records_processed} records."
                    ),
                })

        for pipeline in pipelines:
            historical = self._latency_repo.get_recent_durations(
                pipeline_id=pipeline.id,
                limit=100,
            )
            if len(historical) >= 2:
                result = self._drift_analyzer.analyze(
                    historical[-1], historical[:-1]
                )
                if result.is_drifting:
                    top_risks.append({
                        "type": "latency_drift",
                        "pipeline": pipeline.name,
                        "description": (
                            f"'{pipeline.name}' is "
                            f"+{result.drift_percentage:.1f}% slower than baseline."
                        ),
                    })

        # Generate plain-English summary
        summary_input = SummaryInput(
            week_start=week_start,
            week_end=week_end,
            total_jobs=total_jobs,
            failed_jobs=failed_jobs,
            silent_failures=silent_failures,
            pipelines_with_drift=pipelines_with_drift,
            avg_drift_percentage=avg_drift,
            top_risks=top_risks[:5],
        )
        plain_english = self._summary_generator.generate(summary_input)

        summary = WeeklySummary(
            id=uuid4(),
            tenant_id=tenant_id,
            week_start=week_start,
            week_end=week_end,
            total_jobs=total_jobs,
            failed_jobs=failed_jobs,
            silent_failures=silent_failures,
            pipelines_with_drift=pipelines_with_drift,
            avg_drift_percentage=round(avg_drift, 1),
            top_risks=top_risks[:5],
            plain_english_summary=plain_english,
            generated_at=datetime.now(UTC),
        )
        return self._summary_repo.save(summary)


# ---------------------------------------------------------------------------
# Domain exceptions
# ---------------------------------------------------------------------------


from domain.exceptions import DomainError  # noqa: E402


class PipelineNotFoundError(DomainError):
    """Raised when a pipeline cannot be found."""

    def __init__(self, pipeline_id: str) -> None:
        super().__init__(
            detail=f"Pipeline '{pipeline_id}' does not exist.",
            title="Pipeline Not Found",
            status_code=404,
            error_type="https://api.eu-platform.example/problems/pipeline-not-found",
        )


class AlertNotFoundError(DomainError):
    """Raised when a pipeline alert cannot be found."""

    def __init__(self, alert_id: str) -> None:
        super().__init__(
            detail=f"Alert '{alert_id}' does not exist.",
            title="Alert Not Found",
            status_code=404,
            error_type="https://api.eu-platform.example/problems/alert-not-found",
        )
