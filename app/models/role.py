"""
SkillMesh — Roles Catalog & Role Requirements

RolesCatalog: industry role definitions (Backend Developer, Data Engineer, etc.)
RoleRequirement: which skills a role needs, at what proficiency level, and
                 whether they are required or preferred.

These models power the Skill Gap Engine in Phase 4.
The required_proficiency values here are compared against student proficiency
scores to compute readiness scores and identify gaps.
"""

import uuid

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel
from app.models.skill import RelationshipType


class RolesCatalog(BaseModel):
    """
    Industry role definition.
    E.g. Backend Developer, Data Engineer, ML Engineer, Full Stack Developer.

    Roles are curated — not auto-generated. SUPER_ADMIN manages the catalog.
    Industry partners can request additions.
    """

    __tablename__ = "roles_catalog"

    name: Mapped[str] = mapped_column(String(150), nullable=False, unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Industry sector this role is typically found in
    industry_sector: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # Experience level: entry, mid, senior
    experience_level: Mapped[str] = mapped_column(
        String(20), nullable=False, default="entry"
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # ── Relationships ──────────────────────────────────────────────────────────
    requirements: Mapped[list["RoleRequirement"]] = relationship(
        "RoleRequirement", back_populates="role", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<RolesCatalog id={self.id} name={self.name}>"


class RoleRequirement(BaseModel):
    """
    A specific skill requirement for a role.

    required_proficiency: minimum score (0–100) a student needs to PASS this requirement.
    is_mandatory: if True, this skill is a hard requirement — gap here is always critical.
    relationship_type: mirrors SkillRelationship — REQUIRED or PREFERRED.

    Example (Backend Developer):
      Python          required_proficiency=80  is_mandatory=True   REQUIRED
      SQL             required_proficiency=75  is_mandatory=True   REQUIRED
      REST API        required_proficiency=75  is_mandatory=True   REQUIRED
      Docker          required_proficiency=65  is_mandatory=False  PREFERRED
      AWS             required_proficiency=60  is_mandatory=False  PREFERRED
    """

    __tablename__ = "role_requirements"

    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("roles_catalog.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    skill_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("skills.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    required_proficiency: Mapped[int] = mapped_column(
        Integer, nullable=False, default=70
    )
    is_mandatory: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    relationship_type: Mapped[RelationshipType] = mapped_column(
        # Reuse the enum — REQUIRED or PREFERRED
        String(20), nullable=False, default="required"
    )
    # Display order within the role's requirement list
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # ── Relationships ──────────────────────────────────────────────────────────
    role: Mapped["RolesCatalog"] = relationship(
        "RolesCatalog", back_populates="requirements"
    )
    skill: Mapped["Skill"] = relationship("Skill")  # type: ignore[name-defined]

    def __repr__(self) -> str:
        return (
            f"<RoleRequirement role_id={self.role_id} skill_id={self.skill_id} "
            f"required={self.required_proficiency}>"
        )
