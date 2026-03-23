"""Tests for the Microsoft Teams notification service."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from infrastructure.notifications.teams import TeamsAlertPayload, TeamsNotifier


def _make_payload(**kwargs) -> TeamsAlertPayload:
    defaults = dict(
        severity="CRITICAL",
        alert_type="SILENT_FAILURE",
        title="Pipeline down",
        description="0 records processed.",
        pipeline_name="nightly-etl",
        tenant_id="tenant-uuid-1234",
        alert_id="alert-uuid-5678",
    )
    defaults.update(kwargs)
    return TeamsAlertPayload(**defaults)


def _mock_response(status: int = 200):
    mock = MagicMock()
    mock.status = status
    mock.__enter__ = lambda s: s
    mock.__exit__ = MagicMock(return_value=False)
    return mock


class TestTeamsNotifier:
    def test_send_alert_success_returns_true(self):
        notifier = TeamsNotifier(webhook_url="https://teams.webhook/test")
        with patch("urllib.request.urlopen", return_value=_mock_response(200)):
            assert notifier.send_alert(_make_payload()) is True

    def test_send_alert_2xx_returns_true(self):
        notifier = TeamsNotifier(webhook_url="https://teams.webhook/test")
        with patch("urllib.request.urlopen", return_value=_mock_response(204)):
            assert notifier.send_alert(_make_payload()) is True

    def test_send_alert_4xx_returns_false(self):
        notifier = TeamsNotifier(webhook_url="https://teams.webhook/test")
        with patch("urllib.request.urlopen", return_value=_mock_response(400)):
            assert notifier.send_alert(_make_payload()) is False

    def test_send_alert_5xx_returns_false(self):
        notifier = TeamsNotifier(webhook_url="https://teams.webhook/test")
        with patch("urllib.request.urlopen", return_value=_mock_response(500)):
            assert notifier.send_alert(_make_payload()) is False

    def test_network_error_returns_false(self):
        notifier = TeamsNotifier(webhook_url="https://teams.webhook/test")
        with patch("urllib.request.urlopen", side_effect=OSError("connection refused")):
            assert notifier.send_alert(_make_payload()) is False

    def test_empty_url_raises_value_error(self):
        with pytest.raises(ValueError, match="webhook URL"):
            TeamsNotifier(webhook_url="")

    def test_payload_is_json(self):
        notifier = TeamsNotifier(webhook_url="https://teams.webhook/test")
        captured = {}

        def capture(req, timeout):
            captured["data"] = req.data
            captured["headers"] = req.headers
            return _mock_response(200)

        with patch("urllib.request.urlopen", side_effect=capture):
            notifier.send_alert(_make_payload())

        body = json.loads(captured["data"])
        assert body["type"] == "message"
        assert "attachments" in body

    def test_critical_severity_uses_attention_color(self):
        notifier = TeamsNotifier(webhook_url="https://teams.webhook/test")
        captured = {}

        def capture(req, timeout):
            captured["data"] = req.data
            return _mock_response(200)

        with patch("urllib.request.urlopen", side_effect=capture):
            notifier.send_alert(_make_payload(severity="CRITICAL"))

        body = json.loads(captured["data"])
        card = body["attachments"][0]["content"]
        title_block = card["body"][0]
        assert title_block["color"] == "attention"

    def test_warning_severity_uses_warning_color(self):
        notifier = TeamsNotifier(webhook_url="https://teams.webhook/test")
        captured = {}

        def capture(req, timeout):
            captured["data"] = req.data
            return _mock_response(200)

        with patch("urllib.request.urlopen", side_effect=capture):
            notifier.send_alert(_make_payload(severity="WARNING"))

        body = json.loads(captured["data"])
        card = body["attachments"][0]["content"]
        assert card["body"][0]["color"] == "warning"

    def test_unknown_severity_uses_default_color(self):
        notifier = TeamsNotifier(webhook_url="https://teams.webhook/test")
        captured = {}

        def capture(req, timeout):
            captured["data"] = req.data
            return _mock_response(200)

        with patch("urllib.request.urlopen", side_effect=capture):
            notifier.send_alert(_make_payload(severity="INFO"))

        body = json.loads(captured["data"])
        card = body["attachments"][0]["content"]
        assert card["body"][0]["color"] == "default"

    def test_content_type_header_is_json(self):
        notifier = TeamsNotifier(webhook_url="https://teams.webhook/test")
        captured = {}

        def capture(req, timeout):
            captured["req"] = req
            return _mock_response(200)

        with patch("urllib.request.urlopen", side_effect=capture):
            notifier.send_alert(_make_payload())

        assert captured["req"].get_header("Content-type") == "application/json"
