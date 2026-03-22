from __future__ import annotations

import statistics
from dataclasses import dataclass


@dataclass(frozen=True)
class DriftResult:
    """Result of a latency drift analysis."""

    p50_baseline: float
    p95_baseline: float
    current_duration: float
    drift_percentage: float
    is_drifting: bool
    z_score: float
    is_anomaly: bool


class DriftAnalyzer:
    """Stateless latency drift detection using percentile comparison and z-score."""

    def __init__(
        self,
        drift_threshold: float = 0.25,
        window_size: int = 100,
        z_score_threshold: float = 2.5,
    ) -> None:
        self._drift_threshold = drift_threshold
        self._window_size = window_size
        self._z_score_threshold = z_score_threshold

    def analyze(
        self,
        current_duration: float,
        historical_durations: list[float],
    ) -> DriftResult:
        """Compare current duration against rolling percentile baselines and z-score.

        Uses the last ``window_size`` samples as the rolling baseline.
        A pipeline is considered drifting when the current duration
        exceeds p50 + drift_threshold (default 25%).
        A pipeline is flagged as anomaly when |z-score| > z_score_threshold (default 2.5 sigma).
        """
        window = historical_durations[-self._window_size :]

        if len(window) < 2:
            return DriftResult(
                p50_baseline=current_duration,
                p95_baseline=current_duration,
                current_duration=current_duration,
                drift_percentage=0.0,
                is_drifting=False,
                z_score=0.0,
                is_anomaly=False,
            )

        sorted_vals = sorted(window)
        p50 = statistics.median(sorted_vals)
        idx_95 = int(len(sorted_vals) * 0.95)
        p95 = sorted_vals[min(idx_95, len(sorted_vals) - 1)]

        # Z-score: how many standard deviations from the mean
        mean = statistics.mean(window)
        try:
            std = statistics.stdev(window)
        except statistics.StatisticsError:
            std = 0.0

        z_score = (current_duration - mean) / std if std > 0 else 0.0

        is_anomaly = abs(z_score) > self._z_score_threshold

        if p50 == 0:
            drift_pct = 0.0
            is_drifting = False
        else:
            drift_pct = ((current_duration - p50) / p50) * 100.0
            is_drifting = current_duration > p50 * (1 + self._drift_threshold)

        return DriftResult(
            p50_baseline=round(p50, 2),
            p95_baseline=round(p95, 2),
            current_duration=current_duration,
            drift_percentage=round(drift_pct, 1),
            is_drifting=is_drifting,
            z_score=round(z_score, 2),
            is_anomaly=is_anomaly,
        )
