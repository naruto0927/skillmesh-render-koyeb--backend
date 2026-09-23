"""
Alembic migration environment.
Reads DATABASE_URL from environment variables — never hardcoded.
Uses synchronous psycopg2 URL for migration execution (Alembic is sync).
"""

import os
import re
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Import Base so Alembic can detect model changes for autogenerate
from app.core.database import Base  # noqa: F401

# Import all models so Alembic autogenerate sees every table.
# This is the single place to register new models.
import app.models  # noqa: F401

# ─── Alembic config ───────────────────────────────────────────────────────────
config = context.config

# Set up Python logging from alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# SQLAlchemy MetaData for autogenerate support
target_metadata = Base.metadata


def get_sync_database_url() -> str:
    """
    Convert any database URL variant to a synchronous psycopg2 URL for Alembic.
    Handles all formats Heroku and local dev might provide:
      postgres://          → postgresql://
      postgresql+asyncpg:// → postgresql://
      postgresql://        → postgresql:// (unchanged)
    """
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        raise RuntimeError(
            "DATABASE_URL environment variable is not set. "
            "Copy .env.example to .env and configure your database URL."
        )
    # Heroku shorthand
    url = re.sub(r"^postgres://", "postgresql://", url)
    # Strip async driver — Alembic is sync
    url = re.sub(r"^postgresql\+asyncpg://", "postgresql://", url)
    url = re.sub(r"^postgresql\+psycopg2://", "postgresql://", url)
    return url


def run_migrations_offline() -> None:
    """
    Run migrations in 'offline' mode.
    Generates SQL without requiring a database connection.
    Useful for reviewing migration SQL before applying.
    """
    url = get_sync_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """
    Run migrations in 'online' mode.
    Connects to the database and applies migrations directly.
    """
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = get_sync_database_url()

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,  # No connection pooling in migration context
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,  # Detect column type changes
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
