from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any


@dataclass(frozen=True)
class SummaryInput:
    """Aggregated data needed to produce a weekly summary."""

    week_start: date
    week_end: date
    total_jobs: int
    failed_jobs: int
    silent_failures: int
    pipelines_with_drift: int
    avg_drift_percentage: float
    top_risks: list[dict[str, Any]]


class SummaryGenerator:
    """Generates plain-English weekly CTO summary from aggregated data."""

    def generate(self, data: SummaryInput) -> str:
        success_count = data.total_jobs - data.failed_jobs
        if data.total_jobs > 0:
            success_rate = (success_count / data.total_jobs) * 100.0
        else:
            success_rate = 100.0

        start = data.week_start.strftime("%b %d")
        end = data.week_end.strftime("%b %d, %Y")

        lines: list[str] = [
            f"Weekly Pipeline Health Report ({start} - {end})",
            "",
            f"RELIABILITY: {success_rate:.1f}% success rate "
            f"({data.total_jobs} jobs, {data.failed_jobs} failures)",
        ]

        if data.silent_failures > 0:
            lines.append(
                f"SILENT FAILURES: {data.silent_failures} job(s) failed without "
                "alerting anyone. This is your highest risk."
            )
        else:
            lines.append("SILENT FAILURES: None detected this week.")

        if data.pipelines_with_drift > 0:
            lines.append(
                f"LATENCY DRIFT: {data.pipelines_with_drift} pipeline(s) are "
                f"trending slower (avg +{data.avg_drift_percentage:.1f}% vs baseline)."
            )
        else:
            lines.append("LATENCY DRIFT: All pipelines within normal latency range.")

        if data.top_risks:
            lines.append("")
            lines.append("TOP RISKS:")
            for i, risk in enumerate(data.top_risks[:5], 1):
                lines.append(f"  {i}. {risk.get('description', 'Unknown risk')}")

        lines.append("")
        lines.append(
            "RECOMMENDATION: Investigate flagged pipelines before they "
            "impact downstream analytics."
        )

        return "\n".join(lines)
