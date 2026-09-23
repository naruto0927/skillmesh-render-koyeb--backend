"""
SkillMesh API — Database Engine & Session
Uses SQLAlchemy async engine backed by asyncpg.
The DATABASE_URL environment variable controls which PostgreSQL instance is used
(local Docker in development, Supabase in staging/production).
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings

settings = get_settings()

# Create the async engine.
# echo=True in development prints all SQL — helpful for debugging, noisy in production.
engine = create_async_engine(
    settings.database_url,
    echo=settings.is_development,
    pool_pre_ping=True,  # Verify connections before use (handles dropped DB connections)
    pool_size=5,
    max_overflow=10,
)

# Session factory — use this to create sessions
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,  # Allows accessing attributes after commit without re-querying
    autocommit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    """
    Base class for all SQLAlchemy ORM models.
    All models in app/models/ should inherit from this.
    """
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that provides a database session per request.
    Automatically closes the session when the request is complete.

    Usage in route:
        async def my_route(db: AsyncSession = Depends(get_db)):
            ...
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
    """
    Attempt a simple database query to verify connectivity.
    Used by the /health/db endpoint.
    Returns True if the database is reachable, False otherwise.
    """
    try:
        from sqlalchemy import text
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
