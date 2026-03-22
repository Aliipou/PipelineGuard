"""Unit tests for TenantService — CRUD, lifecycle, and audit chain."""

from __future__ import annotations

from uuid import uuid4

import pytest

from application.services.tenant_service import TenantService
from domain.exceptions import (
    InvalidStateTransitionError,
    TenantAlreadyExistsError,
    TenantNotFoundError,
)
from domain.models.tenant import TenantStatus
from domain.services.tenant_lifecycle import TenantLifecycleService
from infrastructure.adapters import (
    InMemoryAuditRepository,
    InMemoryTenantRepository,
    LoggingEventPublisher,
    NoOpSchemaManager,
)


@pytest.fixture
def svc():
    return TenantService(
        tenant_repo=InMemoryTenantRepository(),
        audit_repo=InMemoryAuditRepository(),
        schema_manager=NoOpSchemaManager(),
        lifecycle_service=TenantLifecycleService(),
        event_publisher=LoggingEventPublisher(),
    )


class TestCreateTenant:
    def test_create_tenant_success(self, svc):
        tenant = svc.create_tenant(name="Acme", slug="acme", owner_email="admin@acme.example")
        assert tenant.name == "Acme"
        assert tenant.slug == "acme"
        assert tenant.status == TenantStatus.ACTIVE
        assert tenant.schema_name == "tenant_acme"

    def test_create_tenant_duplicate_slug_raises(self, svc):
        svc.create_tenant(name="A", slug="dup", owner_email="a@a.com")
        with pytest.raises(TenantAlreadyExistsError):
            svc.create_tenant(name="B", slug="dup", owner_email="b@b.com")

    def test_create_tenant_schema_name_replaces_hyphens(self, svc):
        tenant = svc.create_tenant(name="My Corp", slug="my-corp", owner_email="x@x.com")
        assert tenant.schema_name == "tenant_my_corp"


class TestGetTenant:
    def test_get_existing_tenant(self, svc):
        created = svc.create_tenant(name="T", slug="t", owner_email="t@t.com")
        fetched = svc.get_tenant(created.id)
        assert fetched.id == created.id

    def test_get_nonexistent_raises(self, svc):
        with pytest.raises(TenantNotFoundError):
            svc.get_tenant(uuid4())


class TestListTenants:
    def test_list_returns_paginated(self, svc):
        for i in range(5):
            svc.create_tenant(name=f"T{i}", slug=f"t-{i}", owner_email=f"t{i}@x.com")
        result = svc.list_tenants(page=1, size=3)
        assert len(result.items) == 3
        assert result.total == 5

    def test_list_with_status_filter(self, svc):
        t = svc.create_tenant(name="Active", slug="active", owner_email="a@a.com")
        svc.suspend_tenant(t.id)
        result = svc.list_tenants(status_filter=TenantStatus.SUSPENDED)
        assert result.total == 1
        assert result.items[0].status == TenantStatus.SUSPENDED


class TestUpdateTenant:
    def test_update_name(self, svc):
        t = svc.create_tenant(name="Old", slug="old", owner_email="o@o.com")
        updated = svc.update_tenant(t.id, {"name": "New"})
        assert updated.name == "New"

    def test_update_disallowed_field_ignored(self, svc):
        t = svc.create_tenant(name="X", slug="x", owner_email="x@x.com")
        updated = svc.update_tenant(t.id, {"slug": "new-slug"})
        assert updated.slug == "x"


class TestSuspendActivate:
    def test_suspend_active_tenant(self, svc):
        t = svc.create_tenant(name="S", slug="s", owner_email="s@s.com")
        suspended = svc.suspend_tenant(t.id)
        assert suspended.status == TenantStatus.SUSPENDED

    def test_activate_suspended_tenant(self, svc):
        t = svc.create_tenant(name="A", slug="a", owner_email="a@a.com")
        svc.suspend_tenant(t.id)
        activated = svc.activate_tenant(t.id)
        assert activated.status == TenantStatus.ACTIVE

    def test_suspend_nonexistent_raises(self, svc):
        with pytest.raises(TenantNotFoundError):
            svc.suspend_tenant(uuid4())

    def test_double_suspend_raises(self, svc):
        t = svc.create_tenant(name="D", slug="d", owner_email="d@d.com")
        svc.suspend_tenant(t.id)
        with pytest.raises(InvalidStateTransitionError):
            svc.suspend_tenant(t.id)


class TestAuditChain:
    def test_create_produces_audit_entry(self, svc):
        svc.create_tenant(name="Audit", slug="audit", owner_email="a@a.com")
        # Access internal audit repo to verify
        entries = svc._audit_repo._entries
        assert len(entries) >= 1
        assert entries[0].action.value == "TENANT_CREATED"

    def test_update_produces_audit_entry(self, svc):
        t = svc.create_tenant(name="AuUp", slug="auup", owner_email="a@a.com")
        svc.update_tenant(t.id, {"name": "Updated"})
        entries = svc._audit_repo._entries
        actions = [e.action.value for e in entries]
        assert "TENANT_UPDATED" in actions

    def test_audit_chain_has_linked_hashes(self, svc):
        t = svc.create_tenant(name="Chain", slug="chain", owner_email="c@c.com")
        svc.update_tenant(t.id, {"name": "Changed"})
        entries = svc._audit_repo._entries
        if len(entries) >= 2:
            assert entries[1].previous_hash == entries[0].entry_hash
