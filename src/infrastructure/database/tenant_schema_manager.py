"""
Schema-per-tenant management for PostgreSQL.

Each tenant is isolated in its own PostgreSQL schema named
``tenant_{slug}`` (hyphens in the slug are replaced with underscores).
This module provides the :class:`TenantSchemaManager` that handles
creation, deletion, existence checks, listing, and size reporting of
these schemas using raw SQL over a SQLAlchemy engine connection.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from sqlalchemy import text

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine
    from sqlalchemy.ext.asyncio import AsyncEngine


def _sanitise_slug(slug: str) -> str:
    """Convert a tenant slug into a safe PostgreSQL schema name component.

    Raises :class:`ValueError` if the slug contains characters that are
    not alphanumeric, hyphens, or underscores.
    """
    if not re.match(r"^[a-z0-9][a-z0-9_-]*$", slug):
        raise ValueError(f"Invalid tenant slug: {slug!r}.  Must match ^[a-z0-9][a-z0-9_-]*$")
    return slug.replace("-", "_")


def _schema_name(slug: str) -> str:
    """Return the fully-qualified schema name for a tenant slug."""
    return f"tenant_{_sanitise_slug(slug)}"


class TenantSchemaManager:
    """Manages per-tenant PostgreSQL schemas via raw SQL.

    Parameters
    ----------
    engine:
        A synchronous SQLAlchemy :class:`Engine` used to execute DDL
        statements.
    """

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    # ------------------------------------------------------------------
    # Schema lifecycle
    # ------------------------------------------------------------------

    def create_schema(self, tenant_slug: str) -> str:
        """Create a new PostgreSQL schema for the given tenant.

        Parameters
        ----------
        tenant_slug:
            The unique slug identifying the tenant.

        Returns
        -------
        str
            The created schema name.

        Raises
        ------
        ValueError
            If the slug is invalid.
        RuntimeError
            If the schema already exists.
        """
        schema = _schema_name(tenant_slug)
        with self._engine.begin() as conn:
            exists = self._check_exists(conn, schema)
            if exists:
                raise RuntimeError(f"Schema {schema!r} already exists for tenant {tenant_slug!r}")
            conn.execute(text(f"CREATE SCHEMA {schema}"))
        return schema

    def drop_schema(self, tenant_slug: str) -> None:
        """Drop a tenant's schema with CASCADE.

        .. warning::
            This permanently destroys **all** data in the schema.

        Parameters
        ----------
        tenant_slug:
            The unique slug identifying the tenant.

        Raises
        ------
        ValueError
            If the slug is invalid.
        RuntimeError
            If the schema does not exist.
        """
        schema = _schema_name(tenant_slug)
        with self._engine.begin() as conn:
            if not self._check_exists(conn, schema):
                raise RuntimeError(f"Schema {schema!r} does not exist for tenant {tenant_slug!r}")
            conn.execute(text(f"DROP SCHEMA {schema} CASCADE"))

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def schema_exists(self, tenant_slug: str) -> bool:
        """Return whether the tenant schema exists.

        Parameters
        ----------
        tenant_slug:
            The unique slug identifying the tenant.
        """
        schema = _schema_name(tenant_slug)
        with self._engine.connect() as conn:
            return self._check_exists(conn, schema)

    def list_schemas(self) -> list[str]:
        """Return a sorted list of all ``tenant_*`` schema names."""
        with self._engine.connect() as conn:
            result = conn.execute(
                text(
                    "SELECT schema_name FROM information_schema.schemata "
                    "WHERE schema_name LIKE 'tenant_%' "
                    "ORDER BY schema_name"
                )
            )
            return [row[0] for row in result.fetchall()]

    def get_schema_size(self, tenant_slug: str) -> int:
        """Return the on-disk size of a tenant schema in bytes.

        Parameters
        ----------
        tenant_slug:
            The unique slug identifying the tenant.

        Returns
        -------
        int
            Size in bytes.

        Raises
        ------
        RuntimeError
            If the schema does not exist.
        """
        schema = _schema_name(tenant_slug)
        with self._engine.connect() as conn:
            if not self._check_exists(conn, schema):
                raise RuntimeError(f"Schema {schema!r} does not exist for tenant {tenant_slug!r}")
            result = conn.execute(
                text(
                    "SELECT COALESCE(SUM(pg_total_relation_size(quote_ident(schemaname) "
                    "|| '.' || quote_ident(tablename))), 0) "
                    "FROM pg_tables WHERE schemaname = :schema"
                ),
                {"schema": schema},
            )
            row = result.fetchone()
            return int(row[0]) if row else 0

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _check_exists(conn: Any, schema: str) -> bool:
        result = conn.execute(
            text("SELECT 1 FROM information_schema.schemata WHERE schema_name = :schema"),
            {"schema": schema},
        )
        return result.fetchone() is not None


# ---------------------------------------------------------------------------
# Async variant
# ---------------------------------------------------------------------------


class AsyncTenantSchemaManager:
    """Async counterpart of :class:`TenantSchemaManager`.

    Parameters
    ----------
    engine:
        An asynchronous SQLAlchemy :class:`AsyncEngine`.
    """

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def create_schema(self, tenant_slug: str) -> str:
        schema = _schema_name(tenant_slug)
        async with self._engine.begin() as conn:
            exists = await self._check_exists(conn, schema)
            if exists:
                raise RuntimeError(f"Schema {schema!r} already exists for tenant {tenant_slug!r}")
            await conn.execute(text(f"CREATE SCHEMA {schema}"))
        return schema

    async def drop_schema(self, tenant_slug: str) -> None:
        schema = _schema_name(tenant_slug)
        async with self._engine.begin() as conn:
            if not await self._check_exists(conn, schema):
                raise RuntimeError(f"Schema {schema!r} does not exist for tenant {tenant_slug!r}")
            await conn.execute(text(f"DROP SCHEMA {schema} CASCADE"))

    async def schema_exists(self, tenant_slug: str) -> bool:
        schema = _schema_name(tenant_slug)
        async with self._engine.connect() as conn:
            return await self._check_exists(conn, schema)

    async def list_schemas(self) -> list[str]:
        async with self._engine.connect() as conn:
            result = await conn.execute(
                text(
                    "SELECT schema_name FROM information_schema.schemata "
                    "WHERE schema_name LIKE 'tenant_%' "
                    "ORDER BY schema_name"
                )
            )
            return [row[0] for row in result.fetchall()]

    async def get_schema_size(self, tenant_slug: str) -> int:
        schema = _schema_name(tenant_slug)
        async with self._engine.connect() as conn:
            if not await self._check_exists(conn, schema):
                raise RuntimeError(f"Schema {schema!r} does not exist for tenant {tenant_slug!r}")
            result = await conn.execute(
                text(
                    "SELECT COALESCE(SUM(pg_total_relation_size(quote_ident(schemaname) "
                    "|| '.' || quote_ident(tablename))), 0) "
                    "FROM pg_tables WHERE schemaname = :schema"
                ),
                {"schema": schema},
            )
            row = result.fetchone()
            return int(row[0]) if row else 0

    @staticmethod
    async def _check_exists(conn: Any, schema: str) -> bool:
        result = await conn.execute(
            text("SELECT 1 FROM information_schema.schemata WHERE schema_name = :schema"),
            {"schema": schema},
        )
        return result.fetchone() is not None
