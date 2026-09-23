"""
SkillMesh — Base Model Mixin
All ORM models inherit from TimestampMixin to get consistent
created_at / updated_at timestamps and a UUID primary key.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class TimestampMixin:
    """
    Adds created_at and updated_at to any model.
    Both are set by the database — never trust client-provided timestamps.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class UUIDPrimaryKeyMixin:
    """
    UUID primary key — externally exposed identifier.
    Sequential integers are never exposed in URLs or API responses.
    """

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )


class BaseModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    Abstract base for all SkillMesh models.
    Provides UUID PK + timestamps.
    """

    __abstract__ = True
