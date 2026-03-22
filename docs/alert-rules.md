# Alert Rules Guide

## Creating Rules via API

```bash
POST /api/alerts/rules
Content-Type: application/json

{
  "name": "high-error-rate",
  "pipeline": "etl-daily",
  "job": "*",
  "metric": "error_rate",
  "condition": "greater_than",
  "threshold": 0.05,
  "window_minutes": 10,
  "severity": "critical",
  "channels": ["slack"]
}
```

## Supported Conditions

| Condition | Meaning |
|---|---|
| `greater_than` | metric > threshold |
| `less_than` | metric < threshold |
| `equals` | metric == threshold |
| `missing` | no executions in window |

## Wildcard Matching

Use `*` to match all pipelines or jobs:

```json
{
  "pipeline": "*",
  "job": "load",
  "metric": "latency_p99",
  "threshold": 300
}
```

## Silencing Alerts

```bash
POST /api/alerts/silences
{
  "rule": "high-error-rate",
  "duration_minutes": 60,
  "reason": "Planned maintenance window"
}
```
