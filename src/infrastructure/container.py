"""Dependency injection container for the EU Multi-Tenant Cloud Platform.

Wires together all infrastructure adapters and application services,
exposing factory functions suitable for FastAPI's ``Depends()`` system.
"""

from __future__ import annotations

import logging

from application.services.auth_service import AuthService
from application.services.billing_service import BillingService
from application.services.gdpr_service import GDPRService
from application.services.pipeline_service import PipelineService
from application.services.tenant_service import TenantService
from domain.services.cost_calculator import CostCalculator
from domain.services.drift_analyzer import DriftAnalyzer
from domain.services.summary_generator import SummaryGenerator
from domain.services.tenant_lifecycle import TenantLifecycleService
from infrastructure.adapters import (
    InMemoryAnomalyRepository,
    InMemoryAuditRepository,
    InMemoryCacheManager,
    InMemoryCostRepository,
    InMemoryExportJobRepository,
    InMemoryInvoiceRepository,
    InMemoryJobExecutionRepository,
    InMemoryLatencyRecordRepository,
    InMemoryPipelineAlertRepository,
    InMemoryPipelineRepository,
    InMemoryRefreshTokenStore,
    InMemoryRetentionRepository,
    InMemoryTenantDataRepository,
    InMemoryTenantRepository,
    InMemoryUsageRepository,
    InMemoryUserRepository,
    InMemoryWeeklySummaryRepository,
    LoggingEventPublisher,
    NoOpSchemaManager,
)
from infrastructure.settings import AppSettings, get_settings

logger = logging.getLogger(__name__)


class ServiceContainer:
    """Central DI container that owns all service instances."""

    def __init__(self, settings: AppSettings | None = None) -> None:
        self._settings = settings or get_settings()

        # Infrastructure adapters
        self.tenant_repo = InMemoryTenantRepository()
        self.user_repo = InMemoryUserRepository()
        self.audit_repo = InMemoryAuditRepository()
        self.usage_repo = InMemoryUsageRepository()
        self.cost_repo = InMemoryCostRepository()
        self.invoice_repo = InMemoryInvoiceRepository()
        self.anomaly_repo = InMemoryAnomalyRepository()
        self.refresh_store = InMemoryRefreshTokenStore()
        self.cache_manager = InMemoryCacheManager()
        self.export_job_repo = InMemoryExportJobRepository()
        self.retention_repo = InMemoryRetentionRepository()
        self.data_repo = InMemoryTenantDataRepository()
        self.schema_manager = NoOpSchemaManager()
        self.event_publisher = LoggingEventPublisher()

        # PipelineGuard adapters
        self.pipeline_repo = InMemoryPipelineRepository()
        self.execution_repo = InMemoryJobExecutionRepository()
        self.latency_repo = InMemoryLatencyRecordRepository()
        self.alert_repo = InMemoryPipelineAlertRepository()
        self.summary_repo = InMemoryWeeklySummaryRepository()

        # Domain services
        self.lifecycle_service = TenantLifecycleService()
        self.cost_calculator = CostCalculator()
        self.drift_analyzer = DriftAnalyzer()
        self.summary_generator = SummaryGenerator()

        # Application services
        self.tenant_service = TenantService(
            tenant_repo=self.tenant_repo,
            audit_repo=self.audit_repo,
            schema_manager=self.schema_manager,
            lifecycle_service=self.lifecycle_service,
            event_publisher=self.event_publisher,
        )

        self.auth_service = AuthService(
            user_repo=self.user_repo,
            tenant_repo=self.tenant_repo,
            refresh_store=self.refresh_store,
            audit_repo=self.audit_repo,
            private_key=self._settings.jwt_private_key,
            public_key=self._settings.jwt_public_key,
            issuer=self._settings.jwt_issuer,
        )

        self.billing_service = BillingService(
            usage_repo=self.usage_repo,
            cost_repo=self.cost_repo,
            invoice_repo=self.invoice_repo,
            anomaly_repo=self.anomaly_repo,
            audit_repo=self.audit_repo,
            cost_calculator=self.cost_calculator,
        )

        self.gdpr_service = GDPRService(
            tenant_repo=self.tenant_repo,
            export_job_repo=self.export_job_repo,
            retention_repo=self.retention_repo,
            schema_manager=self.schema_manager,
            cache_manager=self.cache_manager,
            data_repo=self.data_repo,
            audit_repo=self.audit_repo,
            lifecycle_service=self.lifecycle_service,
        )

        self.pipeline_service = PipelineService(
            pipeline_repo=self.pipeline_repo,
            execution_repo=self.execution_repo,
            latency_repo=self.latency_repo,
            alert_repo=self.alert_repo,
            summary_repo=self.summary_repo,
            drift_analyzer=self.drift_analyzer,
            summary_generator=self.summary_generator,
        )

        logger.info("ServiceContainer initialized")


# Module-level singleton
_container: ServiceContainer | None = None


def get_container() -> ServiceContainer:
    """Return the global container singleton."""
    global _container
    if _container is None:
        _container = ServiceContainer()
    return _container


def reset_container() -> None:
    """Reset the global container (for testing)."""
    global _container
    _container = None


# ---------------------------------------------------------------------------
# FastAPI dependency factories
# ---------------------------------------------------------------------------


def get_tenant_service() -> TenantService:
    return get_container().tenant_service


def get_auth_service() -> AuthService:
    return get_container().auth_service


def get_billing_service() -> BillingService:
    return get_container().billing_service


def get_gdpr_service() -> GDPRService:
    return get_container().gdpr_service


def get_pipeline_service() -> PipelineService:
    return get_container().pipeline_service
