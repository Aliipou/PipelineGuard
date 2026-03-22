"""Tests for src/domain/models/audit.py"""

import re
from datetime import UTC, datetime
from uuid import UUID, uuid4

from domain.models.audit import AuditAction, AuditEntry, _compute_entry_hash


class TestAuditAction:
    def test_enum_has_ten_values(self):
        assert len(list(AuditAction)) == 10

    def test_enum_values(self):
        expected = {
            "TENANT_CREATED",
            "TENANT_UPDATED",
            "TENANT_DELETED",
            "USER_LOGIN",
            "DATA_ACCESSED",
            "DATA_EXPORTED",
            "DATA_ERASED",
            "SCHEMA_MIGRATED",
            "COST_ANOMALY_DETECTED",
            "RETENTION_EXECUTED",
        }
        assert {a.value for a in AuditAction} == expected


class TestComputeEntryHash:
    def test_returns_sha256_hex(self):
        tenant_id = uuid4()
        ts = datetime.now(UTC)
        h = _compute_entry_hash("prev", AuditAction.TENANT_CREATED, tenant_id, ts)
        assert isinstance(h, str)
        assert len(h) == 64
        assert re.fullmatch(r"[0-9a-f]{64}", h) is not None

    def test_same_inputs_same_hash(self):
        tenant_id = uuid4()
        ts = datetime(2025, 1, 1, tzinfo=UTC)
        h1 = _compute_entry_hash("", AuditAction.USER_LOGIN, tenant_id, ts)
        h2 = _compute_entry_hash("", AuditAction.USER_LOGIN, tenant_id, ts)
        assert h1 == h2

    def test_different_inputs_different_hash(self):
        tenant_id = uuid4()
        ts = datetime(2025, 1, 1, tzinfo=UTC)
        h1 = _compute_entry_hash("", AuditAction.USER_LOGIN, tenant_id, ts)
        h2 = _compute_entry_hash("x", AuditAction.USER_LOGIN, tenant_id, ts)
        assert h1 != h2


class TestAuditEntry:
    def test_auto_computes_entry_hash(self):
        entry = AuditEntry()
        assert entry.entry_hash != ""
        assert len(entry.entry_hash) == 64

    def test_hash_matches_manual_computation(self):
        entry = AuditEntry()
        expected = _compute_entry_hash(
            entry.previous_hash, entry.action, entry.tenant_id, entry.timestamp
        )
        assert entry.entry_hash == expected

    def test_hash_chain(self):
        first = AuditEntry(previous_hash="")
        second = AuditEntry(previous_hash=first.entry_hash)
        assert second.previous_hash == first.entry_hash
        assert first.entry_hash != second.entry_hash

    def test_defaults(self):
        entry = AuditEntry()
        assert isinstance(entry.id, UUID)
        assert isinstance(entry.tenant_id, UUID)
        assert entry.action == AuditAction.TENANT_CREATED
        assert entry.details == {}
        assert entry.previous_hash == ""
