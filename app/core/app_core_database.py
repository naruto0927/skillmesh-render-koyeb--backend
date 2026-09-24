"""
SkillMesh API — Database Engine & Session

Compatible with Render and any platform that sets DATABASE_URL.

Supabase (and Render) provide DATABASE_URL as:
  postgresql://user:pass@host/db   (standard, no driver suffix)

_make_async_url() normalises all variants to postgresql+asyncpg://
before SQLAlchemy sees them.  This is required because asyncpg will
not accept the bare postgresql:// scheme.

URL formats handled:
  postgres://...              → postgresql+asyncpg://...  (Heroku shorthand)
  postgresql://...            → postgresql+asyncpg://...  (Supabase / Render / standard)
  postgresql+psycopg2://...   → postgresql+asyncpg://...  (explicit psycopg2)
  postgresql+asyncpg://...    → unchanged                 (already correct)
"""

import re
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings

settings = get_settings()


def _make_async_url(url: str) -> str:
    """
    Normalise any PostgreSQL connection URL to use asyncpg driver.
    Called once at module import time.
    """
    url = url.strip()
    url = re.sub(r"^postgres://", "postgresql+asyncpg://", url)
    url = re.sub(r"^postgresql://", "postgresql+asyncpg://", url)
    url = re.sub(r"^postgresql\+psycopg2://", "postgresql+asyncpg://", url)
    return url


def _make_sync_url(url: str) -> str:
    """
    Normalise any PostgreSQL URL to use psycopg2 (sync) driver.
    Used by Alembic migrations only (alembic/env.py calls its own version;
    this helper is kept here for symmetry and testability).
    """
    url = url.strip()
    url = re.sub(r"^postgres://", "postgresql://", url)
    url = re.sub(r"^postgresql\+asyncpg://", "postgresql://", url)
    url = re.sub(r"^postgresql\+psycopg2://", "postgresql://", url)
    return url


_async_url = _make_async_url(settings.database_url)

engine = create_async_engine(
    _async_url,
    echo=settings.is_development,
    pool_pre_ping=True,    # Detect stale connections before use
    pool_size=5,
    max_overflow=10,
    pool_recycle=300,      # Recycle connections every 5 min (Render free-tier idle limits)
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models."""
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency — provides one AsyncSession per request.
    Rolls back on exception and always closes the session.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def check_db_connection() -> bool:
    """Used by the /api/v1/health/db endpoint."""
    try:
        from sqlalchemy import text
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
