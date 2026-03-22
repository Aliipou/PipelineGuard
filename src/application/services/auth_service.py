"""Authentication and authorisation application service.

Handles user registration, credential validation, JWT token issuance /
rotation, and login auditing.  Uses *argon2-cffi* for password hashing
and *python-jose* for RS256 JWT operations.
"""

from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol
from uuid import UUID, uuid4

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from jose import JWTError, jwt

from domain.exceptions import TenantNotFoundError
from domain.models.audit import AuditAction, AuditEntry
from domain.models.tenant import Tenant, TenantStatus
from domain.models.user import TenantRole, User

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Value objects
# ---------------------------------------------------------------------------

ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
REFRESH_TOKEN_EXPIRE_DAYS: int = 7
JWT_ALGORITHM: str = "RS256"


@dataclass(frozen=True)
class TokenPair:
    """Immutable pair of access + refresh tokens."""

    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int = ACCESS_TOKEN_EXPIRE_MINUTES * 60


# ---------------------------------------------------------------------------
# Repository / infrastructure port interfaces
# ---------------------------------------------------------------------------


class UserRepository(Protocol):
    """Port: persistence operations for :class:`User` aggregates."""

    def get_by_id(self, user_id: UUID) -> User | None: ...

    def get_by_email(self, email: str) -> User | None: ...

    def count_by_tenant(self, tenant_id: UUID) -> int: ...

    def save(self, user: User) -> User: ...

    def update(self, user: User) -> User: ...


class TenantRepository(Protocol):
    """Port: read-only tenant lookup for auth validations."""

    def get_by_id(self, tenant_id: UUID) -> Tenant | None: ...


class RefreshTokenStore(Protocol):
    """Port: opaque refresh-token persistence and rotation."""

    def store(self, token_id: str, user_id: UUID, expires_at: datetime) -> None: ...

    def validate(self, token_id: str) -> UUID | None: ...

    def revoke(self, token_id: str) -> None: ...


class AuditRepository(Protocol):
    """Port: tamper-evident audit entries."""

    def get_latest_entry(self, tenant_id: UUID) -> AuditEntry | None: ...

    def save(self, entry: AuditEntry) -> AuditEntry: ...


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class AuthenticationError(Exception):
    """Raised when credentials are invalid."""

    def __init__(self, detail: str = "Invalid credentials") -> None:
        self.detail = detail
        super().__init__(detail)


class InvalidTokenError(Exception):
    """Raised when a JWT or refresh token cannot be validated."""

    def __init__(self, detail: str = "Invalid or expired token") -> None:
        self.detail = detail
        super().__init__(detail)


class UserAlreadyExistsError(Exception):
    """Raised when attempting to register a duplicate email."""

    def __init__(self, email: str = "") -> None:
        self.email = email
        super().__init__(f"User already exists: {email}")


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class AuthService:
    """Handles registration, authentication, and JWT lifecycle."""

    def __init__(
        self,
        user_repo: UserRepository,
        tenant_repo: TenantRepository,
        refresh_store: RefreshTokenStore,
        audit_repo: AuditRepository,
        private_key: str,
        public_key: str,
        issuer: str = "eu-multi-tenant-platform",
    ) -> None:
        self._user_repo = user_repo
        self._tenant_repo = tenant_repo
        self._refresh_store = refresh_store
        self._audit_repo = audit_repo
        self._private_key = private_key
        self._public_key = public_key
        self._issuer = issuer
        self._hasher = PasswordHasher()

    # -- helpers ----------------------------------------------------------

    def _hash_password(self, password: str) -> str:
        return str(self._hasher.hash(password))

    def _verify_password(self, password: str, hashed: str) -> bool:
        try:
            return bool(self._hasher.verify(hashed, password))
        except VerifyMismatchError:
            return False

    def _create_access_token(self, user: User) -> str:
        now = datetime.now(UTC)
        claims: dict[str, Any] = {
            "sub": str(user.id),
            "tenant_id": str(user.tenant_id),
            "email": user.email,
            "role": user.role.value,
            "iss": self._issuer,
            "iat": now,
            "exp": now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
            "jti": uuid4().hex,
        }
        return str(jwt.encode(claims, self._private_key, algorithm=JWT_ALGORITHM))

    def _create_refresh_token(self, user: User) -> str:
        token_id = secrets.token_urlsafe(48)
        expires_at = datetime.now(UTC) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
        self._refresh_store.store(
            token_id=token_id,
            user_id=user.id,
            expires_at=expires_at,
        )
        return token_id

    def _issue_token_pair(self, user: User) -> TokenPair:
        return TokenPair(
            access_token=self._create_access_token(user),
            refresh_token=self._create_refresh_token(user),
        )

    def _create_audit_entry(
        self,
        tenant_id: UUID,
        action: AuditAction,
        actor_id: UUID,
        details: dict[str, Any] | None = None,
    ) -> AuditEntry:
        latest = self._audit_repo.get_latest_entry(tenant_id)
        previous_hash = latest.entry_hash if latest else ""
        entry = AuditEntry(
            id=uuid4(),
            tenant_id=tenant_id,
            action=action,
            actor_id=actor_id,
            details=details or {},
            timestamp=datetime.now(UTC),
            previous_hash=previous_hash,
        )
        return self._audit_repo.save(entry)

    # -- public API -------------------------------------------------------

    def register_user(
        self,
        tenant_id: UUID,
        email: str,
        password: str,
        full_name: str,
    ) -> User:
        """Register a new user within a tenant.

        The first user registered for a tenant automatically receives
        the OWNER role.
        """
        # Validate tenant exists and is active
        tenant = self._tenant_repo.get_by_id(tenant_id)
        if tenant is None:
            raise TenantNotFoundError(tenant_id=str(tenant_id))
        if tenant.status != TenantStatus.ACTIVE:
            raise AuthenticationError(
                detail=f"Tenant {tenant_id} is not active (status={tenant.status.value})"
            )

        # Ensure email uniqueness
        if self._user_repo.get_by_email(email) is not None:
            raise UserAlreadyExistsError(email=email)

        # Determine role
        user_count = self._user_repo.count_by_tenant(tenant_id)
        role = TenantRole.OWNER if user_count == 0 else TenantRole.MEMBER

        user = User(
            id=uuid4(),
            tenant_id=tenant_id,
            email=email,
            hashed_password=self._hash_password(password),
            full_name=full_name,
            role=role,
            is_active=True,
            created_at=datetime.now(UTC),
        )
        user = self._user_repo.save(user)
        logger.info("User %s registered in tenant %s with role %s", user.id, tenant_id, role.value)

        self._create_audit_entry(
            tenant_id=tenant_id,
            action=AuditAction.TENANT_UPDATED,
            actor_id=user.id,
            details={"event": "user_registered", "email": email, "role": role.value},
        )
        return user

    def authenticate(self, email: str, password: str) -> TokenPair:
        """Validate credentials and return an access / refresh token pair."""
        user = self._user_repo.get_by_email(email)
        if user is None:
            raise AuthenticationError()

        if not user.is_active:
            raise AuthenticationError(detail="User account is disabled")

        if not self._verify_password(password, user.hashed_password):
            raise AuthenticationError()

        # Update last login
        user.last_login = datetime.now(UTC)
        self._user_repo.update(user)

        token_pair = self._issue_token_pair(user)

        self._create_audit_entry(
            tenant_id=user.tenant_id,
            action=AuditAction.USER_LOGIN,
            actor_id=user.id,
            details={"email": email},
        )
        logger.info("User %s authenticated successfully", user.id)
        return token_pair

    def refresh_token(self, refresh_token: str) -> TokenPair:
        """Rotate a refresh token and issue a new token pair.

        The old refresh token is revoked immediately.
        """
        user_id = self._refresh_store.validate(refresh_token)
        if user_id is None:
            raise InvalidTokenError(detail="Refresh token is invalid or expired")

        # Revoke old token (rotation)
        self._refresh_store.revoke(refresh_token)

        user = self._user_repo.get_by_id(user_id)
        if user is None or not user.is_active:
            raise InvalidTokenError(detail="User not found or inactive")

        return self._issue_token_pair(user)

    def get_current_user(self, token: str) -> User:
        """Decode and validate an access token, returning the associated user."""
        try:
            payload = jwt.decode(
                token,
                self._public_key,
                algorithms=[JWT_ALGORITHM],
                issuer=self._issuer,
            )
        except JWTError as exc:
            raise InvalidTokenError(detail=str(exc)) from exc

        user_id_str: str | None = payload.get("sub")
        if user_id_str is None:
            raise InvalidTokenError(detail="Token missing 'sub' claim")

        try:
            user_id = UUID(user_id_str)
        except ValueError as exc:
            raise InvalidTokenError(detail="Invalid user ID in token") from exc

        user = self._user_repo.get_by_id(user_id)
        if user is None or not user.is_active:
            raise InvalidTokenError(detail="User not found or inactive")

        return user
