"""Tests for src/domain/models/billing.py"""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from domain.models.billing import CostAnomaly, CostRecord, Invoice, ResourceType, UsageRecord


class TestResourceType:
    def test_enum_has_five_values(self):
        assert len(list(ResourceType)) == 5

    def test_enum_values(self):
        expected = {"CPU", "MEMORY", "STORAGE", "NETWORK", "API_CALLS"}
        assert {r.value for r in ResourceType} == expected


class TestUsageRecord:
    def test_defaults(self):
        record = UsageRecord()
        assert isinstance(record.id, UUID)
        assert isinstance(record.tenant_id, UUID)
        assert record.resource_type == ResourceType.CPU
        assert record.quantity == Decimal("0")
        assert record.unit == ""
        assert isinstance(record.recorded_at, datetime)

    def test_construction(self):
        tid = UUID("12345678-1234-5678-1234-567812345678")
        record = UsageRecord(
            tenant_id=tid,
            resource_type=ResourceType.MEMORY,
            quantity=Decimal("42.5"),
            unit="GB",
        )
        assert record.tenant_id == tid
        assert record.resource_type == ResourceType.MEMORY
        assert record.quantity == Decimal("42.5")
        assert record.unit == "GB"


class TestCostRecord:
    def test_defaults(self):
        record = CostRecord()
        assert isinstance(record.id, UUID)
        assert isinstance(record.tenant_id, UUID)
        assert isinstance(record.date, date)
        assert record.resource_type == ResourceType.CPU
        assert record.quantity == Decimal("0")
        assert record.unit_price == Decimal("0")
        assert record.total_cost == Decimal("0")
        assert record.currency == "EUR"

    def test_construction(self):
        record = CostRecord(
            resource_type=ResourceType.STORAGE,
            quantity=Decimal("100"),
            unit_price=Decimal("0.01"),
            total_cost=Decimal("1.00"),
            currency="USD",
        )
        assert record.resource_type == ResourceType.STORAGE
        assert record.total_cost == Decimal("1.00")
        assert record.currency == "USD"


class TestInvoice:
    def test_defaults(self):
        inv = Invoice()
        assert isinstance(inv.id, UUID)
        assert isinstance(inv.tenant_id, UUID)
        assert isinstance(inv.period_start, date)
        assert isinstance(inv.period_end, date)
        assert inv.line_items == []
        assert inv.total_amount == Decimal("0")
        assert inv.currency == "EUR"
        assert inv.status == "DRAFT"
        assert isinstance(inv.generated_at, datetime)

    def test_construction(self):
        inv = Invoice(
            total_amount=Decimal("250.00"),
            status="SENT",
            line_items=[{"desc": "CPU usage", "amount": 250}],
        )
        assert inv.total_amount == Decimal("250.00")
        assert inv.status == "SENT"
        assert len(inv.line_items) == 1


class TestCostAnomaly:
    def test_defaults(self):
        anomaly = CostAnomaly()
        assert isinstance(anomaly.id, UUID)
        assert isinstance(anomaly.tenant_id, UUID)
        assert anomaly.resource_type == ResourceType.CPU
        assert anomaly.expected_value == Decimal("0")
        assert anomaly.actual_value == Decimal("0")
        assert anomaly.deviation_factor == Decimal("0")
        assert isinstance(anomaly.detected_at, datetime)
        assert anomaly.acknowledged is False

    def test_construction(self):
        anomaly = CostAnomaly(
            resource_type=ResourceType.NETWORK,
            expected_value=Decimal("10.0"),
            actual_value=Decimal("50.0"),
            deviation_factor=Decimal("4.0"),
            acknowledged=True,
        )
        assert anomaly.resource_type == ResourceType.NETWORK
        assert anomaly.actual_value == Decimal("50.0")
        assert anomaly.acknowledged is True
