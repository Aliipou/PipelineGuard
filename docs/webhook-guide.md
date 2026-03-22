# Webhook Guide

PipelineGuard can send real-time notifications to any HTTP endpoint when pipeline events occur.

## Configuring Webhooks

```bash
POST /api/webhooks
Content-Type: application/json

{
  "url": "https://my-service.com/webhooks/pipelineguard",
  "events": ["execution.failed", "alert.fired", "alert.resolved"],
  "secret": "my-webhook-secret",
  "pipelines": ["etl-daily", "ml-train"]  // omit for all pipelines
}
```

## Event Types

| Event | Trigger |
|---|---|
| `execution.started` | Job execution begins |
| `execution.completed` | Job execution succeeds |
| `execution.failed` | Job execution fails |
| `alert.fired` | Alert threshold crossed |
| `alert.resolved` | Alert returns to normal |
| `pipeline.degraded` | Pipeline health < 90% |

## Payload Format

```json
{
  "event": "execution.failed",
  "timestamp": "2024-01-15T10:23:45Z",
  "pipeline": "etl-daily",
  "job": "transform",
  "execution_id": "exec-001",
  "error": "Database connection timeout after 30s",
  "duration_seconds": 30.1,
  "retry_count": 2
}
```

## Verifying Signatures

```python
import hmac, hashlib

def verify_signature(payload: bytes, signature: str, secret: str) -> bool:
    expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", signature)
```
