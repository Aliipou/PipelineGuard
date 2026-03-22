"""Celery application configuration for the EU-Grade Multi-Tenant Cloud Platform.

Sets up the broker (Redis), result backend, serialisation, task routing,
retry policies, and dead-letter queue handling.
"""

from __future__ import annotations

import datetime
import json
import os
from typing import Any

from celery import Celery
from celery.exceptions import MaxRetriesExceededError
from celery.schedules import crontab
from celery.signals import task_failure

app = Celery("eu_multitenant")

# ---------------------------------------------------------------------------
# Broker and result backend (read from environment for Docker compatibility)
# ---------------------------------------------------------------------------

app.conf.broker_url = os.environ.get("APP_CELERY_BROKER_URL", "redis://localhost:6379/1")
app.conf.result_backend = os.environ.get("APP_CELERY_RESULT_BACKEND", "redis://localhost:6379/2")

# ---------------------------------------------------------------------------
# Serialisation
# ---------------------------------------------------------------------------

app.conf.accept_content = ["json"]
app.conf.task_serializer = "json"
app.conf.result_serializer = "json"

# ---------------------------------------------------------------------------
# Task routing (includes dead_letter queue)
# ---------------------------------------------------------------------------

app.conf.task_routes = {
    "application.tasks.tenant_tasks.*": {"queue": "tenants"},
    "application.tasks.billing_tasks.*": {"queue": "billing"},
    "application.tasks.gdpr_tasks.*": {"queue": "gdpr"},
    "application.tasks.pipeline_tasks.*": {"queue": "pipelines"},
    "application.tasks.celery_app.store_dead_letter": {"queue": "dead_letter"},
}

# ---------------------------------------------------------------------------
# Default retry policy (exponential backoff with jitter)
# ---------------------------------------------------------------------------

app.conf.task_annotations = {
    "*": {
        "max_retries": 3,
        "default_retry_delay": 60,
        "retry_backoff": True,
        "retry_backoff_max": 600,
        "retry_jitter": True,
    },
}

# ---------------------------------------------------------------------------
# Miscellaneous
# ---------------------------------------------------------------------------

app.conf.task_acks_late = True
app.conf.worker_prefetch_multiplier = 1
app.conf.task_track_started = True
app.conf.task_time_limit = 3600  # hard limit: 1 hour
app.conf.task_soft_time_limit = 3300  # soft limit: 55 minutes
app.conf.timezone = "UTC"

# ---------------------------------------------------------------------------
# Autodiscovery
# ---------------------------------------------------------------------------

app.autodiscover_tasks(
    [
        "application.tasks.tenant_tasks",
        "application.tasks.billing_tasks",
        "application.tasks.gdpr_tasks",
        "application.tasks.pipeline_tasks",
    ]
)

# ---------------------------------------------------------------------------
# Beat schedule (periodic tasks)
# ---------------------------------------------------------------------------

app.conf.beat_schedule = {
    "scan-silent-failures-every-15-min": {
        "task": "application.tasks.pipeline_tasks.scan_silent_failures",
        "schedule": 900.0,  # 15 minutes
    },
    "check-latency-drift-hourly": {
        "task": "application.tasks.pipeline_tasks.check_latency_drift",
        "schedule": 3600.0,  # 1 hour
    },
    "generate-weekly-summaries-monday": {
        "task": "application.tasks.pipeline_tasks.generate_weekly_summaries",
        "schedule": crontab(hour=8, minute=0, day_of_week=1),  # Monday 08:00 UTC
    },
}

# ---------------------------------------------------------------------------
# Dead Letter Queue — stores tasks that exhausted all retries
# ---------------------------------------------------------------------------


@app.task(name="application.tasks.celery_app.store_dead_letter", queue="dead_letter")  # type: ignore[untyped-decorator]
def store_dead_letter(
    task_name: str, task_id: str, error: str, args: list[Any], kwargs: dict[str, Any]
) -> None:
    """Persist a dead-lettered task to Redis for later inspection."""
    import redis as redis_lib

    redis_url = os.environ.get("APP_REDIS_URL", "redis://localhost:6379/0")
    r = redis_lib.from_url(redis_url)
    entry = json.dumps(
        {
            "task_name": task_name,
            "task_id": task_id,
            "error": error,
            "args": args,
            "kwargs": kwargs,
            "failed_at": datetime.datetime.utcnow().isoformat(),
        }
    )
    r.lpush("dead_letter_queue", entry)
    r.ltrim("dead_letter_queue", 0, 999)  # keep last 1000 entries


@task_failure.connect  # type: ignore[untyped-decorator]
def on_task_failure(
    sender: Any = None,
    task_id: Any = None,
    exception: Any = None,
    args: Any = None,
    kwargs: Any = None,
    **_kw: Any,
) -> None:
    """Route tasks to dead_letter queue when MaxRetriesExceededError is raised."""
    if isinstance(exception, MaxRetriesExceededError):
        store_dead_letter.apply_async(
            args=[
                getattr(sender, "name", "unknown"),
                str(task_id),
                str(exception),
                list(args or []),
                dict(kwargs or {}),
            ],
            queue="dead_letter",
        )
