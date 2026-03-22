"""Tests for src/domain/models/tenant.py"""

from uuid import UUID

from domain.models.tenant import VALID_STATE_TRANSITIONS, Tenant, TenantSettings, TenantStatus


class TestTenantStatus:
    def test_enum_has_six_values(self):
        members = list(TenantStatus)
        assert len(members) == 6

    def test_enum_values(self):
        expected = {"PENDING", "PROVISIONING", "ACTIVE", "SUSPENDED", "DEPROVISIONING", "DELETED"}
        assert {s.value for s in TenantStatus} == expected


class TestValidStateTransitions:
    def test_pending_transitions(self):
        assert VALID_STATE_TRANSITIONS[TenantStatus.PENDING] == [
            TenantStatus.PROVISIONING,
            TenantStatus.DELETED,
        ]

    def test_provisioning_transitions(self):
        assert VALID_STATE_TRANSITIONS[TenantStatus.PROVISIONING] == [
            TenantStatus.ACTIVE,
            TenantStatus.DELETED,
        ]

    def test_active_transitions(self):
        assert VALID_STATE_TRANSITIONS[TenantStatus.ACTIVE] == [
            TenantStatus.SUSPENDED,
            TenantStatus.DEPROVISIONING,
        ]

    def test_suspended_transitions(self):
        assert VALID_STATE_TRANSITIONS[TenantStatus.SUSPENDED] == [
            TenantStatus.ACTIVE,
            TenantStatus.DEPROVISIONING,
        ]

    def test_deprovisioning_transitions(self):
        assert VALID_STATE_TRANSITIONS[TenantStatus.DEPROVISIONING] == [
            TenantStatus.DELETED,
        ]

    def test_deleted_transitions(self):
        assert VALID_STATE_TRANSITIONS[TenantStatus.DELETED] == []

    def test_all_statuses_present(self):
        assert set(VALID_STATE_TRANSITIONS.keys()) == set(TenantStatus)


class TestTenantDefaults:
    def test_id_is_uuid4(self):
        tenant = Tenant()
        assert isinstance(tenant.id, UUID)
        assert tenant.id.version == 4

    def test_status_is_pending(self):
        tenant = Tenant()
        assert tenant.status == TenantStatus.PENDING

    def test_empty_string_defaults(self):
        tenant = Tenant()
        assert tenant.name == ""
        assert tenant.slug == ""
        assert tenant.owner_email == ""
        assert tenant.schema_name == ""

    def test_unique_ids(self):
        t1 = Tenant()
        t2 = Tenant()
        assert t1.id != t2.id

    def test_settings_and_metadata_default_to_empty_dict(self):
        tenant = Tenant()
        assert tenant.settings == {}
        assert tenant.metadata == {}


class TestTenantSettings:
    def test_defaults(self):
        settings = TenantSettings()
        assert settings.max_users == 50
        assert settings.storage_limit_gb == 100
        assert settings.api_rate_limit == 1000
        assert settings.data_retention_days == 365
        assert settings.cost_alert_threshold == 1000.0
