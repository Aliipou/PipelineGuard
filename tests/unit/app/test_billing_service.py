"""Unit tests for BillingService — usage, costs, invoices, anomalies."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from application.services.billing_service import BillingService
from domain.models.billing import CostRecord, ResourceType, UsageRecord
from domain.services.cost_calculator import CostCalculator
from infrastructure.adapters import (
    InMemoryAnomalyRepository,
    InMemoryAuditRepository,
    InMemoryCostRepository,
    InMemoryInvoiceRepository,
    InMemoryUsageRepository,
)


@pytest.fixture
def svc():
    return BillingService(
        usage_repo=InMemoryUsageRepository(),
        cost_repo=InMemoryCostRepository(),
        invoice_repo=InMemoryInvoiceRepository(),
        anomaly_repo=InMemoryAnomalyRepository(),
        audit_repo=InMemoryAuditRepository(),
        cost_calculator=CostCalculator(),
    )


class TestRecordUsage:
    def test_record_returns_usage_record(self, svc):
        rec = svc.record_usage(
            tenant_id=uuid4(),
            resource_type=ResourceType.CPU,
            quantity=Decimal("10"),
            unit="vCPU-hours",
        )
        assert rec.quantity == Decimal("10")
        assert rec.resource_type == ResourceType.CPU

    def test_record_persists(self, svc):
        tid = uuid4()
        svc.record_usage(tid, ResourceType.STORAGE, Decimal("5"), "GB-day")
        records = svc._usage_repo.get_by_tenant_and_date(tid, date.today())
        assert len(records) == 1


class TestCalculateDailyCosts:
    def test_aggregates_by_resource_type(self, svc):
        tid = uuid4()
        today = date.today()
        now = datetime.now(UTC)
        # Add 2 CPU records for the same day
        svc._usage_repo.save(
            UsageRecord(
                tenant_id=tid,
                resource_type=ResourceType.CPU,
                quantity=Decimal("10"),
                unit="vCPU-hours",
                recorded_at=now,
            )
        )
        svc._usage_repo.save(
            UsageRecord(
                tenant_id=tid,
                resource_type=ResourceType.CPU,
                quantity=Decimal("5"),
                unit="vCPU-hours",
                recorded_at=now,
            )
        )
        costs = svc.calculate_daily_costs(tid, today)
        assert len(costs) == 1
        assert costs[0].resource_type == ResourceType.CPU
        assert costs[0].quantity == Decimal("15")

    def test_no_usage_returns_empty(self, svc):
        costs = svc.calculate_daily_costs(uuid4(), date.today())
        assert costs == []


class TestGetCostBreakdown:
    def test_breakdown_totals(self, svc):
        tid = uuid4()
        today = date.today()
        svc._cost_repo.save_many(
            [
                CostRecord(
                    tenant_id=tid,
                    date=today,
                    resource_type=ResourceType.CPU,
                    total_cost=Decimal("10"),
                ),
                CostRecord(
                    tenant_id=tid,
                    date=today,
                    resource_type=ResourceType.MEMORY,
                    total_cost=Decimal("5"),
                ),
            ]
        )
        breakdown = svc.get_cost_breakdown(tid, today, today)
        assert breakdown.total == Decimal("15")
        assert "CPU" in breakdown.by_resource
        assert "MEMORY" in breakdown.by_resource

    def test_empty_range(self, svc):
        breakdown = svc.get_cost_breakdown(uuid4(), date(2026, 1, 1), date(2026, 1, 31))
        assert breakdown.total == Decimal("0")


class TestGenerateInvoice:
    def test_invoice_created_with_costs(self, svc):
        tid = uuid4()
        start = date(2026, 1, 1)
        end = date(2026, 1, 31)
        svc._cost_repo.save_many(
            [
                CostRecord(
                    tenant_id=tid,
                    date=date(2026, 1, 15),
                    resource_type=ResourceType.CPU,
                    quantity=Decimal("100"),
                    unit_price=Decimal("0.05"),
                    total_cost=Decimal("5.00"),
                ),
            ]
        )
        invoice = svc.generate_invoice(tid, start, end)
        assert invoice.total_amount == Decimal("5.00")
        assert invoice.status == "DRAFT"
        assert len(invoice.line_items) == 1

    def test_invoice_with_no_costs(self, svc):
        invoice = svc.generate_invoice(uuid4(), date(2026, 1, 1), date(2026, 1, 31))
        assert invoice.total_amount == Decimal("0.00")
        assert invoice.line_items == []


class TestProjectMonthlyCost:
    def test_projection_with_data(self, svc):
        tid = uuid4()
        today = date.today()
        month_start = today.replace(day=1)
        svc._cost_repo.save_many(
            [
                CostRecord(tenant_id=tid, date=month_start, total_cost=Decimal("10.00")),
            ]
        )
        projection = svc.project_monthly_cost(tid)
        assert projection.actual_cost >= Decimal("0")
        assert projection.projected_cost >= Decimal("0")
        assert projection.tenant_id == tid
