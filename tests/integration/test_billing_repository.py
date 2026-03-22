"""Integration tests for billing repository operations."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from domain.models.billing import CostRecord, Invoice, ResourceType, UsageRecord
from infrastructure.adapters import (
    InMemoryCostRepository,
    InMemoryInvoiceRepository,
    InMemoryUsageRepository,
)


@pytest.mark.integration
class TestUsageRepository:
    def test_save_and_query_by_date(self):
        repo = InMemoryUsageRepository()
        tid = uuid4()
        rec = UsageRecord(
            tenant_id=tid,
            resource_type=ResourceType.CPU,
            quantity=Decimal("10.5"),
            unit="vCPU-hours",
            recorded_at=datetime(2026, 2, 17, 10, 0, tzinfo=UTC),
        )
        repo.save(rec)
        results = repo.get_by_tenant_and_date(tid, date(2026, 2, 17))
        assert len(results) == 1
        assert results[0].quantity == Decimal("10.5")

    def test_query_by_range(self):
        repo = InMemoryUsageRepository()
        tid = uuid4()
        for day in range(15, 20):
            repo.save(
                UsageRecord(
                    tenant_id=tid,
                    resource_type=ResourceType.STORAGE,
                    quantity=Decimal("1"),
                    unit="GB-day",
                    recorded_at=datetime(2026, 2, day, 12, 0, tzinfo=UTC),
                )
            )
        results = repo.get_by_tenant_and_range(tid, date(2026, 2, 16), date(2026, 2, 18))
        assert len(results) == 3


@pytest.mark.integration
class TestCostRepository:
    def test_save_many_and_query(self):
        repo = InMemoryCostRepository()
        tid = uuid4()
        records = [
            CostRecord(
                tenant_id=tid,
                date=date(2026, 2, 17),
                resource_type=ResourceType.CPU,
                total_cost=Decimal("5.00"),
            ),
            CostRecord(
                tenant_id=tid,
                date=date(2026, 2, 17),
                resource_type=ResourceType.MEMORY,
                total_cost=Decimal("3.00"),
            ),
        ]
        saved = repo.save_many(records)
        assert len(saved) == 2
        results = repo.get_by_tenant_and_date(tid, date(2026, 2, 17))
        assert len(results) == 2


@pytest.mark.integration
class TestInvoiceRepository:
    def test_save_and_query_by_period(self):
        repo = InMemoryInvoiceRepository()
        tid = uuid4()
        inv = Invoice(
            tenant_id=tid,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 1, 31),
            total_amount=Decimal("100.00"),
        )
        repo.save(inv)
        result = repo.get_by_tenant_and_period(tid, date(2026, 1, 1), date(2026, 1, 31))
        assert result is not None
        assert result.total_amount == Decimal("100.00")

    def test_query_nonexistent_period(self):
        repo = InMemoryInvoiceRepository()
        result = repo.get_by_tenant_and_period(uuid4(), date(2026, 1, 1), date(2026, 1, 31))
        assert result is None
