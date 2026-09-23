"""
SkillMesh — User Model
Central identity record that links to a Supabase Auth user (via supabase_uid).

Design:
- Supabase Auth handles authentication (password hashing, sessions, OAuth)
- This table stores application-level identity and role
- The supabase_uid is the bridge between Supabase Auth and our application data
- One user can have exactly one role (roles are not additive in Phase 1)
"""

import enum
import uuid

from sqlalchemy import Boolean, Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class UserRole(str, enum.Enum):
    """
    All roles in the system.
    Stored as a string enum in PostgreSQL for readability and migration safety.
    """

    SUPER_ADMIN = "SUPER_ADMIN"
    INSTITUTION_ADMIN = "INSTITUTION_ADMIN"
    FACULTY = "FACULTY"
    STUDENT = "STUDENT"
    INDUSTRY_ADMIN = "INDUSTRY_ADMIN"
    RECRUITER = "RECRUITER"


class User(BaseModel):
    """
    Application user record.
    Authentication is handled by Supabase — this stores application identity.

    Relationships:
      - institution_id → Institution (for INSTITUTION_ADMIN, FACULTY, STUDENT)
      - industry_org_id → IndustryOrganization (for INDUSTRY_ADMIN, RECRUITER)
    """

    __tablename__ = "users"

    # ─── Supabase Auth link ────────────────────────────────────────────────────
    # This is the `id` from Supabase Auth's auth.users table.
    # Indexed for fast JWT → user lookups.
    supabase_uid: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
    )

    # ─── Identity ─────────────────────────────────────────────────────────────
    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
    )
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    avatar_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ─── Role ─────────────────────────────────────────────────────────────────
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role", create_type=True),
        nullable=False,
        index=True,
    )

    # ─── Account state ────────────────────────────────────────────────────────
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_onboarded: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # ─── Tenant links (nullable — only relevant to certain roles) ─────────────
    # INSTITUTION_ADMIN, FACULTY, STUDENT → institution_id
    institution_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("institutions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # INDUSTRY_ADMIN, RECRUITER → industry_org_id
    industry_org_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("industry_organizations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # ─── Relationships ────────────────────────────────────────────────────────
    institution: Mapped["Institution | None"] = relationship(  # type: ignore[name-defined]
        "Institution",
        back_populates="members",
        foreign_keys=[institution_id],
    )
    industry_org: Mapped["IndustryOrganization | None"] = relationship(  # type: ignore[name-defined]
        "IndustryOrganization",
        back_populates="members",
        foreign_keys=[industry_org_id],
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email} role={self.role}>"
