"""Tests for src/domain/events/tenant_events.py"""

from datetime import UTC, datetime
from uuid import UUID

from domain.events.tenant_events import (
    CostAnomalyDetected,
    TenantActivated,
    TenantCreated,
    TenantDeleted,
    TenantDeprovisioning,
    TenantEvent,
    TenantProvisioned,
    TenantSuspended,
)
from domain.models.billing import ResourceType


class TestTenantEventBase:
    def test_tenant_id_is_uuid4(self):
        event = TenantEvent()
        assert isinstance(event.tenant_id, UUID)
        assert event.tenant_id.version == 4

    def test_timestamp_is_utc(self):
        event = TenantEvent()
        assert isinstance(event.timestamp, datetime)
        assert event.timestamp.tzinfo is not None
        assert event.timestamp.tzinfo == UTC

    def test_default_event_type_is_empty(self):
        event = TenantEvent()
        assert event.event_type == ""


class TestSubclassEventTypes:
    def test_tenant_created(self):
        assert TenantCreated().event_type == "TenantCreated"

    def test_tenant_provisioned(self):
        assert TenantProvisioned().event_type == "TenantProvisioned"

    def test_tenant_activated(self):
        assert TenantActivated().event_type == "TenantActivated"

    def test_tenant_suspended(self):
        assert TenantSuspended().event_type == "TenantSuspended"

    def test_tenant_deprovisioning(self):
        assert TenantDeprovisioning().event_type == "TenantDeprovisioning"

    def test_tenant_deleted(self):
        assert TenantDeleted().event_type == "TenantDeleted"

    def test_cost_anomaly_detected(self):
        assert CostAnomalyDetected().event_type == "CostAnomalyDetected"

    def test_all_seven_subclass_event_types(self):
        expected = {
            "TenantCreated",
            "TenantProvisioned",
            "TenantActivated",
            "TenantSuspended",
            "TenantDeprovisioning",
            "TenantDeleted",
            "CostAnomalyDetected",
        }
        subclasses = [
            TenantCreated,
            TenantProvisioned,
            TenantActivated,
            TenantSuspended,
            TenantDeprovisioning,
            TenantDeleted,
            CostAnomalyDetected,
        ]
        assert {cls().event_type for cls in subclasses} == expected


class TestCostAnomalyDetected:
    def test_has_resource_type(self):
        event = CostAnomalyDetected(resource_type=ResourceType.STORAGE)
        assert event.resource_type == ResourceType.STORAGE

    def test_has_deviation(self):
        event = CostAnomalyDetected(deviation=3.5)
        assert event.deviation == 3.5

    def test_defaults(self):
        event = CostAnomalyDetected()
        assert event.resource_type == ResourceType.CPU
        assert event.deviation == 0.0
