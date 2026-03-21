"""Tests for the Slack notification service."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from infrastructure.notifications.slack import AlertPayload, NullNotifier, SlackNotifier


class TestSlackNotifier:
    def test_send_alert_success(self):
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)

        notifier = SlackNotifier(webhook_url="https://hooks.slack.com/test")

        with patch("urllib.request.urlopen", return_value=mock_response) as mock_open:
            result = notifier.send_alert(AlertPayload(
                severity="CRITICAL",
                alert_type="SILENT_FAILURE",
                title="Silent Failure: nightly-etl",
                description="Pipeline processed 0 records.",
                pipeline_name="nightly-etl",
                tenant_id="tenant-uuid-1234",
                alert_id="alert-uuid-5678",
            ))

        assert result is True
        call_args = mock_open.call_args[0][0]
        payload = json.loads(call_args.data)
        attachment = payload["attachments"][0]
        assert attachment["color"] == "#E01E5A"  # red for CRITICAL

    def test_send_alert_network_error_returns_false(self):
        notifier = SlackNotifier(webhook_url="https://hooks.slack.com/unreachable")

        with patch("urllib.request.urlopen", side_effect=Exception("connection refused")):
            result = notifier.send_alert(AlertPayload(
                severity="WARNING",
                alert_type="LATENCY_DRIFT",
                title="Latency drift",
                description="Pipeline is 40% slower than baseline.",
                pipeline_name="hourly-sync",
                tenant_id="tenant-uuid",
                alert_id="alert-uuid",
            ))

        assert result is False

    def test_empty_webhook_url_raises(self):
        import pytest
        with pytest.raises(ValueError, match="webhook URL"):
            SlackNotifier(webhook_url="")

    def test_warning_has_yellow_color(self):
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)

        notifier = SlackNotifier(webhook_url="https://hooks.slack.com/test")

        with patch("urllib.request.urlopen", return_value=mock_response) as mock_open:
            notifier.send_alert(AlertPayload(
                severity="WARNING",
                alert_type="LATENCY_DRIFT",
                title="Drift detected",
                description="25% above baseline.",
                pipeline_name="daily-aggregation",
                tenant_id="tenant-uuid",
                alert_id="alert-uuid",
            ))

        payload = json.loads(mock_open.call_args[0][0].data)
        assert payload["attachments"][0]["color"] == "#ECB22E"


class TestNullNotifier:
    def test_always_returns_true(self):
        notifier = NullNotifier()
        result = notifier.send_alert(AlertPayload(
            severity="CRITICAL",
            alert_type="SILENT_FAILURE",
            title="Test",
            description="Test",
            pipeline_name="test",
            tenant_id="t",
            alert_id="a",
        ))
        assert result is True
