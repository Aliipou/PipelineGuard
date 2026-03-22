"""Tests for infrastructure.cost.anomaly_detector."""

from __future__ import annotations

import pytest

from infrastructure.cost.anomaly_detector import AnomalyDetector


@pytest.fixture
def detector() -> AnomalyDetector:
    return AnomalyDetector()


class TestDetectInsufficientData:
    def test_fewer_than_3_points_is_not_anomaly(self, detector: AnomalyDetector) -> None:
        result = detector.detect(100.0, [50.0, 60.0])
        assert result.is_anomaly is False
        assert result.deviation_factor == 0.0

    def test_empty_history(self, detector: AnomalyDetector) -> None:
        result = detector.detect(99.0, [])
        assert result.is_anomaly is False


class TestDetectAnomaly:
    def test_value_far_from_mean_is_anomaly(self, detector: AnomalyDetector) -> None:
        history = [10.0, 10.0, 10.0, 10.0, 10.0, 11.0, 9.0]
        result = detector.detect(50.0, history)
        assert result.is_anomaly is True
        assert result.deviation_factor > 2.5

    def test_value_within_range_is_not_anomaly(self, detector: AnomalyDetector) -> None:
        history = [10.0, 12.0, 11.0, 9.0, 10.5]
        result = detector.detect(10.8, history)
        assert result.is_anomaly is False


class TestFlatPattern:
    def test_all_same_current_differs(self, detector: AnomalyDetector) -> None:
        """Flat history (std=0) + different current -> anomaly."""
        history = [5.0, 5.0, 5.0, 5.0]
        result = detector.detect(6.0, history)
        assert result.is_anomaly is True
        assert result.deviation_factor == float("inf")

    def test_all_same_current_matches(self, detector: AnomalyDetector) -> None:
        """Flat history + matching current -> not anomaly."""
        history = [5.0, 5.0, 5.0, 5.0]
        result = detector.detect(5.0, history)
        assert result.is_anomaly is False
        assert result.deviation_factor == 0.0
