"""Tests for infrastructure.gdpr.retention_engine."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from infrastructure.gdpr.retention_engine import (
    DataCategory,
    ExpiredRecord,
    RetentionEngine,
    RetentionPolicy,
)

# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

NOW = datetime(2026, 2, 17, 12, 0, 0, tzinfo=UTC)


def _make_expired_record(
    *,
    soft_deleted: bool = False,
    soft_deleted_at: datetime | None = None,
    category: DataCategory = DataCategory.LOG,
) -> ExpiredRecord:
    return ExpiredRecord(
        tenant_id="t-1",
        table_name="logs",
        record_id="r-1",
        category=category,
        created_at=NOW - timedelta(days=400),
        expired_at=NOW - timedelta(days=35),
        soft_deleted=soft_deleted,
        soft_deleted_at=soft_deleted_at,
    )


def _make_db(**overrides) -> AsyncMock:
    db = AsyncMock()
    db.find_expired_records = overrides.get(
        "find_expired_records",
        AsyncMock(return_value=[]),
    )
    db.soft_delete = overrides.get("soft_delete", AsyncMock(return_value=0))
    db.hard_delete = overrides.get("hard_delete", AsyncMock(return_value=0))
    return db


# ------------------------------------------------------------------
# Tests: RetentionPolicy
# ------------------------------------------------------------------


class TestRetentionPolicy:
    def test_defaults(self) -> None:
        p = RetentionPolicy()
        assert p.transactional_data_days == 90
        assert p.log_data_days == 365
        assert p.user_activity_days == 180
        assert p.uploaded_files_days == 365
        assert p.grace_period_days == 30

    def test_days_for(self) -> None:
        p = RetentionPolicy(log_data_days=100)
        assert p.days_for(DataCategory.LOG) == 100
        assert p.days_for(DataCategory.TRANSACTIONAL) == 90


# ------------------------------------------------------------------
# Tests: RetentionEngine.scan_expired_records
# ------------------------------------------------------------------


@pytest.mark.asyncio
class TestScanExpiredRecords:
    async def test_queries_all_categories(self) -> None:
        mock_find = AsyncMock(return_value=[])
        db = _make_db(find_expired_records=mock_find)
        engine = RetentionEngine(db=db, now=lambda: NOW)

        await engine.scan_expired_records("t-1")

        # Should be called once per DataCategory (4 categories)
        assert mock_find.call_count == len(DataCategory)
        called_categories = {call.args[1] for call in mock_find.call_args_list}
        assert called_categories == set(DataCategory)


# ------------------------------------------------------------------
# Tests: soft_delete_records
# ------------------------------------------------------------------


@pytest.mark.asyncio
class TestSoftDeleteRecords:
    async def test_skips_already_soft_deleted(self) -> None:
        already_deleted = _make_expired_record(
            soft_deleted=True,
            soft_deleted_at=NOW - timedelta(days=5),
        )
        db = _make_db()
        engine = RetentionEngine(db=db, now=lambda: NOW)

        count = await engine.soft_delete_records([already_deleted])
        assert count == 0
        db.soft_delete.assert_not_called()

    async def test_processes_non_deleted(self) -> None:
        record = _make_expired_record(soft_deleted=False)
        mock_soft = AsyncMock(return_value=1)
        db = _make_db(soft_delete=mock_soft)
        engine = RetentionEngine(db=db, now=lambda: NOW)

        count = await engine.soft_delete_records([record])
        assert count == 1
        mock_soft.assert_awaited_once()


# ------------------------------------------------------------------
# Tests: hard_delete_records
# ------------------------------------------------------------------


@pytest.mark.asyncio
class TestHardDeleteRecords:
    async def test_only_deletes_past_grace_period(self) -> None:
        """Record soft-deleted 31 days ago (grace=30) -> eligible."""
        eligible = _make_expired_record(
            soft_deleted=True,
            soft_deleted_at=NOW - timedelta(days=31),
        )
        mock_hard = AsyncMock(return_value=1)
        db = _make_db(hard_delete=mock_hard)
        engine = RetentionEngine(db=db, now=lambda: NOW)

        count = await engine.hard_delete_records([eligible])
        assert count == 1
        mock_hard.assert_awaited_once()

    async def test_skips_within_grace_period(self) -> None:
        """Record soft-deleted 5 days ago (grace=30) -> not eligible."""
        recent = _make_expired_record(
            soft_deleted=True,
            soft_deleted_at=NOW - timedelta(days=5),
        )
        db = _make_db()
        engine = RetentionEngine(db=db, now=lambda: NOW)

        count = await engine.hard_delete_records([recent])
        assert count == 0
        db.hard_delete.assert_not_called()

    async def test_skips_non_soft_deleted(self) -> None:
        """Records that were never soft-deleted are not hard-deleted."""
        record = _make_expired_record(soft_deleted=False)
        db = _make_db()
        engine = RetentionEngine(db=db, now=lambda: NOW)

        count = await engine.hard_delete_records([record])
        assert count == 0
        db.hard_delete.assert_not_called()
