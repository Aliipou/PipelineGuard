"""PipelineGuard API endpoints for pipeline monitoring."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Depends, Path, Query, status

from infrastructure.container import get_pipeline_service

from .schemas import (
    AlertAcknowledge,
    AlertListResponse,
    AlertResponse,
    ErrorResponse,
    JobExecutionCreate,
    JobExecutionListResponse,
    JobExecutionResponse,
    LatencyListResponse,
    LatencyResponse,
    PaginationMeta,
    PipelineCreate,
    PipelineListResponse,
    PipelineResponse,
    WeeklySummaryResponse,
)

if TYPE_CHECKING:
    from application.services.pipeline_service import PipelineService
    from domain.models.pipeline import (
        JobExecution,
        LatencyRecord,
        Pipeline,
        PipelineAlert,
    )

router = APIRouter(prefix="/tenants/{tenant_id}", tags=["PipelineGuard"])

TenantID = Annotated[uuid.UUID, Path(description="Unique tenant identifier.")]
PipelineID = Annotated[uuid.UUID, Path(description="Unique pipeline identifier.")]
AlertID = Annotated[uuid.UUID, Path(description="Unique alert identifier.")]


def _pipeline_to_response(pipeline: Pipeline) -> PipelineResponse:
    """Map a domain Pipeline to the API response schema."""
    return PipelineResponse(
        id=pipeline.id,
        tenant_id=pipeline.tenant_id,
        name=pipeline.name,
        source=pipeline.source,
        destination=pipeline.destination,
        schedule_cron=pipeline.schedule_cron,
        status=pipeline.status.value,
        expected_duration_seconds=pipeline.expected_duration_seconds,
        timeout_seconds=pipeline.timeout_seconds,
        failure_threshold=pipeline.failure_threshold,
        metadata=pipeline.metadata_json or None,
        created_at=pipeline.created_at,
        updated_at=pipeline.updated_at,
    )


def _execution_to_response(execution: JobExecution) -> JobExecutionResponse:
    return JobExecutionResponse(
        id=execution.id,
        pipeline_id=execution.pipeline_id,
        tenant_id=execution.tenant_id,
        status=execution.status.value,
        started_at=execution.started_at,
        finished_at=execution.finished_at,
        duration_seconds=execution.duration_seconds,
        records_processed=execution.records_processed,
        error_message=execution.error_message,
        is_silent_failure=execution.is_silent_failure,
        metadata=execution.metadata_json or None,
    )


def _latency_to_response(record: LatencyRecord) -> LatencyResponse:
    return LatencyResponse(
        id=record.id,
        pipeline_id=record.pipeline_id,
        tenant_id=record.tenant_id,
        measured_at=record.measured_at,
        duration_seconds=record.duration_seconds,
        p50_baseline_seconds=record.p50_baseline_seconds,
        p95_baseline_seconds=record.p95_baseline_seconds,
        drift_percentage=record.drift_percentage,
    )


def _alert_to_response(alert: PipelineAlert) -> AlertResponse:
    return AlertResponse(
        id=alert.id,
        tenant_id=alert.tenant_id,
        pipeline_id=alert.pipeline_id,
        severity=alert.severity.value,
        alert_type=alert.alert_type.value,
        title=alert.title,
        description=alert.description,
        acknowledged=alert.acknowledged,
        acknowledged_by=alert.acknowledged_by,
        acknowledged_at=alert.acknowledged_at,
        created_at=alert.created_at,
    )


# ---------------------------------------------------------------------------
# Pipeline CRUD
# ---------------------------------------------------------------------------


@router.post(
    "/pipelines",
    response_model=PipelineResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new pipeline",
    responses={
        201: {"description": "Pipeline registered."},
        422: {"description": "Validation error.", "model": ErrorResponse},
    },
)
async def register_pipeline(
    tenant_id: TenantID,
    body: PipelineCreate,
    service: PipelineService = Depends(get_pipeline_service),
) -> PipelineResponse:
    pipeline = service.register_pipeline(
        tenant_id=tenant_id,
        name=body.name,
        source=body.source,
        destination=body.destination,
        schedule_cron=body.schedule_cron,
        expected_duration_seconds=body.expected_duration_seconds,
        timeout_seconds=body.timeout_seconds,
        failure_threshold=body.failure_threshold,
        metadata_json=body.metadata,
    )
    return _pipeline_to_response(pipeline)


@router.get(
    "/pipelines",
    response_model=PipelineListResponse,
    summary="List pipelines for a tenant",
    responses={200: {"description": "Paginated pipeline list."}},
)
async def list_pipelines(
    tenant_id: TenantID,
    page: int = Query(1, ge=1, description="Page number."),
    page_size: int = Query(20, ge=1, le=100, description="Items per page."),
    service: PipelineService = Depends(get_pipeline_service),
) -> PipelineListResponse:
    result = service.list_pipelines(tenant_id=tenant_id, page=page, size=page_size)
    return PipelineListResponse(
        items=[_pipeline_to_response(p) for p in result.items],
        pagination=PaginationMeta(
            page=result.page,
            page_size=result.size,
            total_items=result.total,
            total_pages=result.pages,
        ),
    )


@router.get(
    "/pipelines/{pipeline_id}",
    response_model=PipelineResponse,
    summary="Get pipeline details",
    responses={
        200: {"description": "Pipeline details."},
        404: {"description": "Pipeline not found.", "model": ErrorResponse},
    },
)
async def get_pipeline(
    tenant_id: TenantID,
    pipeline_id: PipelineID,
    service: PipelineService = Depends(get_pipeline_service),
) -> PipelineResponse:
    pipeline = service.get_pipeline(pipeline_id)
    return _pipeline_to_response(pipeline)


# ---------------------------------------------------------------------------
# Job Executions
# ---------------------------------------------------------------------------


@router.post(
    "/pipelines/{pipeline_id}/executions",
    response_model=JobExecutionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Report a job execution",
    responses={
        201: {"description": "Execution recorded (silent failure auto-detected)."},
        404: {"description": "Pipeline not found.", "model": ErrorResponse},
        422: {"description": "Validation error.", "model": ErrorResponse},
    },
)
async def report_execution(
    tenant_id: TenantID,
    pipeline_id: PipelineID,
    body: JobExecutionCreate,
    service: PipelineService = Depends(get_pipeline_service),
) -> JobExecutionResponse:
    execution = service.record_execution(
        pipeline_id=pipeline_id,
        tenant_id=tenant_id,
        status=body.status,
        started_at=body.started_at,
        finished_at=body.finished_at,
        duration_seconds=body.duration_seconds,
        records_processed=body.records_processed,
        error_message=body.error_message,
        metadata_json=body.metadata,
    )
    return _execution_to_response(execution)


@router.get(
    "/pipelines/{pipeline_id}/executions",
    response_model=JobExecutionListResponse,
    summary="List job executions for a pipeline",
    responses={200: {"description": "Paginated execution list."}},
)
async def list_executions(
    tenant_id: TenantID,
    pipeline_id: PipelineID,
    page: int = Query(1, ge=1, description="Page number."),
    page_size: int = Query(20, ge=1, le=100, description="Items per page."),
    service: PipelineService = Depends(get_pipeline_service),
) -> JobExecutionListResponse:
    result = service.list_executions(pipeline_id=pipeline_id, page=page, size=page_size)
    return JobExecutionListResponse(
        items=[_execution_to_response(ex) for ex in result.items],
        pagination=PaginationMeta(
            page=result.page,
            page_size=result.size,
            total_items=result.total,
            total_pages=result.pages,
        ),
    )


# ---------------------------------------------------------------------------
# Latency
# ---------------------------------------------------------------------------


@router.get(
    "/pipelines/{pipeline_id}/latency",
    response_model=LatencyListResponse,
    summary="Get latency history for a pipeline",
    responses={200: {"description": "Paginated latency history."}},
)
async def get_latency_history(
    tenant_id: TenantID,
    pipeline_id: PipelineID,
    page: int = Query(1, ge=1, description="Page number."),
    page_size: int = Query(50, ge=1, le=100, description="Items per page."),
    service: PipelineService = Depends(get_pipeline_service),
) -> LatencyListResponse:
    result = service.get_latency_history(pipeline_id=pipeline_id, page=page, size=page_size)
    return LatencyListResponse(
        items=[_latency_to_response(r) for r in result.items],
        pagination=PaginationMeta(
            page=result.page,
            page_size=result.size,
            total_items=result.total,
            total_pages=result.pages,
        ),
    )


# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------


@router.get(
    "/alerts",
    response_model=AlertListResponse,
    summary="List alerts for a tenant",
    responses={200: {"description": "Paginated alert list."}},
)
async def list_alerts(
    tenant_id: TenantID,
    page: int = Query(1, ge=1, description="Page number."),
    page_size: int = Query(20, ge=1, le=100, description="Items per page."),
    service: PipelineService = Depends(get_pipeline_service),
) -> AlertListResponse:
    result = service.list_alerts(tenant_id=tenant_id, page=page, size=page_size)
    return AlertListResponse(
        items=[_alert_to_response(a) for a in result.items],
        pagination=PaginationMeta(
            page=result.page,
            page_size=result.size,
            total_items=result.total,
            total_pages=result.pages,
        ),
    )


@router.post(
    "/alerts/{alert_id}/acknowledge",
    response_model=AlertResponse,
    summary="Acknowledge an alert",
    responses={
        200: {"description": "Alert acknowledged."},
        404: {"description": "Alert not found.", "model": ErrorResponse},
    },
)
async def acknowledge_alert(
    tenant_id: TenantID,
    alert_id: AlertID,
    body: AlertAcknowledge,
    service: PipelineService = Depends(get_pipeline_service),
) -> AlertResponse:
    alert = service.acknowledge_alert(
        alert_id=alert_id,
        acknowledged_by=body.acknowledged_by,
    )
    return _alert_to_response(alert)


# ---------------------------------------------------------------------------
# Weekly Summary
# ---------------------------------------------------------------------------


@router.get(
    "/summary",
    response_model=WeeklySummaryResponse | None,
    summary="Get latest weekly summary",
    responses={200: {"description": "Latest weekly summary or null."}},
)
async def get_latest_summary(
    tenant_id: TenantID,
    service: PipelineService = Depends(get_pipeline_service),
) -> WeeklySummaryResponse | None:
    summary = service.get_latest_summary(tenant_id)
    if summary is None:
        return None
    return WeeklySummaryResponse(
        id=summary.id,
        tenant_id=summary.tenant_id,
        week_start=summary.week_start,
        week_end=summary.week_end,
        total_jobs=summary.total_jobs,
        failed_jobs=summary.failed_jobs,
        silent_failures=summary.silent_failures,
        pipelines_with_drift=summary.pipelines_with_drift,
        avg_drift_percentage=summary.avg_drift_percentage,
        top_risks=summary.top_risks or None,
        plain_english_summary=summary.plain_english_summary,
        generated_at=summary.generated_at,
    )


@router.post(
    "/summary/generate",
    response_model=WeeklySummaryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Generate weekly summary now",
    responses={201: {"description": "Summary generated."}},
)
async def generate_summary(
    tenant_id: TenantID,
    service: PipelineService = Depends(get_pipeline_service),
) -> WeeklySummaryResponse:
    summary = service.generate_summary(tenant_id)
    return WeeklySummaryResponse(
        id=summary.id,
        tenant_id=summary.tenant_id,
        week_start=summary.week_start,
        week_end=summary.week_end,
        total_jobs=summary.total_jobs,
        failed_jobs=summary.failed_jobs,
        silent_failures=summary.silent_failures,
        pipelines_with_drift=summary.pipelines_with_drift,
        avg_drift_percentage=summary.avg_drift_percentage,
        top_risks=summary.top_risks or None,
        plain_english_summary=summary.plain_english_summary,
        generated_at=summary.generated_at,
    )
