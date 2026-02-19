"""
Prometheus metrics definitions and FastAPI instrumentation.

Defines platform-wide custom metrics and provides a ``setup_metrics``
function that wires automatic request tracking into any FastAPI application.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    REGISTRY,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response as StarletteResponse

if TYPE_CHECKING:
    from fastapi import FastAPI, Request, Response

# ======================================================================
# Custom metrics (module-level singletons)
# ======================================================================

api_requests_total = Counter(
    "api_requests_total",
    "Total number of API requests",
    labelnames=["method", "endpoint", "status", "tenant_id"],
    registry=REGISTRY,
)

api_request_duration_seconds = Histogram(
    "api_request_duration_seconds",
    "Request latency in seconds",
    labelnames=["method", "endpoint", "tenant_id"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
    registry=REGISTRY,
)

tenant_count = Gauge(
    "tenant_count",
    "Number of tenants by status",
    labelnames=["status"],
    registry=REGISTRY,
)

tenant_resource_usage = Gauge(
    "tenant_resource_usage",
    "Current resource usage per tenant",
    labelnames=["tenant_id", "resource_type"],
    registry=REGISTRY,
)

cost_anomalies_total = Counter(
    "cost_anomalies_total",
    "Total detected cost anomalies",
    labelnames=["tenant_id", "resource_type"],
    registry=REGISTRY,
)

# PipelineGuard metrics
pipeline_silent_failures_total = Counter(
    "pipeline_silent_failures_total",
    "Total silent pipeline failures detected",
    labelnames=["tenant_id", "pipeline_id"],
    registry=REGISTRY,
)

pipeline_latency_drift_detected = Counter(
    "pipeline_latency_drift_detected",
    "Number of latency drift detections",
    labelnames=["tenant_id", "pipeline_id"],
    registry=REGISTRY,
)

pipeline_alerts_active = Gauge(
    "pipeline_alerts_active",
    "Currently active (unacknowledged) pipeline alerts",
    labelnames=["tenant_id", "severity"],
    registry=REGISTRY,
)


# ======================================================================
# Middleware for automatic request instrumentation
# ======================================================================


class PrometheusMiddleware(BaseHTTPMiddleware):
    """Middleware that records request count and latency per endpoint."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        method = request.method
        # Use the matched route path template when available, otherwise
        # fall back to the raw URL path.
        endpoint = self._get_path_template(request)
        tenant_id = self._extract_tenant_id(request)

        start = time.perf_counter()
        response: Response = await call_next(request)
        duration = time.perf_counter() - start

        status_code = str(response.status_code)

        api_requests_total.labels(
            method=method,
            endpoint=endpoint,
            status=status_code,
            tenant_id=tenant_id,
        ).inc()

        api_request_duration_seconds.labels(
            method=method,
            endpoint=endpoint,
            tenant_id=tenant_id,
        ).observe(duration)

        return response

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_path_template(request: Request) -> str:
        """
        Attempt to resolve the route template (e.g. ``/tenants/{id}``)
        so that cardinality stays bounded.
        """
        route = request.scope.get("route")
        if route and hasattr(route, "path"):
            return str(route.path)
        return str(request.url.path)

    @staticmethod
    def _extract_tenant_id(request: Request) -> str:
        """
        Best-effort extraction of the tenant ID from the request.

        Checks (in order): request state, path parameters, headers.
        """
        # From auth middleware (most common path).
        user = getattr(request.state, "user", None)
        if user and isinstance(user, dict) and "tenant_id" in user:
            return str(user["tenant_id"])

        # From path parameters.
        tenant_id = request.path_params.get("tenant_id")
        if tenant_id:
            return str(tenant_id)

        return str(request.headers.get("x-tenant-id", "unknown"))


# ======================================================================
# Setup helper
# ======================================================================


def setup_metrics(app: FastAPI) -> None:
    """
    Instrument a FastAPI application with Prometheus metrics.

    * Adds the ``PrometheusMiddleware`` for automatic request tracking.
    * Registers a ``/metrics`` endpoint that serves the Prometheus
      exposition format.
    """

    app.add_middleware(PrometheusMiddleware)

    @app.get("/metrics", include_in_schema=False)
    async def metrics_endpoint() -> StarletteResponse:
        body = generate_latest(REGISTRY)
        return StarletteResponse(
            content=body,
            media_type=CONTENT_TYPE_LATEST,
        )
