"""Background Celery tasks for PipelineGuard operations."""

from __future__ import annotations

import logging
from typing import Any

from application.tasks.celery_app import app

logger = logging.getLogger(__name__)


@app.task(  # type: ignore[untyped-decorator]
    name="application.tasks.pipeline_tasks.scan_silent_failures",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def scan_silent_failures(self: Any) -> dict[str, Any]:
    """Scan recent job executions for silent failure patterns.

    Runs every 15 minutes. Checks all recent SUCCEEDED jobs across
    all tenants for zero records or non-empty error messages.
    """
    from domain.models.pipeline import JobStatus
    from domain.models.tenant import TenantStatus
    from infrastructure.container import get_container

    logger.info("Scanning for silent failures")

    try:
        container = get_container()
        tenants, _ = container.tenant_repo.list_tenants(0, 10000, TenantStatus.ACTIVE)
        total_detected = 0
        tenants_scanned = 0

        for tenant in tenants:
            try:
                recent = container.execution_repo.list_recent_by_tenant(
                    tenant_id=tenant.id,
                    limit=100,
                )
                for ex in recent:
                    if (
                        ex.status == JobStatus.SUCCEEDED
                        and (ex.records_processed == 0 or ex.error_message)
                    ):
                        # Re-record through service to trigger alert
                        container.pipeline_service.record_execution(
                            pipeline_id=ex.pipeline_id,
                            tenant_id=ex.tenant_id,
                            status="SUCCEEDED",
                            started_at=ex.started_at,
                            finished_at=ex.finished_at,
                            duration_seconds=ex.duration_seconds,
                            records_processed=ex.records_processed,
                            error_message=ex.error_message,
                        )
                        total_detected += 1
                tenants_scanned += 1
            except Exception:
                logger.exception("Silent failure scan failed for tenant %s", tenant.id)

        logger.info(
            "Silent failure scan: %d tenants, %d detected",
            tenants_scanned,
            total_detected,
        )
        return {"tenants_scanned": tenants_scanned, "silent_failures_detected": total_detected}

    except Exception as exc:
        logger.exception("Silent failure scan failed")
        raise self.retry(exc=exc) from exc


@app.task(  # type: ignore[untyped-decorator]
    name="application.tasks.pipeline_tasks.check_latency_drift",
    bind=True,
    max_retries=2,
    default_retry_delay=120,
)
def check_latency_drift(self: Any) -> dict[str, Any]:
    """Check all pipelines for latency drift against baseline.

    Runs hourly. Compares recent latency measurements against
    percentile baselines and generates WARNING alerts for drifting pipelines.
    """
    from domain.models.tenant import TenantStatus
    from infrastructure.container import get_container

    logger.info("Checking latency drift for all pipelines")

    try:
        container = get_container()
        tenants, _ = container.tenant_repo.list_tenants(0, 10000, TenantStatus.ACTIVE)
        pipelines_checked = 0
        drift_detected = 0

        for tenant in tenants:
            try:
                pipelines, _ = container.pipeline_repo.list_by_tenant(
                    tenant_id=tenant.id,
                    offset=0,
                    limit=10000,
                )
                for pipeline in pipelines:
                    try:
                        is_drifting = container.pipeline_service.check_latency_drift(
                            pipeline.id
                        )
                        pipelines_checked += 1
                        if is_drifting:
                            drift_detected += 1
                    except Exception:
                        logger.exception(
                            "Drift check failed for pipeline %s", pipeline.id
                        )
            except Exception:
                logger.exception("Drift check failed for tenant %s", tenant.id)

        logger.info(
            "Latency drift check: %d pipelines, %d drifting",
            pipelines_checked,
            drift_detected,
        )
        return {"pipelines_checked": pipelines_checked, "drift_detected": drift_detected}

    except Exception as exc:
        logger.exception("Latency drift check failed")
        raise self.retry(exc=exc) from exc


@app.task(  # type: ignore[untyped-decorator]
    name="application.tasks.pipeline_tasks.generate_weekly_summaries",
    bind=True,
    max_retries=3,
    default_retry_delay=300,
)
def generate_weekly_summaries(self: Any) -> dict[str, Any]:
    """Generate weekly pipeline health summaries for all tenants.

    Runs every Monday at 08:00 UTC. Produces a plain-English CTO
    summary for each active tenant.
    """
    from domain.models.tenant import TenantStatus
    from infrastructure.container import get_container

    logger.info("Generating weekly pipeline summaries")

    try:
        container = get_container()
        tenants, _ = container.tenant_repo.list_tenants(0, 10000, TenantStatus.ACTIVE)
        summaries_generated = 0
        errors: list[str] = []

        for tenant in tenants:
            try:
                container.pipeline_service.generate_summary(tenant.id)
                summaries_generated += 1
            except Exception as exc:
                errors.append(f"{tenant.id}: {exc}")

        logger.info(
            "Weekly summaries: %d generated, %d errors",
            summaries_generated,
            len(errors),
        )
        return {"summaries_generated": summaries_generated, "errors": errors}

    except Exception as exc:
        logger.exception("Weekly summary generation failed")
        raise self.retry(exc=exc) from exc
