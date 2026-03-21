"""SQLAlchemy implementation of pipeline repositories."""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from domain.models.pipeline import (
    AlertSeverity, AlertType, JobExecution, JobStatus,
    LatencyRecord, Pipeline, PipelineAlert, PipelineStatus, WeeklySummary,
)
from infrastructure.database.models import (
    PipelineModel, JobExecutionModel, LatencyRecordModel,
    PipelineAlertModel, WeeklySummaryModel,
)


def _to_pipeline(m: PipelineModel) -> Pipeline:
    return Pipeline(
        id=m.id, tenant_id=m.tenant_id, name=m.name,
        source=m.source, destination=m.destination,
        schedule_cron=m.schedule_cron or "",
        status=PipelineStatus(m.status),
        expected_duration_seconds=m.expected_duration_seconds or 0.0,
        timeout_seconds=m.timeout_seconds or 3600,
        failure_threshold=m.failure_threshold or 3,
        metadata_json=m.metadata_json or {},
        created_at=m.created_at, updated_at=m.updated_at,
    )


def _to_execution(m: JobExecutionModel) -> JobExecution:
    return JobExecution(
        id=m.id, pipeline_id=m.pipeline_id, tenant_id=m.tenant_id,
        status=JobStatus(m.status),
        started_at=m.started_at, finished_at=m.finished_at,
        duration_seconds=m.duration_seconds or 0.0,
        records_processed=m.records_processed or 0,
        error_message=m.error_message or "",
        is_silent_failure=m.is_silent_failure or False,
        metadata_json=m.metadata_json or {},
    )


def _to_latency(m: LatencyRecordModel) -> LatencyRecord:
    return LatencyRecord(
        id=m.id, pipeline_id=m.pipeline_id, tenant_id=m.tenant_id,
        measured_at=m.measured_at,
        duration_seconds=m.duration_seconds or 0.0,
        p50_baseline_seconds=m.p50_baseline_seconds or 0.0,
        p95_baseline_seconds=m.p95_baseline_seconds or 0.0,
        drift_percentage=m.drift_percentage or 0.0,
    )


def _to_alert(m: PipelineAlertModel) -> PipelineAlert:
    return PipelineAlert(
        id=m.id, tenant_id=m.tenant_id, pipeline_id=m.pipeline_id,
        severity=AlertSeverity(m.severity),
        alert_type=AlertType(m.alert_type),
        title=m.title, description=m.description,
        acknowledged=m.acknowledged or False,
        acknowledged_by=m.acknowledged_by,
        acknowledged_at=m.acknowledged_at,
        created_at=m.created_at,
    )


class SQLPipelineRepository:
    """Postgres-backed pipeline repository."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_id(self, pipeline_id: UUID) -> Pipeline | None:
        m = self._session.get(PipelineModel, pipeline_id)
        return _to_pipeline(m) if m else None

    def list_by_tenant(
        self, tenant_id: UUID, offset: int = 0, limit: int = 20,
    ) -> tuple[list[Pipeline], int]:
        q = select(PipelineModel).where(PipelineModel.tenant_id == tenant_id)
        total = self._session.scalar(select(func.count()).select_from(q.subquery())) or 0
        rows = self._session.scalars(q.offset(offset).limit(limit)).all()
        return [_to_pipeline(r) for r in rows], total

    def save(self, pipeline: Pipeline) -> Pipeline:
        m = PipelineModel(
            id=pipeline.id, tenant_id=pipeline.tenant_id, name=pipeline.name,
            source=pipeline.source, destination=pipeline.destination,
            schedule_cron=pipeline.schedule_cron,
            status=pipeline.status.value,
            expected_duration_seconds=pipeline.expected_duration_seconds,
            timeout_seconds=pipeline.timeout_seconds,
            failure_threshold=pipeline.failure_threshold,
            metadata_json=pipeline.metadata_json,
            created_at=pipeline.created_at, updated_at=pipeline.updated_at,
        )
        self._session.add(m)
        self._session.flush()
        return pipeline

    def update(self, pipeline: Pipeline) -> Pipeline:
        m = self._session.get(PipelineModel, pipeline.id)
        if m:
            m.name = pipeline.name
            m.status = pipeline.status.value
            m.updated_at = pipeline.updated_at
            self._session.flush()
        return pipeline


class SQLJobExecutionRepository:
    """Postgres-backed job execution repository."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_id(self, execution_id: UUID) -> JobExecution | None:
        m = self._session.get(JobExecutionModel, execution_id)
        return _to_execution(m) if m else None

    def list_by_pipeline(
        self, pipeline_id: UUID, offset: int = 0, limit: int = 20,
    ) -> tuple[list[JobExecution], int]:
        q = select(JobExecutionModel).where(JobExecutionModel.pipeline_id == pipeline_id)
        total = self._session.scalar(select(func.count()).select_from(q.subquery())) or 0
        rows = self._session.scalars(
            q.order_by(JobExecutionModel.started_at.desc()).offset(offset).limit(limit)
        ).all()
        return [_to_execution(r) for r in rows], total

    def list_recent_by_pipeline(self, pipeline_id: UUID, limit: int = 10) -> list[JobExecution]:
        rows = self._session.scalars(
            select(JobExecutionModel)
            .where(JobExecutionModel.pipeline_id == pipeline_id)
            .order_by(JobExecutionModel.started_at.desc())
            .limit(limit)
        ).all()
        return [_to_execution(r) for r in rows]

    def list_recent_by_tenant(self, tenant_id: UUID, limit: int = 100) -> list[JobExecution]:
        rows = self._session.scalars(
            select(JobExecutionModel)
            .where(JobExecutionModel.tenant_id == tenant_id)
            .order_by(JobExecutionModel.started_at.desc())
            .limit(limit)
        ).all()
        return [_to_execution(r) for r in rows]

    def save(self, execution: JobExecution) -> JobExecution:
        m = JobExecutionModel(
            id=execution.id, pipeline_id=execution.pipeline_id,
            tenant_id=execution.tenant_id, status=execution.status.value,
            started_at=execution.started_at, finished_at=execution.finished_at,
            duration_seconds=execution.duration_seconds,
            records_processed=execution.records_processed,
            error_message=execution.error_message,
            is_silent_failure=execution.is_silent_failure,
            metadata_json=execution.metadata_json,
        )
        self._session.add(m)
        self._session.flush()
        return execution


class SQLLatencyRecordRepository:
    """Postgres-backed latency record repository."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def list_by_pipeline(
        self, pipeline_id: UUID, offset: int = 0, limit: int = 50,
    ) -> tuple[list[LatencyRecord], int]:
        q = select(LatencyRecordModel).where(LatencyRecordModel.pipeline_id == pipeline_id)
        total = self._session.scalar(select(func.count()).select_from(q.subquery())) or 0
        rows = self._session.scalars(
            q.order_by(LatencyRecordModel.measured_at.desc()).offset(offset).limit(limit)
        ).all()
        return [_to_latency(r) for r in rows], total

    def get_recent_durations(self, pipeline_id: UUID, limit: int = 100) -> list[float]:
        rows = self._session.scalars(
            select(LatencyRecordModel.duration_seconds)
            .where(LatencyRecordModel.pipeline_id == pipeline_id)
            .order_by(LatencyRecordModel.measured_at.asc())
            .limit(limit)
        ).all()
        return list(rows)

    def save(self, record: LatencyRecord) -> LatencyRecord:
        m = LatencyRecordModel(
            id=record.id, pipeline_id=record.pipeline_id,
            tenant_id=record.tenant_id, measured_at=record.measured_at,
            duration_seconds=record.duration_seconds,
            p50_baseline_seconds=record.p50_baseline_seconds,
            p95_baseline_seconds=record.p95_baseline_seconds,
            drift_percentage=record.drift_percentage,
        )
        self._session.add(m)
        self._session.flush()
        return record


class SQLPipelineAlertRepository:
    """Postgres-backed alert repository."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_id(self, alert_id: UUID) -> PipelineAlert | None:
        m = self._session.get(PipelineAlertModel, alert_id)
        return _to_alert(m) if m else None

    def list_by_tenant(
        self, tenant_id: UUID, offset: int = 0, limit: int = 20,
    ) -> tuple[list[PipelineAlert], int]:
        q = select(PipelineAlertModel).where(PipelineAlertModel.tenant_id == tenant_id)
        total = self._session.scalar(select(func.count()).select_from(q.subquery())) or 0
        rows = self._session.scalars(
            q.order_by(PipelineAlertModel.created_at.desc()).offset(offset).limit(limit)
        ).all()
        return [_to_alert(r) for r in rows], total

    def save(self, alert: PipelineAlert) -> PipelineAlert:
        m = PipelineAlertModel(
            id=alert.id, tenant_id=alert.tenant_id, pipeline_id=alert.pipeline_id,
            severity=alert.severity.value, alert_type=alert.alert_type.value,
            title=alert.title, description=alert.description,
            acknowledged=alert.acknowledged,
            created_at=alert.created_at,
        )
        self._session.add(m)
        self._session.flush()
        return alert

    def update(self, alert: PipelineAlert) -> PipelineAlert:
        m = self._session.get(PipelineAlertModel, alert.id)
        if m:
            m.acknowledged = alert.acknowledged
            m.acknowledged_by = alert.acknowledged_by
            m.acknowledged_at = alert.acknowledged_at
            self._session.flush()
        return alert
