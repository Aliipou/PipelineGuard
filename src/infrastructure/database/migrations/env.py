"""Alembic environment configuration for tenant-aware migrations.

Supports both public schema (platform tables) and per-tenant schema migrations.
Usage:
  - Public: alembic upgrade head
  - Tenant: alembic -x tenant=tenant_slug upgrade head
"""

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool, text

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Build URL from environment if available
db_url = os.environ.get("DATABASE_URL") or config.get_main_option("sqlalchemy.url")


def get_tenant_schema() -> str | None:
    """Get tenant schema from alembic -x tenant=slug argument."""
    tenant = context.get_x_argument(as_dictionary=True).get("tenant")
    if tenant:
        return f"tenant_{tenant}"
    return None


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode — generates SQL script."""
    schema = get_tenant_schema()
    context.configure(
        url=db_url,
        target_metadata=None,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        version_table_schema=schema or "public",
        include_schemas=True,
    )

    with context.begin_transaction():
        if schema:
            context.execute(f"SET search_path TO {schema}, public")
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode — connects to database."""
    schema = get_tenant_schema()

    assert db_url is not None, "DATABASE_URL or sqlalchemy.url must be set"
    connectable = create_engine(db_url, poolclass=pool.NullPool)

    with connectable.connect() as connection:
        if schema:
            connection.execute(text(f"SET search_path TO {schema}, public"))

        context.configure(
            connection=connection,
            target_metadata=None,
            version_table_schema=schema or "public",
            include_schemas=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
