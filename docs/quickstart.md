# PipelineGuard Quickstart

Get pipeline observability in 5 minutes.

## Installation

```bash
pip install pipelineguard-sdk
```

## Instrument Your Pipeline

```python
from pipelineguard import guard

@guard(pipeline="etl-daily", job="transform")
def transform_records(records: list[dict]) -> list[dict]:
    return [clean(r) for r in records]
```

That's it. PipelineGuard automatically captures:
- Execution time
- Record counts (input/output)
- Error rate
- Latency percentiles (p50, p95, p99)

## View in Dashboard

```bash
export PIPELINEGUARD_API_URL=http://localhost:8000
export PIPELINEGUARD_API_KEY=your-key

pipelineguard dashboard
# Opens at http://localhost:3000
```

## Set an Alert

```python
# Alert if error rate > 5% over 10 minutes
from pipelineguard import AlertRule

rule = AlertRule(
    pipeline="etl-daily",
    metric="error_rate",
    threshold=0.05,
    window_minutes=10,
    channel="slack",
)
```
