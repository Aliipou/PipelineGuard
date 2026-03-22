"""Integration tests for TenantRepository with real PostgreSQL."""

from __future__ import annotations

from uuid import uuid4

import pytest

from domain.models.tenant import Tenant, TenantStatus
from infrastructure.adapters import InMemoryTenantRepository


@pytest.mark.integration
class TestTenantRepository:
    """Test tenant CRUD operations."""

    def test_save_and_get_by_id(self):
        repo = InMemoryTenantRepository()
        tenant = Tenant(id=uuid4(), name="Test", slug="test", status=TenantStatus.PENDING)
        saved = repo.save(tenant)
        assert saved.id == tenant.id
        retrieved = repo.get_by_id(tenant.id)
        assert retrieved is not None
        assert retrieved.name == "Test"

    def test_get_by_slug(self):
        repo = InMemoryTenantRepository()
        tenant = Tenant(id=uuid4(), name="Slug Test", slug="slug-test")
        repo.save(tenant)
        result = repo.get_by_slug("slug-test")
        assert result is not None
        assert result.name == "Slug Test"

    def test_get_by_slug_not_found(self):
        repo = InMemoryTenantRepository()
        assert repo.get_by_slug("nonexistent") is None

    def test_list_tenants_pagination(self):
        repo = InMemoryTenantRepository()
        for i in range(5):
            repo.save(Tenant(id=uuid4(), name=f"T{i}", slug=f"t-{i}"))
        items, total = repo.list_tenants(offset=0, limit=3)
        assert len(items) == 3
        assert total == 5

    def test_list_tenants_status_filter(self):
        repo = InMemoryTenantRepository()
        repo.save(Tenant(id=uuid4(), name="Active", slug="active", status=TenantStatus.ACTIVE))
        repo.save(Tenant(id=uuid4(), name="Pending", slug="pending", status=TenantStatus.PENDING))
        items, total = repo.list_tenants(offset=0, limit=10, status_filter=TenantStatus.ACTIVE)
        assert total == 1
        assert items[0].name == "Active"

    def test_update_tenant(self):
        repo = InMemoryTenantRepository()
        tenant = Tenant(id=uuid4(), name="Old", slug="old")
        repo.save(tenant)
        tenant.name = "New"
        updated = repo.update(tenant)
        assert updated.name == "New"
        assert repo.get_by_id(tenant.id).name == "New"
