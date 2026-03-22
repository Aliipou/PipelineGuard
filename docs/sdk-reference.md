# SDK Reference

## @guard Decorator

```python
from pipelineguard import guard

@guard(
    pipeline="my-pipeline",  # pipeline name (required)
    job="transform",         # job name (required)
    record_count_fn=len,     # function to count output records
    tags={"env": "prod"},    # arbitrary tags
)
def my_job(data):
    ...
```

## PipelineGuardClient

```python
from pipelineguard import PipelineGuardClient

client = PipelineGuardClient(
    api_url="http://pipelineguard:8000",
    api_key="your-key",
    timeout=5.0,
)

# Manual execution reporting
with client.execution("my-pipeline", "load") as exec:
    exec.set_input_count(1000)
    load_records(data)
    exec.set_output_count(998)
```

## AlertRule

```python
from pipelineguard import AlertRule

rule = AlertRule(
    pipeline="*",              # glob: all pipelines
    job="*",
    metric="latency_p99",      # latency_p50/p95/p99, error_rate, record_count
    threshold=30.0,            # 30 seconds
    window_minutes=5,
    severity="critical",       # info/warning/critical
    channel="slack",
)
```
