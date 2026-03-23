"""Tests for the generic webhook notifier."""

from __future__ import annotations

import hashlib
import hmac
import json
from unittest.mock import MagicMock, patch

import pytest

from infrastructure.notifications.webhook import WebhookNotifier, WebhookPayload


def _make_payload(**kwargs) -> WebhookPayload:
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
    return WebhookPayload(**defaults)


def _mock_response(status: int = 200):
    mock = MagicMock()
    mock.status = status
    mock.__enter__ = lambda s: s
    mock.__exit__ = MagicMock(return_value=False)
    return mock


class TestWebhookNotifier:
    def test_success_returns_true(self):
        notifier = WebhookNotifier(url="https://example.com/hook")
        with patch("urllib.request.urlopen", return_value=_mock_response(200)):
            assert notifier.send_alert(_make_payload()) is True

    def test_4xx_returns_false(self):
        notifier = WebhookNotifier(url="https://example.com/hook")
        with patch("urllib.request.urlopen", return_value=_mock_response(422)):
            assert notifier.send_alert(_make_payload()) is False

    def test_5xx_returns_false(self):
        notifier = WebhookNotifier(url="https://example.com/hook")
        with patch("urllib.request.urlopen", return_value=_mock_response(503)):
            assert notifier.send_alert(_make_payload()) is False

    def test_network_error_returns_false(self):
        notifier = WebhookNotifier(url="https://example.com/hook")
        with patch("urllib.request.urlopen", side_effect=OSError("timeout")):
            assert notifier.send_alert(_make_payload()) is False

    def test_payload_contains_all_fields(self):
        notifier = WebhookNotifier(url="https://example.com/hook")
        captured = {}

        def capture(req, timeout):
            captured["data"] = req.data
            return _mock_response(200)

        with patch("urllib.request.urlopen", side_effect=capture):
            notifier.send_alert(_make_payload())

        body = json.loads(captured["data"])
        assert body["severity"] == "CRITICAL"
        assert body["alert_type"] == "SILENT_FAILURE"
        assert body["pipeline_name"] == "nightly-etl"
        assert body["tenant_id"] == "tenant-uuid-1234"
        assert body["alert_id"] == "alert-uuid-5678"

    def test_hmac_signature_added_when_secret_provided(self):
        secret = "super-secret"
        notifier = WebhookNotifier(url="https://example.com/hook", secret=secret)
        captured = {}

        def capture(req, timeout):
            captured["req"] = req
            captured["body"] = req.data
            return _mock_response(200)

        with patch("urllib.request.urlopen", side_effect=capture):
            notifier.send_alert(_make_payload())

        sig_header = captured["req"].get_header("X-pipelineguard-signature")
        assert sig_header is not None
        assert sig_header.startswith("sha256=")

        # Verify the signature is correct
        expected = hmac.new(secret.encode(), captured["body"], hashlib.sha256).hexdigest()
        assert sig_header == f"sha256={expected}"

    def test_no_signature_header_when_no_secret(self):
        notifier = WebhookNotifier(url="https://example.com/hook")
        captured = {}

        def capture(req, timeout):
            captured["req"] = req
            return _mock_response(200)

        with patch("urllib.request.urlopen", side_effect=capture):
            notifier.send_alert(_make_payload())

        assert captured["req"].get_header("X-pipelineguard-signature") is None

    def test_content_type_is_json(self):
        notifier = WebhookNotifier(url="https://example.com/hook")
        captured = {}

        def capture(req, timeout):
            captured["req"] = req
            return _mock_response(200)

        with patch("urllib.request.urlopen", side_effect=capture):
            notifier.send_alert(_make_payload())

        assert captured["req"].get_header("Content-type") == "application/json"
