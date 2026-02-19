"""Contract tests for PipelineGuard API schemas and validation."""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

TENANT_ID = str(uuid.uuid4())
TENANT_HEADERS = {"X-Tenant-ID": TENANT_ID}


@pytest.fixture
def client():
    from presentation.main import create_app
    from starlette.testclient import TestClient

    return TestClient(create_app())


@pytest.mark.contract
class TestPipelineValidation:

    def test_create_pipeline_missing_name(self, client) -> None:
        resp = client.post(
            f"/api/v1/tenants/{TENANT_ID}/pipelines",
            json={"source": "Google Ads", "destination": "BigQuery"},
            headers=TENANT_HEADERS,
        )
        assert resp.status_code == 422
        data = resp.json()
        assert data["title"] == "Validation Error"
        assert any("name" in e.get("field", "") for e in data.get("errors", []))

    def test_create_pipeline_missing_source(self, client) -> None:
        resp = client.post(
            f"/api/v1/tenants/{TENANT_ID}/pipelines",
            json={"name": "Test", "destination": "BigQuery"},
            headers=TENANT_HEADERS,
        )
        assert resp.status_code == 422

    def test_create_pipeline_missing_destination(self, client) -> None:
        resp = client.post(
            f"/api/v1/tenants/{TENANT_ID}/pipelines",
            json={"name": "Test", "source": "Google Ads"},
            headers=TENANT_HEADERS,
        )
        assert resp.status_code == 422

    def test_create_pipeline_name_too_short(self, client) -> None:
        resp = client.post(
            f"/api/v1/tenants/{TENANT_ID}/pipelines",
            json={"name": "x", "source": "Google Ads", "destination": "BigQuery"},
            headers=TENANT_HEADERS,
        )
        assert resp.status_code == 422

    def test_create_pipeline_success(self, client) -> None:
        resp = client.post(
            f"/api/v1/tenants/{TENANT_ID}/pipelines",
            json={
                "name": "Google Ads -> BigQuery",
                "source": "Google Ads",
                "destination": "BigQuery",
            },
            headers=TENANT_HEADERS,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Google Ads -> BigQuery"
        assert data["source"] == "Google Ads"
        assert data["destination"] == "BigQuery"
        assert data["status"] == "ACTIVE"
        assert "id" in data
        assert "created_at" in data


@pytest.mark.contract
class TestExecutionValidation:

    def _create_pipeline(self, client) -> str:
        resp = client.post(
            f"/api/v1/tenants/{TENANT_ID}/pipelines",
            json={
                "name": "Test Pipeline",
                "source": "src",
                "destination": "dst",
            },
            headers=TENANT_HEADERS,
        )
        return resp.json()["id"]

    def test_report_execution_missing_status(self, client) -> None:
        pipeline_id = self._create_pipeline(client)
        resp = client.post(
            f"/api/v1/tenants/{TENANT_ID}/pipelines/{pipeline_id}/executions",
            json={"started_at": "2026-02-18T03:00:00Z"},
            headers=TENANT_HEADERS,
        )
        assert resp.status_code == 422

    def test_report_execution_missing_started_at(self, client) -> None:
        pipeline_id = self._create_pipeline(client)
        resp = client.post(
            f"/api/v1/tenants/{TENANT_ID}/pipelines/{pipeline_id}/executions",
            json={"status": "SUCCEEDED"},
            headers=TENANT_HEADERS,
        )
        assert resp.status_code == 422

    def test_report_execution_success(self, client) -> None:
        pipeline_id = self._create_pipeline(client)
        resp = client.post(
            f"/api/v1/tenants/{TENANT_ID}/pipelines/{pipeline_id}/executions",
            json={
                "status": "SUCCEEDED",
                "started_at": "2026-02-18T03:00:00Z",
                "finished_at": "2026-02-18T03:02:05Z",
                "duration_seconds": 125.3,
                "records_processed": 500,
            },
            headers=TENANT_HEADERS,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "SUCCEEDED"
        assert data["is_silent_failure"] is False

    def test_silent_failure_auto_detected(self, client) -> None:
        pipeline_id = self._create_pipeline(client)
        resp = client.post(
            f"/api/v1/tenants/{TENANT_ID}/pipelines/{pipeline_id}/executions",
            json={
                "status": "SUCCEEDED",
                "started_at": "2026-02-18T03:00:00Z",
                "duration_seconds": 125.3,
                "records_processed": 0,
            },
            headers=TENANT_HEADERS,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "SILENT_FAILURE"
        assert data["is_silent_failure"] is True


@pytest.mark.contract
class TestPipelineResponseSchemas:

    def test_list_pipelines_response_shape(self, client) -> None:
        resp = client.get(
            f"/api/v1/tenants/{TENANT_ID}/pipelines",
            headers=TENANT_HEADERS,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "pagination" in data
        pagination = data["pagination"]
        assert "page" in pagination
        assert "page_size" in pagination
        assert "total_items" in pagination
        assert "total_pages" in pagination

    def test_alerts_response_shape(self, client) -> None:
        resp = client.get(
            f"/api/v1/tenants/{TENANT_ID}/alerts",
            headers=TENANT_HEADERS,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "pagination" in data

    def test_summary_response_null_when_empty(self, client) -> None:
        resp = client.get(
            f"/api/v1/tenants/{TENANT_ID}/summary",
            headers=TENANT_HEADERS,
        )
        assert resp.status_code == 200

    def test_generate_summary_response(self, client) -> None:
        resp = client.post(
            f"/api/v1/tenants/{TENANT_ID}/summary/generate",
            headers=TENANT_HEADERS,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert "plain_english_summary" in data
        assert "total_jobs" in data
        assert "week_start" in data
        assert "week_end" in data


@pytest.mark.contract
class TestPipelineRFC9457:

    def test_pipeline_not_found_returns_problem_json(self, client) -> None:
        fake_id = str(uuid.uuid4())
        resp = client.get(
            f"/api/v1/tenants/{TENANT_ID}/pipelines/{fake_id}",
            headers=TENANT_HEADERS,
        )
        assert resp.status_code == 404
        data = resp.json()
        assert "type" in data
        assert "title" in data
        assert "status" in data
        assert data["status"] == 404

    def test_alert_not_found_returns_problem_json(self, client) -> None:
        fake_id = str(uuid.uuid4())
        resp = client.post(
            f"/api/v1/tenants/{TENANT_ID}/alerts/{fake_id}/acknowledge",
            json={"acknowledged_by": str(uuid.uuid4())},
            headers=TENANT_HEADERS,
        )
        assert resp.status_code == 404
        data = resp.json()
        assert data["status"] == 404
