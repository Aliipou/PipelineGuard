"""Tests for the PipelineGuard Python SDK."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from pipelineguard.sdk import PipelineGuardClient, guard


class TestPipelineGuardClient:
    def test_report_execution_success(self):
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read.return_value = json.dumps({"id": "abc"}).encode()
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)

        client = PipelineGuardClient(
            api_url="http://localhost:8000",
            api_key="pg_test_key",
            tenant_id="tenant-uuid",
        )

        with patch("urllib.request.urlopen", return_value=mock_response):
            result = client.report_execution(
                pipeline_id="pipe-uuid",
                status="SUCCEEDED",
                started_at=datetime.now(UTC),
                finished_at=datetime.now(UTC),
                duration_seconds=42.5,
                records_processed=1000,
            )

        assert result == {"id": "abc"}

    def test_report_execution_network_error_returns_error_dict(self):
        client = PipelineGuardClient(
            api_url="http://unreachable:9999",
            api_key="pg_test_key",
            tenant_id="tenant-uuid",
        )

        result = client.report_execution(
            pipeline_id="pipe-uuid",
            status="SUCCEEDED",
            started_at=datetime.now(UTC),
            finished_at=datetime.now(UTC),
            duration_seconds=1.0,
        )

        assert "error" in result


class TestGuardDecorator:
    def test_successful_function_reports_succeeded(self):
        reports = []

        def mock_report(**kwargs):
            reports.append(kwargs)
            return {"id": "abc"}

        with patch(
            "pipelineguard.sdk.PipelineGuardClient.report_execution", side_effect=mock_report
        ):

            @guard(
                pipeline_id="pipe-uuid",
                tenant_id="tenant-uuid",
                api_url="http://localhost:8000",
                api_key="pg_test",
            )
            def my_pipeline() -> int:
                return 500

            result = my_pipeline()

        assert result == 500
        assert len(reports) == 1
        assert reports[0]["status"] == "SUCCEEDED"
        assert reports[0]["records_processed"] == 500

    def test_failing_function_reports_failed_and_reraises(self):
        reports = []

        def mock_report(**kwargs):
            reports.append(kwargs)
            return {}

        with patch(
            "pipelineguard.sdk.PipelineGuardClient.report_execution", side_effect=mock_report
        ):

            @guard(
                pipeline_id="pipe-uuid",
                tenant_id="tenant-uuid",
                api_url="http://localhost:8000",
                api_key="pg_test",
            )
            def broken_pipeline():
                raise ValueError("upstream timeout")

            with pytest.raises(ValueError, match="upstream timeout"):
                broken_pipeline()

        assert len(reports) == 1
        assert reports[0]["status"] == "FAILED"
        assert "upstream timeout" in reports[0]["error_message"]

    def test_zero_return_is_not_counted_as_silent_failure_by_sdk(self):
        """The SDK reports the count honestly — PipelineGuard server detects silent failures."""
        reports = []

        def mock_report(**kwargs):
            reports.append(kwargs)
            return {}

        with patch(
            "pipelineguard.sdk.PipelineGuardClient.report_execution", side_effect=mock_report
        ):

            @guard(
                pipeline_id="pipe-uuid",
                tenant_id="tenant-uuid",
                api_url="http://localhost:8000",
                api_key="pg_test",
            )
            def empty_pipeline() -> int:
                return 0  # nothing to process today

            empty_pipeline()

        assert reports[0]["records_processed"] == 0
        assert reports[0]["status"] == "SUCCEEDED"
        # The server will detect this as a silent failure and alert
