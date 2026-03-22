"""Unit tests for GDPRService — export, erasure, retention."""

from __future__ import annotations

from uuid import uuid4

import pytest

from application.services.gdpr_service import (
    GDPRService,
    RetentionPolicy,
)
from domain.models.tenant import Tenant, TenantStatus
from domain.services.tenant_lifecycle import TenantLifecycleService
from infrastructure.adapters import (
    InMemoryAuditRepository,
    InMemoryCacheManager,
    InMemoryExportJobRepository,
    InMemoryRetentionRepository,
    InMemoryTenantDataRepository,
    InMemoryTenantRepository,
    NoOpSchemaManager,
)


@pytest.fixture
def tenant_repo():
    return InMemoryTenantRepository()


@pytest.fixture
def active_tenant(tenant_repo):
    tenant = Tenant(
        id=uuid4(),
        name="GDPRCorp",
        slug="gdpr-corp",
        status=TenantStatus.ACTIVE,
        schema_name="tenant_gdpr_corp",
    )
    tenant_repo.save(tenant)
    return tenant


@pytest.fixture
def svc(tenant_repo):
    return GDPRService(
        tenant_repo=tenant_repo,
        export_job_repo=InMemoryExportJobRepository(),
        retention_repo=InMemoryRetentionRepository(),
        schema_manager=NoOpSchemaManager(),
        cache_manager=InMemoryCacheManager(),
        data_repo=InMemoryTenantDataRepository(),
        audit_repo=InMemoryAuditRepository(),
        lifecycle_service=TenantLifecycleService(),
    )


class TestExportTenantData:
    def test_export_returns_job_id(self, svc, active_tenant):
        import sys
        from unittest.mock import MagicMock

        mock_mod = MagicMock()
        sys.modules["application.tasks.gdpr_tasks"] = mock_mod
        try:
            job_id = svc.export_tenant_data(active_tenant.id)
            assert isinstance(job_id, str)
            assert len(job_id) == 32  # uuid4().hex
        finally:
            sys.modules.pop("application.tasks.gdpr_tasks", None)

    def test_export_creates_queued_job(self, svc, active_tenant):
        import sys
        from unittest.mock import MagicMock

        mock_mod = MagicMock()
        sys.modules["application.tasks.gdpr_tasks"] = mock_mod
        try:
            job_id = svc.export_tenant_data(active_tenant.id)
            status = svc.get_export_status(job_id)
            assert status is not None
        finally:
            sys.modules.pop("application.tasks.gdpr_tasks", None)

    def test_export_nonexistent_tenant_raises(self, svc):
        from domain.exceptions import TenantNotFoundError

        with pytest.raises(TenantNotFoundError):
            svc.export_tenant_data(uuid4())


class TestGetExportStatus:
    def test_nonexistent_job_raises(self, svc):
        with pytest.raises(ValueError, match="Export job not found"):
            svc.get_export_status("nonexistent-job-id")


class TestExecuteErasure:
    def test_erasure_deletes_tenant(self, svc, active_tenant):
        result = svc.execute_erasure(active_tenant.id)
        assert result.tenant_id == active_tenant.id
        assert result.caches_purged is True
        assert "tenant_gdpr_corp" in result.schemas_dropped

    def test_erasure_transitions_to_deleted(self, svc, active_tenant, tenant_repo):
        svc.execute_erasure(active_tenant.id)
        tenant = tenant_repo.get_by_id(active_tenant.id)
        assert tenant.status == TenantStatus.DELETED

    def test_erasure_creates_audit_entry(self, svc, active_tenant):
        svc.execute_erasure(active_tenant.id)
        entries = svc._audit_repo._entries
        actions = [e.action.value for e in entries]
        assert "DATA_ERASED" in actions

    def test_erasure_nonexistent_tenant_raises(self, svc):
        from domain.exceptions import TenantNotFoundError

        with pytest.raises(TenantNotFoundError):
            svc.execute_erasure(uuid4())


class TestRetentionPolicy:
    def test_get_default_policy(self, svc, active_tenant):
        policy = svc.get_retention_policy(active_tenant.id)
        assert policy.tenant_id == active_tenant.id
        assert policy.retention_days == 365

    def test_update_policy(self, svc, active_tenant):
        policy = RetentionPolicy(
            tenant_id=active_tenant.id,
            retention_days=180,
            grace_period_days=14,
        )
        saved = svc.update_retention_policy(active_tenant.id, policy)
        assert saved.retention_days == 180
        assert saved.grace_period_days == 14

    def test_get_updated_policy(self, svc, active_tenant):
        policy = RetentionPolicy(tenant_id=active_tenant.id, retention_days=90)
        svc.update_retention_policy(active_tenant.id, policy)
        fetched = svc.get_retention_policy(active_tenant.id)
        assert fetched.retention_days == 90


class TestRetentionCleanup:
    def test_cleanup_returns_result(self, svc, active_tenant):
        result = svc.run_retention_cleanup(active_tenant.id)
        assert result.tenant_id == active_tenant.id
        assert result.records_soft_deleted == 0
        assert result.records_hard_deleted == 0

    def test_cleanup_nonexistent_tenant_raises(self, svc):
        from domain.exceptions import TenantNotFoundError

        with pytest.raises(TenantNotFoundError):
            svc.run_retention_cleanup(uuid4())
