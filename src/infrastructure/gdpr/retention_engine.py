"""
Data retention engine for GDPR-compliant lifecycle management.

Scans tenant data for records that have exceeded their retention period and
supports both soft-delete (mark as deleted, enter grace period) and
hard-delete (irreversible removal after the grace period expires).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Sequence

# ======================================================================
# Data categories
# ======================================================================


class DataCategory(str, Enum):
    TRANSACTIONAL = "transactional"
    LOG = "log"
    USER_ACTIVITY = "user_activity"
    UPLOADED_FILE = "uploaded_file"


# ======================================================================
# Retention policy
# ======================================================================


@dataclass(frozen=True)
class RetentionPolicy:
    """
    Per-category retention limits.

    Each value is the maximum number of days a record in that category may
    be retained before it must be deleted.
    """

    transactional_data_days: int = 90
    log_data_days: int = 365
    user_activity_days: int = 180
    uploaded_files_days: int = 365
    grace_period_days: int = 30

    def days_for(self, category: DataCategory) -> int:
        """Return the retention limit for the given *category*."""
        mapping = {
            DataCategory.TRANSACTIONAL: self.transactional_data_days,
            DataCategory.LOG: self.log_data_days,
            DataCategory.USER_ACTIVITY: self.user_activity_days,
            DataCategory.UPLOADED_FILE: self.uploaded_files_days,
        }
        return mapping[category]


DEFAULT_POLICY = RetentionPolicy()


# ======================================================================
# Expired-record reference
# ======================================================================


@dataclass(frozen=True)
class ExpiredRecord:
    """Pointer to a single record that has exceeded its retention limit."""

    tenant_id: str
    table_name: str
    record_id: str
    category: DataCategory
    created_at: datetime
    expired_at: datetime
    soft_deleted: bool = False
    soft_deleted_at: datetime | None = None


# ======================================================================
# Database abstraction
# ======================================================================


class RetentionDatabase(Protocol):
    """Interface the retention engine uses to interact with storage."""

    async def find_expired_records(
        self,
        tenant_id: str,
        category: DataCategory,
        cutoff: datetime,
    ) -> list[ExpiredRecord]: ...

    async def soft_delete(self, records: Sequence[ExpiredRecord]) -> int:
        """Mark records as soft-deleted. Return count of affected rows."""
        ...

    async def hard_delete(self, records: Sequence[ExpiredRecord]) -> int:
        """Permanently remove records. Return count of affected rows."""
        ...


# ======================================================================
# Retention engine
# ======================================================================


class RetentionEngine:
    """
    Orchestrates scanning and deletion of expired tenant data.

    Typical workflow::

        engine = RetentionEngine(db=my_adapter)
        expired = await engine.scan_expired_records("tenant_x", policy)
        soft_count = await engine.soft_delete_records(expired)
        # ... after grace period ...
        hard_count = await engine.hard_delete_records(expired)
    """

    def __init__(
        self,
        db: RetentionDatabase,
        *,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._db = db
        self._now: Callable[[], datetime] = now or (lambda: datetime.now(UTC))

    async def scan_expired_records(
        self,
        tenant_id: str,
        policy: RetentionPolicy | None = None,
    ) -> list[ExpiredRecord]:
        """
        Return all records for *tenant_id* whose retention limit has passed.
        """

        policy = policy or DEFAULT_POLICY
        now = self._now()
        all_expired: list[ExpiredRecord] = []

        for category in DataCategory:
            cutoff = now - timedelta(days=policy.days_for(category))
            records = await self._db.find_expired_records(tenant_id, category, cutoff)
            all_expired.extend(records)

        return all_expired

    async def soft_delete_records(
        self,
        records: Sequence[ExpiredRecord],
    ) -> int:
        """
        Soft-delete records (reversible during the grace period).

        Only processes records that have not already been soft-deleted.
        """

        candidates = [r for r in records if not r.soft_deleted]
        if not candidates:
            return 0
        return await self._db.soft_delete(candidates)

    async def hard_delete_records(
        self,
        records: Sequence[ExpiredRecord],
        policy: RetentionPolicy | None = None,
    ) -> int:
        """
        Hard-delete records whose grace period has elapsed.

        Only records that were soft-deleted **and** whose grace period has
        fully expired will be permanently removed.
        """

        policy = policy or DEFAULT_POLICY
        now = self._now()
        grace = timedelta(days=policy.grace_period_days)

        eligible = [
            r
            for r in records
            if r.soft_deleted
            and r.soft_deleted_at is not None
            and (now - r.soft_deleted_at) >= grace
        ]

        if not eligible:
            return 0
        return await self._db.hard_delete(eligible)
