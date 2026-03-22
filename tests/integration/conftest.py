"""Integration test fixtures using testcontainers for PostgreSQL and Redis."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))


@pytest.fixture(scope="session")
def postgres_url():
    """Provide a PostgreSQL URL via testcontainers.

    Falls back to a local connection string if testcontainers is unavailable
    (CI without Docker).
    """
    try:
        from testcontainers.postgres import PostgresContainer

        with PostgresContainer("postgres:16-alpine") as pg:
            yield pg.get_connection_url()
    except Exception:
        pytest.skip("PostgreSQL testcontainer unavailable")


@pytest.fixture(scope="session")
def redis_url():
    """Provide a Redis URL via testcontainers."""
    try:
        from testcontainers.redis import RedisContainer

        with RedisContainer("redis:7-alpine") as r:
            yield f"redis://{r.get_container_host_ip()}:{r.get_exposed_port(6379)}/0"
    except Exception:
        pytest.skip("Redis testcontainer unavailable")


@pytest.fixture
def sync_engine(postgres_url):
    """Create a synchronous SQLAlchemy engine for integration tests."""
    from sqlalchemy import create_engine

    engine = create_engine(postgres_url, echo=False)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(sync_engine):
    """Provide a scoped database session with rollback."""
    from sqlalchemy.orm import sessionmaker

    session_factory = sessionmaker(bind=sync_engine)
    session = session_factory()
    yield session
    session.rollback()
    session.close()
