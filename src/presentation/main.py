"""FastAPI application factory for the EU Multi-Tenant Cloud Platform."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from domain.exceptions.tenant_exceptions import DomainError
from infrastructure.container import get_container
from infrastructure.observability.logging_config import setup_logging

from .api.v1 import auth, billing, gdpr, pipelines, tenants
from .middleware.request_logging import RequestLoggingMiddleware
from .middleware.tenant_context import TenantContextMiddleware

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

# ---------------------------------------------------------------------------
# Lifespan (startup / shutdown)
# ---------------------------------------------------------------------------


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    setup_logging()
    container = get_container()
    app.state.container = container
    yield


# ---------------------------------------------------------------------------
# Exception handlers (RFC 9457 Problem Details)
# ---------------------------------------------------------------------------


def _problem_json(
    status_code: int,
    title: str,
    detail: str,
    *,
    error_type: str = "about:blank",
    instance: str | None = None,
    errors: list[dict[str, Any]] | None = None,
) -> JSONResponse:
    body: dict[str, Any] = {
        "type": error_type,
        "title": title,
        "status": status_code,
        "detail": detail,
    }
    if instance:
        body["instance"] = instance
    if errors:
        body["errors"] = errors
    return JSONResponse(
        status_code=status_code,
        content=body,
        media_type="application/problem+json",
    )


async def _domain_exception_handler(request: Request, exc: DomainError) -> JSONResponse:
    return _problem_json(
        status_code=exc.status_code,
        title=exc.title,
        detail=exc.detail,
        error_type=exc.error_type,
        instance=str(request.url.path),
    )


async def _validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    errors = []
    for err in exc.errors():
        errors.append(
            {
                "field": " -> ".join(str(loc) for loc in err.get("loc", [])),
                "message": err.get("msg", ""),
                "type": err.get("type", ""),
            }
        )
    return _problem_json(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        title="Validation Error",
        detail="The request body or parameters failed validation.",
        error_type="https://api.eu-platform.example/problems/validation-error",
        instance=str(request.url.path),
        errors=errors,
    )


async def _generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    return _problem_json(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        title="Internal Server Error",
        detail="An unexpected error occurred. Please try again later.",
        instance=str(request.url.path),
    )


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------

API_V1_PREFIX = "/api/v1"


def create_app() -> FastAPI:
    app = FastAPI(
        title="EU Multi-Tenant Cloud Platform",
        version="1.0.0",
        description=(
            "API for the EU-Grade Multi-Tenant Cloud Platform. Provides "
            "tenant management, authentication, billing, and GDPR compliance "
            "endpoints with full data-residency isolation."
        ),
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=_lifespan,
    )

    # -- CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )

    # -- Custom middleware
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(TenantContextMiddleware)

    # -- API routers
    app.include_router(tenants.router, prefix=API_V1_PREFIX)
    app.include_router(auth.router, prefix=API_V1_PREFIX)
    app.include_router(billing.router, prefix=API_V1_PREFIX)
    app.include_router(gdpr.router, prefix=API_V1_PREFIX)
    app.include_router(pipelines.router, prefix=API_V1_PREFIX)

    # -- Exception handlers
    app.add_exception_handler(DomainError, _domain_exception_handler)
    app.add_exception_handler(RequestValidationError, _validation_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, _generic_exception_handler)

    return app


app = create_app()


@app.get("/health", tags=["Operations"], summary="Health check", response_model=dict)
async def health_check() -> dict[str, Any]:
    return {
        "status": "healthy",
        "version": "1.0.0",
        "timestamp": datetime.now(UTC).isoformat(),
    }
