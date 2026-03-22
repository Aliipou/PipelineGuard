"""Unit tests for the DriftAnalyzer domain service."""

from __future__ import annotations

import pytest

from domain.services.drift_analyzer import DriftAnalyzer, DriftResult


class TestDriftAnalyzer:
    def setup_method(self) -> None:
        self.analyzer = DriftAnalyzer(drift_threshold=0.25)

    def test_no_historical_data(self) -> None:
        result = self.analyzer.analyze(100.0, [])
        assert result.is_drifting is False
        assert result.drift_percentage == 0.0
        assert result.p50_baseline == 100.0

    def test_single_historical_value(self) -> None:
        result = self.analyzer.analyze(100.0, [90.0])
        assert result.is_drifting is False

    def test_no_drift_within_threshold(self) -> None:
        historical = [100.0, 102.0, 98.0, 101.0, 99.0]
        result = self.analyzer.analyze(110.0, historical)
        # p50 = 100.0, 110 is +10% which is < 25% threshold
        assert result.is_drifting is False
        assert result.drift_percentage == 10.0

    def test_drift_detected_above_threshold(self) -> None:
        historical = [100.0, 102.0, 98.0, 101.0, 99.0]
        result = self.analyzer.analyze(130.0, historical)
        # p50 = 100.0, 130 is +30% which is > 25% threshold
        assert result.is_drifting is True
        assert result.drift_percentage == 30.0

    def test_drift_at_exact_threshold(self) -> None:
        historical = [100.0, 100.0, 100.0, 100.0]
        # 125 is exactly 25%, threshold is >25% so not drifting
        result = self.analyzer.analyze(125.0, historical)
        assert result.is_drifting is False

    def test_drift_just_above_threshold(self) -> None:
        historical = [100.0, 100.0, 100.0, 100.0]
        result = self.analyzer.analyze(126.0, historical)
        assert result.is_drifting is True

    def test_faster_than_baseline_no_drift(self) -> None:
        historical = [100.0, 102.0, 98.0, 101.0, 99.0]
        result = self.analyzer.analyze(80.0, historical)
        assert result.is_drifting is False
        assert result.drift_percentage < 0

    def test_p50_and_p95_baselines(self) -> None:
        historical = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0]
        result = self.analyzer.analyze(55.0, historical)
        assert result.p50_baseline == 55.0  # median
        assert result.p95_baseline == 100.0  # 95th percentile

    def test_zero_baseline_no_crash(self) -> None:
        historical = [0.0, 0.0, 0.0]
        result = self.analyzer.analyze(5.0, historical)
        assert result.is_drifting is False
        assert result.drift_percentage == 0.0

    def test_custom_threshold(self) -> None:
        analyzer = DriftAnalyzer(drift_threshold=0.10)  # 10%
        historical = [100.0, 100.0, 100.0]
        result = analyzer.analyze(115.0, historical)
        assert result.is_drifting is True

    def test_result_is_frozen(self) -> None:
        result = self.analyzer.analyze(100.0, [90.0, 110.0])
        assert isinstance(result, DriftResult)
        with pytest.raises(AttributeError):
            result.is_drifting = True  # type: ignore[misc]

    # ── Z-score & rolling window tests ──────────────────────────────────────

    def test_z_score_anomaly_detected(self) -> None:
        # Baseline: cluster around 100 with natural variance, then a huge outlier → |z| >> 2.5
        historical = [
            95.0,
            100.0,
            105.0,
            98.0,
            102.0,
            99.0,
            101.0,
            97.0,
            103.0,
            100.0,
            98.0,
            102.0,
            100.0,
            99.0,
            101.0,
            100.0,
            98.0,
            103.0,
            97.0,
            102.0,
        ]
        result = self.analyzer.analyze(500.0, historical)
        assert result.is_anomaly is True
        assert result.z_score > 2.5

    def test_z_score_normal_no_anomaly(self) -> None:
        # Value within 1σ of mean — well under 2.5σ threshold
        historical = [100.0, 102.0, 98.0, 101.0, 99.0, 100.0, 103.0, 97.0]
        result = self.analyzer.analyze(101.0, historical)
        assert result.is_anomaly is False
        assert abs(result.z_score) < 2.5

    def test_rolling_window_limits_to_n_samples(self) -> None:
        # Provide 200 ancient "100s" then 10 fresh "200s" with window_size=10
        # The analyzer should only see the last 10 samples (all 200s)
        analyzer_small = DriftAnalyzer(drift_threshold=0.25, window_size=10)
        old_data = [100.0] * 200
        recent_data = [200.0] * 10
        historical = old_data + recent_data
        result = analyzer_small.analyze(205.0, historical)
        # p50 of the window is ~200, not 100 — no drift at 205 vs 200 baseline
        assert result.p50_baseline == pytest.approx(200.0, abs=1.0)
        assert result.is_drifting is False

    def test_z_score_zero_when_uniform_baseline(self) -> None:
        # All identical values → stdev == 0 → z_score must be 0, no crash
        historical = [60.0] * 10
        result = self.analyzer.analyze(60.0, historical)
        assert result.z_score == 0.0
        assert result.is_anomaly is False

    def test_anomaly_negative_z_score(self) -> None:
        # A job that ran impossibly fast is also an anomaly (negative z)
        historical = [
            95.0,
            100.0,
            105.0,
            98.0,
            102.0,
            99.0,
            101.0,
            97.0,
            103.0,
            100.0,
            98.0,
            102.0,
            100.0,
            99.0,
            101.0,
            100.0,
            98.0,
            103.0,
            97.0,
            102.0,
        ]
        result = self.analyzer.analyze(1.0, historical)
        assert result.is_anomaly is True
        assert result.z_score < -2.5
