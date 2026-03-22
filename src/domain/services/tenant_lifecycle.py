from __future__ import annotations

from domain.models.tenant import TenantStatus

VALID_TRANSITIONS: dict[TenantStatus, list[TenantStatus]] = {
    TenantStatus.PENDING: [TenantStatus.PROVISIONING, TenantStatus.DELETED],
    TenantStatus.PROVISIONING: [TenantStatus.ACTIVE, TenantStatus.DELETED],
    TenantStatus.ACTIVE: [TenantStatus.SUSPENDED, TenantStatus.DEPROVISIONING],
    TenantStatus.SUSPENDED: [TenantStatus.ACTIVE, TenantStatus.DEPROVISIONING],
    TenantStatus.DEPROVISIONING: [TenantStatus.DELETED],
    TenantStatus.DELETED: [],
}

_TRANSITION_ACTIONS: dict[tuple[TenantStatus, TenantStatus], list[str]] = {
    (TenantStatus.PENDING, TenantStatus.PROVISIONING): [
        "create_schema",
        "initialize_default_settings",
        "send_provisioning_notification",
    ],
    (TenantStatus.PROVISIONING, TenantStatus.ACTIVE): [
        "activate_schema",
        "enable_api_access",
        "send_welcome_notification",
    ],
    (TenantStatus.PROVISIONING, TenantStatus.DELETED): [
        "cleanup_partial_schema",
        "send_failure_notification",
    ],
    (TenantStatus.ACTIVE, TenantStatus.SUSPENDED): [
        "disable_api_access",
        "send_suspension_notification",
    ],
    (TenantStatus.ACTIVE, TenantStatus.DEPROVISIONING): [
        "disable_api_access",
        "schedule_data_export",
        "send_deprovisioning_notification",
    ],
    (TenantStatus.SUSPENDED, TenantStatus.ACTIVE): [
        "enable_api_access",
        "send_reactivation_notification",
    ],
    (TenantStatus.SUSPENDED, TenantStatus.DEPROVISIONING): [
        "schedule_data_export",
        "send_deprovisioning_notification",
    ],
    (TenantStatus.DEPROVISIONING, TenantStatus.DELETED): [
        "delete_schema",
        "purge_tenant_data",
        "send_deletion_confirmation",
    ],
    (TenantStatus.PENDING, TenantStatus.DELETED): [
        "send_cancellation_notification",
    ],
}


class TenantLifecycleService:
    def validate_transition(
        self,
        current_state: TenantStatus,
        new_state: TenantStatus,
    ) -> bool:
        allowed = VALID_TRANSITIONS.get(current_state, [])
        return new_state in allowed

    def get_transition_actions(
        self,
        current_state: TenantStatus,
        new_state: TenantStatus,
    ) -> list[str]:
        return list(_TRANSITION_ACTIONS.get((current_state, new_state), []))
