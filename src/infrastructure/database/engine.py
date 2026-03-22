"""
SQLAlchemy engine setup with connection pooling and tenant-aware sessions.

Provides both synchronous and asynchronous engines, plus FastAPI-style
dependency helpers that yield properly-scoped database sessions.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import create_engine as sa_create_engine
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import QueuePool

from .config import (
    DatabaseSettings,
    get_async_database_url,
    get_database_url,
    get_default_settings,
)

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Generator

    from sqlalchemy.engine import Engine

# ---------------------------------------------------------------------------
# Engine factories
# ---------------------------------------------------------------------------


def build_sync_engine(settings: DatabaseSettings | None = None) -> Engine:
    """Create a synchronous SQLAlchemy :class:`Engine` with QueuePool.

    Parameters
    ----------
    settings:
        Database configuration.  Falls back to defaults when *None*.
    """
    s = settings or get_default_settings()
    engine = sa_create_engine(
        get_database_url(s),
        poolclass=QueuePool,
        pool_size=s.POOL_SIZE,
        max_overflow=s.MAX_OVERFLOW,
        pool_timeout=s.POOL_TIMEOUT,
        pool_pre_ping=True,
        echo=False,
    )
    return engine


def build_async_engine(settings: DatabaseSettings | None = None) -> AsyncEngine:
    """Create an asynchronous SQLAlchemy :class:`AsyncEngine`.

    Parameters
    ----------
    settings:
        Database configuration.  Falls back to defaults when *None*.
    """
    s = settings or get_default_settings()
    engine = create_async_engine(
        get_async_database_url(s),
        pool_size=s.POOL_SIZE,
        max_overflow=s.MAX_OVERFLOW,
        pool_timeout=s.POOL_TIMEOUT,
        pool_pre_ping=True,
        echo=False,
    )
    return engine


# ---------------------------------------------------------------------------
# Module-level singletons (lazily initialised on first import)
# ---------------------------------------------------------------------------

_sync_engine: Engine | None = None
_async_engine: AsyncEngine | None = None
_SyncSessionFactory: sessionmaker[Session] | None = None
_AsyncSessionFactory: async_sessionmaker[AsyncSession] | None = None


def get_sync_engine(settings: DatabaseSettings | None = None) -> Engine:
    """Return (or create) the module-level synchronous engine."""
    global _sync_engine
    if _sync_engine is None:
        _sync_engine = build_sync_engine(settings)
    return _sync_engine


def get_async_engine(settings: DatabaseSettings | None = None) -> AsyncEngine:
    """Return (or create) the module-level asynchronous engine."""
    global _async_engine
    if _async_engine is None:
        _async_engine = build_async_engine(settings)
    return _async_engine


def _sync_session_factory() -> sessionmaker[Session]:
    global _SyncSessionFactory
    if _SyncSessionFactory is None:
        _SyncSessionFactory = sessionmaker(
            bind=get_sync_engine(),
            expire_on_commit=False,
        )
    return _SyncSessionFactory


def _async_session_factory() -> async_sessionmaker[AsyncSession]:
    global _AsyncSessionFactory
    if _AsyncSessionFactory is None:
        _AsyncSessionFactory = async_sessionmaker(
            bind=get_async_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _AsyncSessionFactory


# ---------------------------------------------------------------------------
# Session dependency helpers (for FastAPI / DI frameworks)
# ---------------------------------------------------------------------------


def get_session() -> Generator[Session, None, None]:
    """Yield a synchronous :class:`Session` and ensure it is closed.

    Typical usage as a FastAPI dependency::

        @app.get("/items")
        def list_items(db: Session = Depends(get_session)):
            ...
    """
    session = _sync_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an asynchronous :class:`AsyncSession` and ensure it is closed.

    Typical usage as a FastAPI dependency::

        @app.get("/items")
        async def list_items(db: AsyncSession = Depends(get_async_session)):
            ...
    """
    async with _async_session_factory()() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# ---------------------------------------------------------------------------
# Tenant-aware session helpers
# ---------------------------------------------------------------------------


def _tenant_schema_name(tenant_id: str) -> str:
    """Derive the PostgreSQL schema name from a tenant identifier.

    The identifier is expected to be the tenant *slug* (lower-case,
    alphanumeric + hyphens).  The schema name follows the convention
    ``tenant_{slug}`` with hyphens replaced by underscores.
    """
    safe_slug = tenant_id.replace("-", "_")
    return f"tenant_{safe_slug}"


def get_tenant_session(tenant_id: str) -> Generator[Session, None, None]:
    """Yield a synchronous session whose ``search_path`` is set to the
    tenant's dedicated PostgreSQL schema.

    Parameters
    ----------
    tenant_id:
        The tenant slug used to derive the schema name.
    """
    schema = _tenant_schema_name(tenant_id)
    session = _sync_session_factory()()
    try:
        session.execute(text(f"SET search_path TO {schema}, public"))
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.execute(text("SET search_path TO public"))
        session.close()


async def get_async_tenant_session(
    tenant_id: str,
) -> AsyncGenerator[AsyncSession, None]:
    """Yield an asynchronous session routed to the tenant's schema.

    Parameters
    ----------
    tenant_id:
        The tenant slug used to derive the schema name.
    """
    schema = _tenant_schema_name(tenant_id)
    async with _async_session_factory()() as session:
        try:
            await session.execute(text(f"SET search_path TO {schema}, public"))
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.execute(text("SET search_path TO public"))


# ---------------------------------------------------------------------------
# Cleanup helpers
# ---------------------------------------------------------------------------


async def dispose_engines() -> None:
    """Dispose both engines, closing all pooled connections.

    Call this during application shutdown.
    """
    global _sync_engine, _async_engine, _SyncSessionFactory, _AsyncSessionFactory
    if _async_engine is not None:
        await _async_engine.dispose()
        _async_engine = None
        _AsyncSessionFactory = None
    if _sync_engine is not None:
        _sync_engine.dispose()
        _sync_engine = None
        _SyncSessionFactory = None
