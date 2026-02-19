# ADR-006: PipelineGuard — Pipeline Monitoring with Percentile-Based Drift Detection

## Status

Accepted

## Context

Async data pipelines pulling from marketing platforms (Google Ads, Facebook, TikTok, etc.) into analytics tools have two specific failure modes that go unnoticed:

1. **Silent failures**: Jobs report `SUCCEEDED` but pull zero records, or complete with non-empty error messages. No alerts fire because the job technically "succeeded."
2. **Latency drift**: Pipeline durations gradually increase 20-40% over weeks. Nobody notices until downstream analytics are delayed and clients complain.

Both problems share a pattern: the system reports success while the data is degraded. Traditional monitoring (uptime, error rates) misses them entirely.

## Decision

### Silent Failure Detection

Flag a job as `SILENT_FAILURE` when:
- Reported status is `SUCCEEDED` AND `records_processed == 0`
- Reported status is `SUCCEEDED` AND `error_message` is non-empty

This is checked synchronously at ingestion time (POST execution endpoint) for immediate feedback. A `CRITICAL` alert is generated automatically.

**Rationale**: Zero records from a marketing data pull is never correct — these pipelines always have impression/click data. Checking at ingestion time provides the fastest possible feedback loop.

### Latency Drift Detection

Use **percentile-based comparison** against a rolling baseline:
- Baseline: **p50 (median)** of the last 100 duration measurements
- Threshold: Current duration exceeds `p50 * 1.25` (25% above baseline)
- Alert severity: `WARNING`

**Rationale**: Median is robust against outliers (unlike mean). The 25% threshold balances sensitivity vs. false positives — a pipeline running 25% slower than its typical behavior warrants investigation but isn't necessarily critical. The threshold is configurable via `DriftAnalyzer(drift_threshold=0.25)`.

**Why not z-score (like cost anomaly detection)?**: Pipeline latencies are often not normally distributed — they have long right tails (network issues, API rate limits). Percentile-based comparison handles skewed distributions better than z-score. We use z-score for costs (ADR-005) where daily aggregates are closer to normal.

### Consecutive Failure Alerting

Track the last N executions per pipeline. If N consecutive executions are `FAILED` or `SILENT_FAILURE` (where N = `failure_threshold`, default 3), generate a `CRITICAL` alert.

### Weekly Summary Generation

A Celery beat task runs Monday 08:00 UTC, aggregating per-tenant:
- Total jobs, failures, silent failures
- Pipelines with active drift
- Top 5 risks ranked by severity

Output is a plain-English report stored in `weekly_summaries` table and retrievable via API.

### Database Design

All 5 PipelineGuard tables live in the `public` schema (not per-tenant schemas) because:
- Pipeline monitoring is a platform-level concern
- Queries need to scan across pipelines efficiently
- Tenant isolation is enforced via `tenant_id` column + application-level filtering
- Alembic migration `003` handles creation

## Consequences

### Positive
- Silent failures caught within 15 minutes (scan task) or immediately (API ingestion)
- Latency drift detected before clients notice downstream delays
- CTO gets a weekly summary without manual dashboard checking
- Drops into existing pipeline infrastructure via a single webhook per job completion
- Follows all existing codebase patterns (Clean Architecture, Protocol-based DI, RFC 9457 errors)

### Negative
- Percentile baseline requires ~10+ historical measurements to be meaningful
- 25% threshold may need tuning per pipeline (fast pipelines may fluctuate more)
- Weekly summary aggregation scans all recent executions — may need indexing at scale

### Future Improvements
- Per-pipeline configurable drift thresholds
- Slack/email webhook integration for alerts
- Anomaly detection on records_processed counts (not just zero/non-zero)
- Trend prediction: "at current drift rate, this pipeline will breach SLA in N days"
