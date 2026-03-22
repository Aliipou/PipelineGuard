"""Shared fixtures for unit tests."""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest

# Ensure src is importable
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from domain.models.tenant import Tenant, TenantStatus
from domain.models.user import TenantRole, User
from domain.services.cost_calculator import CostCalculator
from domain.services.tenant_lifecycle import TenantLifecycleService
from infrastructure.adapters import (
    InMemoryAnomalyRepository,
    InMemoryAuditRepository,
    InMemoryCostRepository,
    InMemoryInvoiceRepository,
    InMemoryRefreshTokenStore,
    InMemoryTenantRepository,
    InMemoryUsageRepository,
    InMemoryUserRepository,
    LoggingEventPublisher,
    NoOpSchemaManager,
)

TENANT_ID = UUID("00000000-0000-0000-0000-000000000001")
USER_ID = UUID("00000000-0000-0000-0000-000000000002")
NOW = datetime(2026, 2, 17, 12, 0, 0, tzinfo=UTC)


@pytest.fixture
def tenant_id() -> UUID:
    return TENANT_ID


@pytest.fixture
def user_id() -> UUID:
    return USER_ID


@pytest.fixture
def sample_tenant() -> Tenant:
    return Tenant(
        id=TENANT_ID,
        name="Test Corp",
        slug="test-corp",
        owner_email="admin@test.example",
        status=TenantStatus.ACTIVE,
        schema_name="tenant_test_corp",
        created_at=NOW,
        updated_at=NOW,
        settings={"tier": "FREE"},
        metadata={"data_residency_region": "eu-central-1"},
    )


@pytest.fixture
def sample_user() -> User:
    return User(
        id=USER_ID,
        tenant_id=TENANT_ID,
        email="alice@test.example",
        hashed_password="$argon2id$v=19$m=65536,t=3,p=4$hash",
        full_name="Alice Test",
        role=TenantRole.OWNER,
        is_active=True,
        created_at=NOW,
    )


@pytest.fixture
def tenant_repo() -> InMemoryTenantRepository:
    return InMemoryTenantRepository()


@pytest.fixture
def user_repo() -> InMemoryUserRepository:
    return InMemoryUserRepository()


@pytest.fixture
def audit_repo() -> InMemoryAuditRepository:
    return InMemoryAuditRepository()


@pytest.fixture
def usage_repo() -> InMemoryUsageRepository:
    return InMemoryUsageRepository()


@pytest.fixture
def cost_repo() -> InMemoryCostRepository:
    return InMemoryCostRepository()


@pytest.fixture
def invoice_repo() -> InMemoryInvoiceRepository:
    return InMemoryInvoiceRepository()


@pytest.fixture
def anomaly_repo() -> InMemoryAnomalyRepository:
    return InMemoryAnomalyRepository()


@pytest.fixture
def refresh_store() -> InMemoryRefreshTokenStore:
    return InMemoryRefreshTokenStore()


@pytest.fixture
def schema_manager() -> NoOpSchemaManager:
    return NoOpSchemaManager()


@pytest.fixture
def event_publisher() -> LoggingEventPublisher:
    return LoggingEventPublisher()


@pytest.fixture
def lifecycle_service() -> TenantLifecycleService:
    return TenantLifecycleService()


@pytest.fixture
def cost_calculator() -> CostCalculator:
    return CostCalculator()
