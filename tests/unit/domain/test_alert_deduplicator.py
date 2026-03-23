"""Tests for AlertDeduplicator."""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest

from domain.services.alert_deduplicator import AlertDeduplicator


class TestAlertDeduplicator:
    def test_first_alert_always_allowed(self):
        dedup = AlertDeduplicator(cooldown_seconds=300)
        assert dedup.should_alert("pipe-1", "SILENT_FAILURE") is True

    def test_second_alert_within_cooldown_suppressed(self):
        dedup = AlertDeduplicator(cooldown_seconds=300)
        dedup.should_alert("pipe-1", "SILENT_FAILURE")
        assert dedup.should_alert("pipe-1", "SILENT_FAILURE") is False

    def test_alert_allowed_after_cooldown_expires(self):
        dedup = AlertDeduplicator(cooldown_seconds=60)
        with patch("time.monotonic", return_value=1000.0):
            dedup.should_alert("pipe-1", "LATENCY_DRIFT")

        with patch("time.monotonic", return_value=1061.0):
            assert dedup.should_alert("pipe-1", "LATENCY_DRIFT") is True

    def test_alert_suppressed_just_before_cooldown_expires(self):
        dedup = AlertDeduplicator(cooldown_seconds=60)
        with patch("time.monotonic", return_value=1000.0):
            dedup.should_alert("pipe-1", "LATENCY_DRIFT")

        with patch("time.monotonic", return_value=1059.9):
            assert dedup.should_alert("pipe-1", "LATENCY_DRIFT") is False

    def test_different_pipeline_ids_are_independent(self):
        dedup = AlertDeduplicator(cooldown_seconds=300)
        dedup.should_alert("pipe-1", "SILENT_FAILURE")
        # pipe-2 has never alerted — should be allowed
        assert dedup.should_alert("pipe-2", "SILENT_FAILURE") is True

    def test_different_alert_types_are_independent(self):
        dedup = AlertDeduplicator(cooldown_seconds=300)
        dedup.should_alert("pipe-1", "SILENT_FAILURE")
        # Different type for same pipeline — should be allowed
        assert dedup.should_alert("pipe-1", "LATENCY_DRIFT") is True

    def test_reset_clears_cooldown(self):
        dedup = AlertDeduplicator(cooldown_seconds=300)
        dedup.should_alert("pipe-1", "SILENT_FAILURE")
        dedup.reset("pipe-1", "SILENT_FAILURE")
        assert dedup.should_alert("pipe-1", "SILENT_FAILURE") is True

    def test_reset_nonexistent_key_is_noop(self):
        dedup = AlertDeduplicator(cooldown_seconds=300)
        # Should not raise
        dedup.reset("nonexistent", "SILENT_FAILURE")

    def test_reset_does_not_affect_other_keys(self):
        dedup = AlertDeduplicator(cooldown_seconds=300)
        dedup.should_alert("pipe-1", "SILENT_FAILURE")
        dedup.should_alert("pipe-2", "SILENT_FAILURE")
        dedup.reset("pipe-1", "SILENT_FAILURE")
        # pipe-2 should still be suppressed
        assert dedup.should_alert("pipe-2", "SILENT_FAILURE") is False

    def test_zero_cooldown_always_alerts(self):
        dedup = AlertDeduplicator(cooldown_seconds=0)
        dedup.should_alert("pipe-1", "SILENT_FAILURE")
        assert dedup.should_alert("pipe-1", "SILENT_FAILURE") is True

    def test_default_cooldown_is_300_seconds(self):
        dedup = AlertDeduplicator()
        assert dedup.cooldown_seconds == 300.0

    def test_updates_timestamp_on_allow(self):
        dedup = AlertDeduplicator(cooldown_seconds=60)
        with patch("time.monotonic", return_value=500.0):
            dedup.should_alert("pipe-1", "SILENT_FAILURE")

        # Allow after first cooldown, record new timestamp
        with patch("time.monotonic", return_value=561.0):
            dedup.should_alert("pipe-1", "SILENT_FAILURE")

        # Now within a new cooldown window
        with patch("time.monotonic", return_value=600.0):
            assert dedup.should_alert("pipe-1", "SILENT_FAILURE") is False
