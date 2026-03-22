"""Tests for infrastructure.auth.rbac."""

from __future__ import annotations

import asyncio

from infrastructure.auth.rbac import (
    ROLE_PERMISSIONS,
    Permission,
    TenantRole,
    require_permission,
    require_role,
)


class TestPermissionEnum:
    def test_has_10_values(self) -> None:
        assert len(Permission) == 10

    def test_known_members(self) -> None:
        assert Permission.TENANT_READ.value == "tenant:read"
        assert Permission.AUDIT_READ.value == "audit:read"


class TestTenantRole:
    def test_has_4_values(self) -> None:
        assert len(TenantRole) == 4

    def test_ordering(self) -> None:
        assert TenantRole.VIEWER == 10
        assert TenantRole.MEMBER == 20
        assert TenantRole.ADMIN == 30
        assert TenantRole.OWNER == 40

    def test_viewer_less_than_owner(self) -> None:
        assert TenantRole.VIEWER < TenantRole.OWNER


class TestRolePermissions:
    def test_owner_has_all_permissions(self) -> None:
        assert ROLE_PERMISSIONS[TenantRole.OWNER] == set(Permission)

    def test_viewer_lacks_tenant_write(self) -> None:
        viewer_perms = ROLE_PERMISSIONS[TenantRole.VIEWER]
        assert Permission.TENANT_WRITE not in viewer_perms

    def test_admin_lacks_tenant_admin(self) -> None:
        admin_perms = ROLE_PERMISSIONS[TenantRole.ADMIN]
        assert Permission.TENANT_ADMIN not in admin_perms


class TestRequirePermission:
    def test_returns_async_callable(self) -> None:
        dep = require_permission(Permission.BILLING_READ)
        assert callable(dep)
        assert asyncio.iscoroutinefunction(dep)


class TestRequireRole:
    def test_returns_async_callable(self) -> None:
        dep = require_role(TenantRole.ADMIN)
        assert callable(dep)
        assert asyncio.iscoroutinefunction(dep)
