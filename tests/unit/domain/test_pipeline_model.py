"""Unit tests for PipelineGuard domain models."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

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


class TestPipeline:
    def test_default_values(self) -> None:
        p = Pipeline(name="test", source="src", destination="dst")
        assert p.name == "test"
        assert p.source == "src"
        assert p.destination == "dst"
        assert p.status == PipelineStatus.ACTIVE
        assert p.timeout_seconds == 3600
        assert p.failure_threshold == 3
        assert isinstance(p.metadata_json, dict)

    def test_custom_values(self) -> None:
        p = Pipeline(
            name="Google Ads -> BigQuery",
            source="Google Ads",
            destination="BigQuery",
            schedule_cron="0 3 * * *",
            failure_threshold=5,
            timeout_seconds=7200,
        )
        assert p.failure_threshold == 5
        assert p.timeout_seconds == 7200
        assert p.schedule_cron == "0 3 * * *"


class TestJobExecution:
    def test_default_values(self) -> None:
        ex = JobExecution()
        assert ex.status == JobStatus.RUNNING
        assert ex.records_processed == 0
        assert ex.is_silent_failure is False
        assert ex.error_message == ""

    def test_silent_failure_fields(self) -> None:
        ex = JobExecution(
            status=JobStatus.SILENT_FAILURE,
            records_processed=0,
            is_silent_failure=True,
        )
        assert ex.is_silent_failure is True
        assert ex.status == JobStatus.SILENT_FAILURE


class TestLatencyRecord:
    def test_default_values(self) -> None:
        r = LatencyRecord()
        assert r.duration_seconds == 0.0
        assert r.drift_percentage == 0.0
        assert r.p50_baseline_seconds == 0.0

    def test_with_drift(self) -> None:
        r = LatencyRecord(
            duration_seconds=150.0,
            p50_baseline_seconds=100.0,
            drift_percentage=50.0,
        )
        assert r.drift_percentage == 50.0


class TestPipelineAlert:
    def test_default_values(self) -> None:
        a = PipelineAlert(title="Test alert")
        assert a.acknowledged is False
        assert a.acknowledged_by is None
        assert a.severity == AlertSeverity.WARNING

    def test_critical_alert(self) -> None:
        a = PipelineAlert(
            severity=AlertSeverity.CRITICAL,
            alert_type=AlertType.SILENT_FAILURE,
            title="Silent failure detected",
        )
        assert a.severity == AlertSeverity.CRITICAL
        assert a.alert_type == AlertType.SILENT_FAILURE


class TestWeeklySummary:
    def test_default_values(self) -> None:
        s = WeeklySummary()
        assert s.total_jobs == 0
        assert s.failed_jobs == 0
        assert s.silent_failures == 0
        assert s.plain_english_summary == ""

    def test_with_data(self) -> None:
        s = WeeklySummary(
            total_jobs=100,
            failed_jobs=5,
            silent_failures=2,
            pipelines_with_drift=1,
            avg_drift_percentage=34.5,
        )
        assert s.total_jobs == 100
        assert s.silent_failures == 2


class TestEnums:
    def test_pipeline_status_values(self) -> None:
        assert PipelineStatus.ACTIVE.value == "ACTIVE"
        assert PipelineStatus.PAUSED.value == "PAUSED"
        assert PipelineStatus.DISABLED.value == "DISABLED"

    def test_job_status_values(self) -> None:
        assert JobStatus.RUNNING.value == "RUNNING"
        assert JobStatus.SUCCEEDED.value == "SUCCEEDED"
        assert JobStatus.FAILED.value == "FAILED"
        assert JobStatus.SILENT_FAILURE.value == "SILENT_FAILURE"

    def test_alert_severity_values(self) -> None:
        assert AlertSeverity.WARNING.value == "WARNING"
        assert AlertSeverity.CRITICAL.value == "CRITICAL"

    def test_alert_type_values(self) -> None:
        assert AlertType.SILENT_FAILURE.value == "SILENT_FAILURE"
        assert AlertType.LATENCY_DRIFT.value == "LATENCY_DRIFT"
        assert AlertType.CONSECUTIVE_FAILURES.value == "CONSECUTIVE_FAILURES"
