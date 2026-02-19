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


class DriftAnalyzer:
    """Stateless latency drift detection using percentile comparison."""

    def __init__(self, drift_threshold: float = 0.25) -> None:
        self._drift_threshold = drift_threshold

    def analyze(
        self,
        current_duration: float,
        historical_durations: list[float],
    ) -> DriftResult:
        """Compare current duration against percentile baselines.

        A pipeline is considered drifting when the current duration
        exceeds p50 + drift_threshold (default 25%).
        """
        if len(historical_durations) < 2:
            return DriftResult(
                p50_baseline=current_duration,
                p95_baseline=current_duration,
                current_duration=current_duration,
                drift_percentage=0.0,
                is_drifting=False,
            )

        sorted_vals = sorted(historical_durations)
        p50 = statistics.median(sorted_vals)
        idx_95 = int(len(sorted_vals) * 0.95)
        p95 = sorted_vals[min(idx_95, len(sorted_vals) - 1)]

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
        )
