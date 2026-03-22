"""Unit tests for AuthService — register, login, refresh, roles."""

from __future__ import annotations

from uuid import uuid4

import pytest
from cryptography.hazmat.primitives import serialization

# RSA key pair for tests (small, fast)
from cryptography.hazmat.primitives.asymmetric import rsa

from application.services.auth_service import (
    AuthenticationError,
    AuthService,
    InvalidTokenError,
    UserAlreadyExistsError,
)
from domain.models.tenant import Tenant, TenantStatus
from domain.models.user import TenantRole
from infrastructure.adapters import (
    InMemoryAuditRepository,
    InMemoryRefreshTokenStore,
    InMemoryTenantRepository,
    InMemoryUserRepository,
)


def _generate_rsa_keys():
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv_pem = private.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    pub_pem = (
        private.public_key()
        .public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )
    return priv_pem, pub_pem


PRIV_KEY, PUB_KEY = _generate_rsa_keys()


@pytest.fixture
def repos():
    tenant_repo = InMemoryTenantRepository()
    user_repo = InMemoryUserRepository()
    refresh_store = InMemoryRefreshTokenStore()
    audit_repo = InMemoryAuditRepository()
    return tenant_repo, user_repo, refresh_store, audit_repo


@pytest.fixture
def active_tenant(repos):
    tenant_repo = repos[0]
    tenant = Tenant(
        id=uuid4(),
        name="TestCorp",
        slug="test-corp",
        status=TenantStatus.ACTIVE,
        schema_name="tenant_test_corp",
    )
    tenant_repo.save(tenant)
    return tenant


@pytest.fixture
def auth_svc(repos):
    tenant_repo, user_repo, refresh_store, audit_repo = repos
    return AuthService(
        user_repo=user_repo,
        tenant_repo=tenant_repo,
        refresh_store=refresh_store,
        audit_repo=audit_repo,
        private_key=PRIV_KEY,
        public_key=PUB_KEY,
    )


class TestRegister:
    def test_register_first_user_is_owner(self, auth_svc, active_tenant):
        user = auth_svc.register_user(
            tenant_id=active_tenant.id,
            email="first@test.com",
            password="S3cret!Pass#",
            full_name="First User",
        )
        assert user.role == TenantRole.OWNER

    def test_register_second_user_is_member(self, auth_svc, active_tenant):
        auth_svc.register_user(active_tenant.id, "first@test.com", "S3cret!Pass#", "First")
        user2 = auth_svc.register_user(
            active_tenant.id, "second@test.com", "S3cret!Pass#", "Second"
        )
        assert user2.role == TenantRole.MEMBER

    def test_register_duplicate_email_raises(self, auth_svc, active_tenant):
        auth_svc.register_user(active_tenant.id, "dup@test.com", "S3cret!Pass#", "Dup")
        with pytest.raises(UserAlreadyExistsError):
            auth_svc.register_user(active_tenant.id, "dup@test.com", "S3cret!Pass#", "Dup2")

    def test_register_nonexistent_tenant_raises(self, auth_svc):
        from domain.exceptions import TenantNotFoundError

        with pytest.raises(TenantNotFoundError):
            auth_svc.register_user(uuid4(), "a@b.com", "S3cret!Pass#", "A")

    def test_register_inactive_tenant_raises(self, repos):
        tenant_repo, user_repo, refresh_store, audit_repo = repos
        tenant = Tenant(id=uuid4(), name="Pend", slug="pend", status=TenantStatus.PENDING)
        tenant_repo.save(tenant)
        svc = AuthService(
            user_repo=user_repo,
            tenant_repo=tenant_repo,
            refresh_store=refresh_store,
            audit_repo=audit_repo,
            private_key=PRIV_KEY,
            public_key=PUB_KEY,
        )
        with pytest.raises(AuthenticationError):
            svc.register_user(tenant.id, "a@b.com", "S3cret!Pass#", "A")


class TestAuthenticate:
    def test_login_success(self, auth_svc, active_tenant):
        auth_svc.register_user(active_tenant.id, "login@test.com", "S3cret!Pass#", "Login")
        tokens = auth_svc.authenticate("login@test.com", "S3cret!Pass#")
        assert tokens.access_token
        assert tokens.refresh_token
        assert tokens.token_type == "Bearer"

    def test_login_wrong_password(self, auth_svc, active_tenant):
        auth_svc.register_user(active_tenant.id, "wp@test.com", "S3cret!Pass#", "WP")
        with pytest.raises(AuthenticationError):
            auth_svc.authenticate("wp@test.com", "WrongPassword!")

    def test_login_unknown_email(self, auth_svc):
        with pytest.raises(AuthenticationError):
            auth_svc.authenticate("nobody@test.com", "S3cret!Pass#")

    def test_login_disabled_user(self, auth_svc, active_tenant):
        user = auth_svc.register_user(active_tenant.id, "dis@test.com", "S3cret!Pass#", "Disabled")
        user.is_active = False
        auth_svc._user_repo.update(user)
        with pytest.raises(AuthenticationError):
            auth_svc.authenticate("dis@test.com", "S3cret!Pass#")


class TestRefreshToken:
    def test_refresh_returns_new_pair(self, auth_svc, active_tenant):
        auth_svc.register_user(active_tenant.id, "ref@test.com", "S3cret!Pass#", "Ref")
        pair1 = auth_svc.authenticate("ref@test.com", "S3cret!Pass#")
        pair2 = auth_svc.refresh_token(pair1.refresh_token)
        assert pair2.access_token != pair1.access_token
        assert pair2.refresh_token != pair1.refresh_token

    def test_old_refresh_token_revoked(self, auth_svc, active_tenant):
        auth_svc.register_user(active_tenant.id, "rev@test.com", "S3cret!Pass#", "Rev")
        pair1 = auth_svc.authenticate("rev@test.com", "S3cret!Pass#")
        auth_svc.refresh_token(pair1.refresh_token)
        with pytest.raises(InvalidTokenError):
            auth_svc.refresh_token(pair1.refresh_token)

    def test_invalid_refresh_token(self, auth_svc):
        with pytest.raises(InvalidTokenError):
            auth_svc.refresh_token("totally-invalid-token")


class TestGetCurrentUser:
    def test_decode_valid_token(self, auth_svc, active_tenant):
        auth_svc.register_user(active_tenant.id, "cur@test.com", "S3cret!Pass#", "Current")
        tokens = auth_svc.authenticate("cur@test.com", "S3cret!Pass#")
        user = auth_svc.get_current_user(tokens.access_token)
        assert user.email == "cur@test.com"

    def test_invalid_token_raises(self, auth_svc):
        with pytest.raises(InvalidTokenError):
            auth_svc.get_current_user("invalid.jwt.token")
