# Metrics Reference

PipelineGuard tracks the following metrics for every pipeline and job.

## Execution Metrics

| Metric | Type | Description |
|---|---|---|
| `duration_seconds` | Histogram | Total execution time |
| `input_records` | Gauge | Records received |
| `output_records` | Gauge | Records produced |
| `error_count` | Counter | Errors during execution |
| `retry_count` | Counter | Retry attempts |

## Latency Percentiles

| Metric | Description |
|---|---|
| `latency_p50` | Median execution time (50th percentile) |
| `latency_p95` | 95th percentile execution time |
| `latency_p99` | 99th percentile execution time |

Percentiles are computed over a sliding 1-hour window.

## Derived Metrics

| Metric | Formula |
|---|---|
| `error_rate` | `error_count / (input_records + 1)` |
| `throughput` | `output_records / duration_seconds` |
| `record_loss_rate` | `(input_records - output_records) / input_records` |

## Query via API

```bash
GET /api/pipelines/etl-daily/metrics?window=1h

{
  "pipeline": "etl-daily",
  "window": "1h",
  "metrics": {
    "duration_p50": 45.2,
    "duration_p99": 187.3,
    "error_rate": 0.002,
    "throughput": 1250.5
  }
}
```
