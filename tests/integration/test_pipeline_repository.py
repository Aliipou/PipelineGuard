"""Integration tests for PipelineGuard repositories."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from domain.models.pipeline import (
    AlertSeverity,
    AlertType,
    JobExecution,
    JobStatus,
    LatencyRecord,
    Pipeline,
    PipelineAlert,
    WeeklySummary,
)
from infrastructure.adapters import (
    InMemoryJobExecutionRepository,
    InMemoryLatencyRecordRepository,
    InMemoryPipelineAlertRepository,
    InMemoryPipelineRepository,
    InMemoryWeeklySummaryRepository,
)

TENANT_ID = UUID("00000000-0000-0000-0000-000000000001")
PIPELINE_ID = UUID("00000000-0000-0000-0000-000000000010")
NOW = datetime(2026, 2, 17, 12, 0, 0, tzinfo=UTC)


@pytest.mark.integration
class TestPipelineRepository:
    def test_save_and_get(self) -> None:
        repo = InMemoryPipelineRepository()
        pipeline = Pipeline(
            id=PIPELINE_ID,
            tenant_id=TENANT_ID,
            name="Test Pipeline",
            source="Google Ads",
            destination="BigQuery",
        )
        repo.save(pipeline)
        result = repo.get_by_id(PIPELINE_ID)
        assert result is not None
        assert result.name == "Test Pipeline"

    def test_get_nonexistent(self) -> None:
        repo = InMemoryPipelineRepository()
        assert repo.get_by_id(uuid4()) is None

    def test_list_by_tenant(self) -> None:
        repo = InMemoryPipelineRepository()
        for i in range(3):
            repo.save(
                Pipeline(id=uuid4(), tenant_id=TENANT_ID, name=f"P{i}", source="s", destination="d")
            )
        repo.save(
            Pipeline(id=uuid4(), tenant_id=uuid4(), name="Other", source="s", destination="d")
        )
        _items, total = repo.list_by_tenant(TENANT_ID)
        assert total == 3

    def test_list_pagination(self) -> None:
        repo = InMemoryPipelineRepository()
        for i in range(5):
            repo.save(
                Pipeline(id=uuid4(), tenant_id=TENANT_ID, name=f"P{i}", source="s", destination="d")
            )
        items, total = repo.list_by_tenant(TENANT_ID, offset=2, limit=2)
        assert len(items) == 2
        assert total == 5

    def test_update(self) -> None:
        repo = InMemoryPipelineRepository()
        pipeline = Pipeline(
            id=PIPELINE_ID, tenant_id=TENANT_ID, name="Original", source="s", destination="d"
        )
        repo.save(pipeline)
        pipeline.name = "Updated"
        repo.update(pipeline)
        result = repo.get_by_id(PIPELINE_ID)
        assert result is not None
        assert result.name == "Updated"


@pytest.mark.integration
class TestJobExecutionRepository:
    def test_save_and_get(self) -> None:
        repo = InMemoryJobExecutionRepository()
        ex = JobExecution(
            id=uuid4(), pipeline_id=PIPELINE_ID, tenant_id=TENANT_ID, status=JobStatus.SUCCEEDED
        )
        repo.save(ex)
        result = repo.get_by_id(ex.id)
        assert result is not None

    def test_list_by_pipeline(self) -> None:
        repo = InMemoryJobExecutionRepository()
        for _ in range(3):
            repo.save(JobExecution(id=uuid4(), pipeline_id=PIPELINE_ID, tenant_id=TENANT_ID))
        _items, total = repo.list_by_pipeline(PIPELINE_ID)
        assert total == 3

    def test_list_recent_by_pipeline(self) -> None:
        repo = InMemoryJobExecutionRepository()
        for _ in range(5):
            repo.save(JobExecution(id=uuid4(), pipeline_id=PIPELINE_ID, tenant_id=TENANT_ID))
        recent = repo.list_recent_by_pipeline(PIPELINE_ID, limit=3)
        assert len(recent) == 3

    def test_list_recent_by_tenant(self) -> None:
        repo = InMemoryJobExecutionRepository()
        for _ in range(5):
            repo.save(JobExecution(id=uuid4(), pipeline_id=PIPELINE_ID, tenant_id=TENANT_ID))
        recent = repo.list_recent_by_tenant(TENANT_ID, limit=3)
        assert len(recent) == 3


@pytest.mark.integration
class TestLatencyRecordRepository:
    def test_save_and_list(self) -> None:
        repo = InMemoryLatencyRecordRepository()
        for i in range(5):
            repo.save(
                LatencyRecord(
                    id=uuid4(),
                    pipeline_id=PIPELINE_ID,
                    tenant_id=TENANT_ID,
                    duration_seconds=100.0 + i,
                )
            )
        _items, total = repo.list_by_pipeline(PIPELINE_ID)
        assert total == 5

    def test_get_recent_durations(self) -> None:
        repo = InMemoryLatencyRecordRepository()
        for i in range(10):
            repo.save(
                LatencyRecord(
                    id=uuid4(),
                    pipeline_id=PIPELINE_ID,
                    tenant_id=TENANT_ID,
                    duration_seconds=float(i * 10),
                )
            )
        durations = repo.get_recent_durations(PIPELINE_ID, limit=5)
        assert len(durations) == 5
        assert durations == [50.0, 60.0, 70.0, 80.0, 90.0]


@pytest.mark.integration
class TestPipelineAlertRepository:
    def test_save_and_get(self) -> None:
        repo = InMemoryPipelineAlertRepository()
        alert = PipelineAlert(
            id=uuid4(),
            tenant_id=TENANT_ID,
            pipeline_id=PIPELINE_ID,
            severity=AlertSeverity.CRITICAL,
            alert_type=AlertType.SILENT_FAILURE,
            title="Test",
        )
        repo.save(alert)
        result = repo.get_by_id(alert.id)
        assert result is not None
        assert result.title == "Test"

    def test_list_by_tenant(self) -> None:
        repo = InMemoryPipelineAlertRepository()
        for _ in range(3):
            repo.save(
                PipelineAlert(
                    id=uuid4(),
                    tenant_id=TENANT_ID,
                    pipeline_id=PIPELINE_ID,
                    title="Alert",
                )
            )
        _items, total = repo.list_by_tenant(TENANT_ID)
        assert total == 3

    def test_update(self) -> None:
        repo = InMemoryPipelineAlertRepository()
        alert = PipelineAlert(
            id=uuid4(), tenant_id=TENANT_ID, pipeline_id=PIPELINE_ID, title="Original"
        )
        repo.save(alert)
        alert.acknowledged = True
        repo.update(alert)
        result = repo.get_by_id(alert.id)
        assert result is not None
        assert result.acknowledged is True


@pytest.mark.integration
class TestWeeklySummaryRepository:
    def test_save_and_get_latest(self) -> None:
        repo = InMemoryWeeklySummaryRepository()
        s1 = WeeklySummary(id=uuid4(), tenant_id=TENANT_ID, total_jobs=10)
        s2 = WeeklySummary(id=uuid4(), tenant_id=TENANT_ID, total_jobs=20)
        repo.save(s1)
        repo.save(s2)
        latest = repo.get_latest_by_tenant(TENANT_ID)
        assert latest is not None
        assert latest.total_jobs == 20

    def test_get_latest_none(self) -> None:
        repo = InMemoryWeeklySummaryRepository()
        assert repo.get_latest_by_tenant(uuid4()) is None
