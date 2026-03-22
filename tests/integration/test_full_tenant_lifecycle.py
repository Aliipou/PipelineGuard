"""Integration test for full tenant lifecycle: create -> provision -> use -> suspend -> delete."""

from __future__ import annotations

from uuid import uuid4

import pytest

from domain.exceptions import InvalidStateTransitionError
from domain.models.tenant import Tenant, TenantStatus
from domain.services.tenant_lifecycle import TenantLifecycleService
from infrastructure.adapters import InMemoryTenantRepository


def _do_transition(
    lifecycle: TenantLifecycleService, tenant: Tenant, new_status: TenantStatus
) -> None:
    """Validate and apply a state transition, raising on invalid."""
    if not lifecycle.validate_transition(tenant.status, new_status):
        raise InvalidStateTransitionError(
            current_state=tenant.status.value, new_state=new_status.value
        )
    tenant.status = new_status


@pytest.mark.integration
class TestFullTenantLifecycle:
    def _make_tenant(self, **overrides) -> Tenant:
        defaults = dict(
            id=uuid4(),
            name="Lifecycle Corp",
            slug="lifecycle-corp",
            owner_email="admin@lifecycle.example",
            status=TenantStatus.PENDING,
        )
        defaults.update(overrides)
        return Tenant(**defaults)

    def test_full_lifecycle(self):
        """Walk a tenant through: PENDING -> PROVISIONING -> ACTIVE -> SUSPENDED -> ACTIVE -> DEPROVISIONING -> DELETED."""
        tenant_repo = InMemoryTenantRepository()
        lifecycle = TenantLifecycleService()

        tenant = self._make_tenant()
        tenant_repo.save(tenant)
        assert tenant.status == TenantStatus.PENDING

        _do_transition(lifecycle, tenant, TenantStatus.PROVISIONING)
        tenant_repo.update(tenant)
        assert tenant.status == TenantStatus.PROVISIONING

        _do_transition(lifecycle, tenant, TenantStatus.ACTIVE)
        tenant_repo.update(tenant)
        assert tenant.status == TenantStatus.ACTIVE

        _do_transition(lifecycle, tenant, TenantStatus.SUSPENDED)
        tenant_repo.update(tenant)
        assert tenant.status == TenantStatus.SUSPENDED

        _do_transition(lifecycle, tenant, TenantStatus.ACTIVE)
        tenant_repo.update(tenant)
        assert tenant.status == TenantStatus.ACTIVE

        _do_transition(lifecycle, tenant, TenantStatus.DEPROVISIONING)
        tenant_repo.update(tenant)
        assert tenant.status == TenantStatus.DEPROVISIONING

        _do_transition(lifecycle, tenant, TenantStatus.DELETED)
        tenant_repo.update(tenant)
        assert tenant.status == TenantStatus.DELETED

        retrieved = tenant_repo.get_by_id(tenant.id)
        assert retrieved.status == TenantStatus.DELETED

    def test_invalid_transition_raises(self):
        lifecycle = TenantLifecycleService()
        tenant = self._make_tenant(status=TenantStatus.PENDING)
        with pytest.raises(InvalidStateTransitionError):
            _do_transition(lifecycle, tenant, TenantStatus.ACTIVE)  # PENDING -> ACTIVE is invalid

    def test_tenant_isolation_across_lifecycle(self):
        """Two tenants at different lifecycle stages don't interfere."""
        repo = InMemoryTenantRepository()
        lifecycle = TenantLifecycleService()

        t1 = self._make_tenant(slug="iso-one")
        t2 = self._make_tenant(slug="iso-two")
        repo.save(t1)
        repo.save(t2)

        _do_transition(lifecycle, t1, TenantStatus.PROVISIONING)
        _do_transition(lifecycle, t1, TenantStatus.ACTIVE)
        repo.update(t1)

        assert repo.get_by_id(t1.id).status == TenantStatus.ACTIVE
        assert repo.get_by_id(t2.id).status == TenantStatus.PENDING
