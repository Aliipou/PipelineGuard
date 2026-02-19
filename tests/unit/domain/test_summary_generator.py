"""Unit tests for the SummaryGenerator domain service."""

from __future__ import annotations

from datetime import date

from domain.services.summary_generator import SummaryGenerator, SummaryInput


class TestSummaryGenerator:
    def setup_method(self) -> None:
        self.generator = SummaryGenerator()

    def test_generates_report_header(self) -> None:
        data = SummaryInput(
            week_start=date(2026, 2, 10),
            week_end=date(2026, 2, 17),
            total_jobs=100,
            failed_jobs=5,
            silent_failures=0,
            pipelines_with_drift=0,
            avg_drift_percentage=0.0,
            top_risks=[],
        )
        result = self.generator.generate(data)
        assert "Weekly Pipeline Health Report (Feb 10 - Feb 17, 2026)" in result

    def test_reliability_percentage(self) -> None:
        data = SummaryInput(
            week_start=date(2026, 2, 10),
            week_end=date(2026, 2, 17),
            total_jobs=847,
            failed_jobs=49,
            silent_failures=0,
            pipelines_with_drift=0,
            avg_drift_percentage=0.0,
            top_risks=[],
        )
        result = self.generator.generate(data)
        assert "94.2%" in result
        assert "847 jobs" in result
        assert "49 failures" in result

    def test_silent_failures_warning(self) -> None:
        data = SummaryInput(
            week_start=date(2026, 2, 10),
            week_end=date(2026, 2, 17),
            total_jobs=100,
            failed_jobs=3,
            silent_failures=3,
            pipelines_with_drift=0,
            avg_drift_percentage=0.0,
            top_risks=[],
        )
        result = self.generator.generate(data)
        assert "3 job(s) failed without alerting anyone" in result

    def test_no_silent_failures_message(self) -> None:
        data = SummaryInput(
            week_start=date(2026, 2, 10),
            week_end=date(2026, 2, 17),
            total_jobs=100,
            failed_jobs=0,
            silent_failures=0,
            pipelines_with_drift=0,
            avg_drift_percentage=0.0,
            top_risks=[],
        )
        result = self.generator.generate(data)
        assert "None detected this week" in result

    def test_latency_drift_section(self) -> None:
        data = SummaryInput(
            week_start=date(2026, 2, 10),
            week_end=date(2026, 2, 17),
            total_jobs=100,
            failed_jobs=0,
            silent_failures=0,
            pipelines_with_drift=2,
            avg_drift_percentage=34.7,
            top_risks=[],
        )
        result = self.generator.generate(data)
        assert "2 pipeline(s) are trending slower" in result
        assert "+34.7%" in result

    def test_no_drift_message(self) -> None:
        data = SummaryInput(
            week_start=date(2026, 2, 10),
            week_end=date(2026, 2, 17),
            total_jobs=100,
            failed_jobs=0,
            silent_failures=0,
            pipelines_with_drift=0,
            avg_drift_percentage=0.0,
            top_risks=[],
        )
        result = self.generator.generate(data)
        assert "All pipelines within normal latency range" in result

    def test_top_risks_included(self) -> None:
        risks = [
            {"description": "'Facebook Ads -> BigQuery' silent failure on Feb 14"},
            {"description": "'TikTok Ads -> BigQuery' is +41.2% slower"},
        ]
        data = SummaryInput(
            week_start=date(2026, 2, 10),
            week_end=date(2026, 2, 17),
            total_jobs=100,
            failed_jobs=5,
            silent_failures=1,
            pipelines_with_drift=1,
            avg_drift_percentage=41.2,
            top_risks=risks,
        )
        result = self.generator.generate(data)
        assert "TOP RISKS:" in result
        assert "Facebook Ads -> BigQuery" in result
        assert "TikTok Ads -> BigQuery" in result

    def test_recommendation_always_present(self) -> None:
        data = SummaryInput(
            week_start=date(2026, 2, 10),
            week_end=date(2026, 2, 17),
            total_jobs=0,
            failed_jobs=0,
            silent_failures=0,
            pipelines_with_drift=0,
            avg_drift_percentage=0.0,
            top_risks=[],
        )
        result = self.generator.generate(data)
        assert "RECOMMENDATION:" in result

    def test_zero_jobs_shows_100_percent(self) -> None:
        data = SummaryInput(
            week_start=date(2026, 2, 10),
            week_end=date(2026, 2, 17),
            total_jobs=0,
            failed_jobs=0,
            silent_failures=0,
            pipelines_with_drift=0,
            avg_drift_percentage=0.0,
            top_risks=[],
        )
        result = self.generator.generate(data)
        assert "100.0% success rate" in result

    def test_top_risks_capped_at_five(self) -> None:
        risks = [{"description": f"Risk {i}"} for i in range(10)]
        data = SummaryInput(
            week_start=date(2026, 2, 10),
            week_end=date(2026, 2, 17),
            total_jobs=100,
            failed_jobs=10,
            silent_failures=5,
            pipelines_with_drift=5,
            avg_drift_percentage=30.0,
            top_risks=risks,
        )
        result = self.generator.generate(data)
        assert "5." in result
        assert "6." not in result
