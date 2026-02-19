"""Unit tests for PipelineService application service."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from application.services.pipeline_service import (
    AlertNotFoundError,
    PipelineNotFoundError,
    PipelineService,
)
from domain.models.pipeline import (
    AlertSeverity,
    AlertType,
    JobExecution,
    JobStatus,
    Pipeline,
    PipelineStatus,
)
from domain.services.drift_analyzer import DriftAnalyzer
from domain.services.summary_generator import SummaryGenerator
from infrastructure.adapters import (
    InMemoryJobExecutionRepository,
    InMemoryLatencyRecordRepository,
    InMemoryPipelineAlertRepository,
    InMemoryPipelineRepository,
    InMemoryWeeklySummaryRepository,
)

TENANT_ID = UUID("00000000-0000-0000-0000-000000000001")
NOW = datetime(2026, 2, 17, 12, 0, 0, tzinfo=UTC)


@pytest.fixture
def svc() -> PipelineService:
    return PipelineService(
        pipeline_repo=InMemoryPipelineRepository(),
        execution_repo=InMemoryJobExecutionRepository(),
        latency_repo=InMemoryLatencyRecordRepository(),
        alert_repo=InMemoryPipelineAlertRepository(),
        summary_repo=InMemoryWeeklySummaryRepository(),
        drift_analyzer=DriftAnalyzer(),
        summary_generator=SummaryGenerator(),
    )


class TestRegisterPipeline:
    def test_register_success(self, svc: PipelineService) -> None:
        pipeline = svc.register_pipeline(
            tenant_id=TENANT_ID,
            name="Google Ads -> BigQuery",
            source="Google Ads",
            destination="BigQuery",
        )
        assert pipeline.name == "Google Ads -> BigQuery"
        assert pipeline.tenant_id == TENANT_ID
        assert pipeline.status == PipelineStatus.ACTIVE

    def test_register_with_custom_settings(self, svc: PipelineService) -> None:
        pipeline = svc.register_pipeline(
            tenant_id=TENANT_ID,
            name="Test",
            source="src",
            destination="dst",
            failure_threshold=5,
            timeout_seconds=7200,
        )
        assert pipeline.failure_threshold == 5
        assert pipeline.timeout_seconds == 7200


class TestGetPipeline:
    def test_get_existing(self, svc: PipelineService) -> None:
        created = svc.register_pipeline(
            tenant_id=TENANT_ID, name="Test", source="s", destination="d"
        )
        found = svc.get_pipeline(created.id)
        assert found.id == created.id

    def test_get_nonexistent_raises(self, svc: PipelineService) -> None:
        with pytest.raises(PipelineNotFoundError):
            svc.get_pipeline(uuid4())


class TestListPipelines:
    def test_list_empty(self, svc: PipelineService) -> None:
        result = svc.list_pipelines(TENANT_ID)
        assert result.total == 0
        assert result.items == []

    def test_list_with_items(self, svc: PipelineService) -> None:
        svc.register_pipeline(tenant_id=TENANT_ID, name="P1", source="s", destination="d")
        svc.register_pipeline(tenant_id=TENANT_ID, name="P2", source="s", destination="d")
        result = svc.list_pipelines(TENANT_ID)
        assert result.total == 2

    def test_list_filters_by_tenant(self, svc: PipelineService) -> None:
        other_tenant = uuid4()
        svc.register_pipeline(tenant_id=TENANT_ID, name="P1", source="s", destination="d")
        svc.register_pipeline(tenant_id=other_tenant, name="P2", source="s", destination="d")
        result = svc.list_pipelines(TENANT_ID)
        assert result.total == 1


class TestRecordExecution:
    def test_normal_success(self, svc: PipelineService) -> None:
        pipeline = svc.register_pipeline(
            tenant_id=TENANT_ID, name="Test", source="s", destination="d"
        )
        execution = svc.record_execution(
            pipeline_id=pipeline.id,
            tenant_id=TENANT_ID,
            status="SUCCEEDED",
            started_at=NOW,
            duration_seconds=100.0,
            records_processed=500,
        )
        assert execution.status == JobStatus.SUCCEEDED
        assert execution.is_silent_failure is False

    def test_silent_failure_zero_records(self, svc: PipelineService) -> None:
        pipeline = svc.register_pipeline(
            tenant_id=TENANT_ID, name="Test", source="s", destination="d"
        )
        execution = svc.record_execution(
            pipeline_id=pipeline.id,
            tenant_id=TENANT_ID,
            status="SUCCEEDED",
            started_at=NOW,
            duration_seconds=100.0,
            records_processed=0,
        )
        assert execution.status == JobStatus.SILENT_FAILURE
        assert execution.is_silent_failure is True

    def test_silent_failure_error_message(self, svc: PipelineService) -> None:
        pipeline = svc.register_pipeline(
            tenant_id=TENANT_ID, name="Test", source="s", destination="d"
        )
        execution = svc.record_execution(
            pipeline_id=pipeline.id,
            tenant_id=TENANT_ID,
            status="SUCCEEDED",
            started_at=NOW,
            duration_seconds=100.0,
            records_processed=50,
            error_message="Partial data warning",
        )
        assert execution.status == JobStatus.SILENT_FAILURE
        assert execution.is_silent_failure is True

    def test_silent_failure_creates_alert(self, svc: PipelineService) -> None:
        pipeline = svc.register_pipeline(
            tenant_id=TENANT_ID, name="Test Pipeline", source="s", destination="d"
        )
        svc.record_execution(
            pipeline_id=pipeline.id,
            tenant_id=TENANT_ID,
            status="SUCCEEDED",
            started_at=NOW,
            records_processed=0,
        )
        alerts = svc.list_alerts(TENANT_ID)
        assert alerts.total >= 1
        alert = alerts.items[0]
        assert alert.alert_type == AlertType.SILENT_FAILURE
        assert alert.severity == AlertSeverity.CRITICAL

    def test_failed_execution_no_silent_failure(self, svc: PipelineService) -> None:
        pipeline = svc.register_pipeline(
            tenant_id=TENANT_ID, name="Test", source="s", destination="d"
        )
        execution = svc.record_execution(
            pipeline_id=pipeline.id,
            tenant_id=TENANT_ID,
            status="FAILED",
            started_at=NOW,
            records_processed=0,
        )
        assert execution.status == JobStatus.FAILED
        assert execution.is_silent_failure is False

    def test_nonexistent_pipeline_raises(self, svc: PipelineService) -> None:
        with pytest.raises(PipelineNotFoundError):
            svc.record_execution(
                pipeline_id=uuid4(),
                tenant_id=TENANT_ID,
                status="SUCCEEDED",
                started_at=NOW,
            )


class TestConsecutiveFailures:
    def test_consecutive_failures_alert(self, svc: PipelineService) -> None:
        pipeline = svc.register_pipeline(
            tenant_id=TENANT_ID,
            name="Flaky Pipeline",
            source="s",
            destination="d",
            failure_threshold=3,
        )
        for i in range(3):
            svc.record_execution(
                pipeline_id=pipeline.id,
                tenant_id=TENANT_ID,
                status="FAILED",
                started_at=NOW,
            )
        alerts = svc.list_alerts(TENANT_ID)
        consecutive_alerts = [
            a for a in alerts.items if a.alert_type == AlertType.CONSECUTIVE_FAILURES
        ]
        assert len(consecutive_alerts) >= 1

    def test_no_alert_below_threshold(self, svc: PipelineService) -> None:
        pipeline = svc.register_pipeline(
            tenant_id=TENANT_ID,
            name="Flaky Pipeline",
            source="s",
            destination="d",
            failure_threshold=3,
        )
        for i in range(2):
            svc.record_execution(
                pipeline_id=pipeline.id,
                tenant_id=TENANT_ID,
                status="FAILED",
                started_at=NOW,
            )
        alerts = svc.list_alerts(TENANT_ID)
        consecutive_alerts = [
            a for a in alerts.items if a.alert_type == AlertType.CONSECUTIVE_FAILURES
        ]
        assert len(consecutive_alerts) == 0


class TestAcknowledgeAlert:
    def test_acknowledge_success(self, svc: PipelineService) -> None:
        pipeline = svc.register_pipeline(
            tenant_id=TENANT_ID, name="Test", source="s", destination="d"
        )
        svc.record_execution(
            pipeline_id=pipeline.id,
            tenant_id=TENANT_ID,
            status="SUCCEEDED",
            started_at=NOW,
            records_processed=0,
        )
        alerts = svc.list_alerts(TENANT_ID)
        assert alerts.total >= 1

        user_id = uuid4()
        acked = svc.acknowledge_alert(alerts.items[0].id, user_id)
        assert acked.acknowledged is True
        assert acked.acknowledged_by == user_id

    def test_acknowledge_nonexistent_raises(self, svc: PipelineService) -> None:
        with pytest.raises(AlertNotFoundError):
            svc.acknowledge_alert(uuid4(), uuid4())


class TestWeeklySummary:
    def test_generate_empty_summary(self, svc: PipelineService) -> None:
        summary = svc.generate_summary(TENANT_ID)
        assert summary.total_jobs == 0
        assert summary.failed_jobs == 0
        assert "100.0%" in summary.plain_english_summary

    def test_generate_summary_with_data(self, svc: PipelineService) -> None:
        pipeline = svc.register_pipeline(
            tenant_id=TENANT_ID, name="Test", source="s", destination="d"
        )
        # Record some executions
        for _ in range(5):
            svc.record_execution(
                pipeline_id=pipeline.id,
                tenant_id=TENANT_ID,
                status="SUCCEEDED",
                started_at=NOW,
                duration_seconds=100.0,
                records_processed=100,
            )
        svc.record_execution(
            pipeline_id=pipeline.id,
            tenant_id=TENANT_ID,
            status="FAILED",
            started_at=NOW,
        )
        summary = svc.generate_summary(TENANT_ID)
        assert summary.total_jobs == 6
        assert summary.failed_jobs == 1
        assert "RELIABILITY" in summary.plain_english_summary

    def test_get_latest_summary_none(self, svc: PipelineService) -> None:
        result = svc.get_latest_summary(TENANT_ID)
        assert result is None

    def test_get_latest_summary_after_generate(self, svc: PipelineService) -> None:
        svc.generate_summary(TENANT_ID)
        result = svc.get_latest_summary(TENANT_ID)
        assert result is not None
        assert result.tenant_id == TENANT_ID
