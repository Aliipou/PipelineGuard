"""Celery application configuration for the EU-Grade Multi-Tenant Cloud Platform.

Sets up the broker (Redis), result backend, serialisation, task routing,
and retry policies.
"""

from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

app = Celery("eu_multitenant")

# ---------------------------------------------------------------------------
# Broker and result backend
# ---------------------------------------------------------------------------

app.conf.broker_url = "redis://localhost:6379/0"
app.conf.result_backend = "redis://localhost:6379/1"

# ---------------------------------------------------------------------------
# Serialisation
# ---------------------------------------------------------------------------

app.conf.accept_content = ["json"]
app.conf.task_serializer = "json"
app.conf.result_serializer = "json"

# ---------------------------------------------------------------------------
# Task routing
# ---------------------------------------------------------------------------

app.conf.task_routes = {
    "application.tasks.tenant_tasks.*": {"queue": "tenants"},
    "application.tasks.billing_tasks.*": {"queue": "billing"},
    "application.tasks.gdpr_tasks.*": {"queue": "gdpr"},
    "application.tasks.pipeline_tasks.*": {"queue": "pipelines"},
}

# ---------------------------------------------------------------------------
# Default retry policy
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
