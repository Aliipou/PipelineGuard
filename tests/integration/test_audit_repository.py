"""Integration tests for audit repository — hash chain integrity."""

from __future__ import annotations

from uuid import uuid4

import pytest

from domain.models.audit import AuditAction, AuditEntry, _compute_entry_hash
from infrastructure.adapters import InMemoryAuditRepository


@pytest.mark.integration
class TestAuditRepository:
    def test_save_and_get_latest(self):
        repo = InMemoryAuditRepository()
        tid = uuid4()
        entry = AuditEntry(tenant_id=tid, action=AuditAction.TENANT_CREATED, actor_id=uuid4())
        repo.save(entry)
        latest = repo.get_latest_entry(tid)
        assert latest is not None
        assert latest.action == AuditAction.TENANT_CREATED

    def test_hash_chain_integrity(self):
        repo = InMemoryAuditRepository()
        tid = uuid4()
        actor = uuid4()

        e1 = AuditEntry(
            tenant_id=tid,
            action=AuditAction.TENANT_CREATED,
            actor_id=actor,
            previous_hash="",
        )
        repo.save(e1)

        e2 = AuditEntry(
            tenant_id=tid,
            action=AuditAction.TENANT_UPDATED,
            actor_id=actor,
            previous_hash=e1.entry_hash,
        )
        repo.save(e2)

        expected_hash = _compute_entry_hash(e1.entry_hash, e2.action, e2.tenant_id, e2.timestamp)
        assert e2.entry_hash == expected_hash
        assert e2.previous_hash == e1.entry_hash

    def test_get_latest_returns_most_recent(self):
        repo = InMemoryAuditRepository()
        tid = uuid4()
        for action in [
            AuditAction.TENANT_CREATED,
            AuditAction.USER_LOGIN,
            AuditAction.DATA_ACCESSED,
        ]:
            repo.save(AuditEntry(tenant_id=tid, action=action, actor_id=uuid4()))
        latest = repo.get_latest_entry(tid)
        assert latest.action == AuditAction.DATA_ACCESSED

    def test_get_latest_different_tenants(self):
        repo = InMemoryAuditRepository()
        t1, t2 = uuid4(), uuid4()
        repo.save(AuditEntry(tenant_id=t1, action=AuditAction.TENANT_CREATED, actor_id=uuid4()))
        repo.save(AuditEntry(tenant_id=t2, action=AuditAction.USER_LOGIN, actor_id=uuid4()))
        assert repo.get_latest_entry(t1).action == AuditAction.TENANT_CREATED
        assert repo.get_latest_entry(t2).action == AuditAction.USER_LOGIN

    def test_get_latest_nonexistent_tenant(self):
        repo = InMemoryAuditRepository()
        assert repo.get_latest_entry(uuid4()) is None
