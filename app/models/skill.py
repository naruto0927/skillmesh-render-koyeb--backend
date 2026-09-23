"""
SkillMesh — Skill & Competency Graph Models

Design decisions:
- Skill is the top-level entity (Python, SQL, Docker, AWS)
- Competency is a specific sub-skill within a Skill (Python → OOP, Data Handling)
- SkillRelationship encodes directed edges in the skill graph
- Skills use a controlled taxonomy — AI must not add skills silently

Relationship types mirror Section 10 of the project spec:
  required     — role depends on this skill
  preferred    — role benefits from this skill
  related      — skills are used together but neither requires the other
  prerequisite — must know A before learning B
  equivalent   — two names for the same concept (normalisation target)
"""

import enum
import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class SkillCategory(str, enum.Enum):
    TECHNICAL = "technical"
    SOFT_SKILL = "soft_skill"
    DOMAIN = "domain"
    TOOL = "tool"
    LANGUAGE = "language"
    FRAMEWORK = "framework"
    CLOUD = "cloud"
    DATABASE = "database"
    OTHER = "other"


class SkillStatus(str, enum.Enum):
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    PENDING_REVIEW = "pending_review"


class RelationshipType(str, enum.Enum):
    REQUIRED = "required"
    PREFERRED = "preferred"
    RELATED = "related"
    PREREQUISITE = "prerequisite"
    EQUIVALENT = "equivalent"


class ProficiencyLevel(str, enum.Enum):
    """Named proficiency bands — maps to numeric ranges."""
    BEGINNER = "beginner"       # 0–39
    ELEMENTARY = "elementary"   # 40–59
    INTERMEDIATE = "intermediate"  # 60–74
    ADVANCED = "advanced"       # 75–89
    EXPERT = "expert"           # 90–100


class Skill(BaseModel):
    """
    Canonical skill entity.
    Represents a single, well-defined skill in the taxonomy.
    E.g. Python, SQL, Docker, React, Communication.

    New skills must be added by SUPER_ADMIN or via seeding —
    never auto-created by AI.
    """

    __tablename__ = "skills"

    canonical_name: Mapped[str] = mapped_column(
        String(100), nullable=False, unique=True, index=True
    )
    category: Mapped[SkillCategory] = mapped_column(
        Enum(SkillCategory, name="skill_category", create_type=True),
        nullable=False,
        default=SkillCategory.OTHER,
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[SkillStatus] = mapped_column(
        Enum(SkillStatus, name="skill_status", create_type=True),
        nullable=False,
        default=SkillStatus.ACTIVE,
        index=True,
    )
    # Icon name for UI display (e.g. "python", "aws")
    icon_key: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # Common aliases used in normalisation (comma-separated, e.g. "Python3,py")
    aliases: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Relationships ──────────────────────────────────────────────────────────
    competencies: Mapped[list["Competency"]] = relationship(
        "Competency", back_populates="skill", cascade="all, delete-orphan"
    )
    outgoing_relationships: Mapped[list["SkillRelationship"]] = relationship(
        "SkillRelationship",
        foreign_keys="SkillRelationship.from_skill_id",
        back_populates="from_skill",
        cascade="all, delete-orphan",
    )
    incoming_relationships: Mapped[list["SkillRelationship"]] = relationship(
        "SkillRelationship",
        foreign_keys="SkillRelationship.to_skill_id",
        back_populates="to_skill",
    )
    student_skills: Mapped[list["StudentSkill"]] = relationship(
        "StudentSkill", back_populates="skill"
    )
    assessment_questions: Mapped[list["AssessmentQuestion"]] = relationship(
        "AssessmentQuestion", back_populates="skill"
    )

    def __repr__(self) -> str:
        return f"<Skill id={self.id} name={self.canonical_name}>"


class Competency(BaseModel):
    """
    A specific, assessable sub-skill within a Skill.
    E.g. Python → OOP, Python → Async Programming

    Competencies are what the assessment engine actually tests.
    Proficiency at the skill level is aggregated from competency scores.
    """

    __tablename__ = "competencies"
    __table_args__ = (
        UniqueConstraint("skill_id", "name", name="uq_competency_skill_name"),
    )

    skill_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("skills.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Relative importance weight within the parent skill (0.0–1.0)
    # All competencies within a skill should sum to ~1.0
    weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    # Ordered position for display
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # ── Relationships ──────────────────────────────────────────────────────────
    skill: Mapped["Skill"] = relationship("Skill", back_populates="competencies")
    assessment_questions: Mapped[list["AssessmentQuestion"]] = relationship(
        "AssessmentQuestion", back_populates="competency"
    )

    def __repr__(self) -> str:
        return f"<Competency id={self.id} name={self.name} skill_id={self.skill_id}>"


class SkillRelationship(BaseModel):
    """
    Directed edge in the skill graph.
    from_skill → relationship_type → to_skill

    Example:
      Backend Developer REQUIRES Python
      Python PREREQUISITE Programming Fundamentals
      React RELATED TypeScript
    """

    __tablename__ = "skill_relationships"
    __table_args__ = (
        UniqueConstraint(
            "from_skill_id", "to_skill_id", "relationship_type",
            name="uq_skill_relationship"
        ),
    )

    from_skill_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("skills.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    to_skill_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("skills.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    relationship_type: Mapped[RelationshipType] = mapped_column(
        Enum(RelationshipType, name="relationship_type", create_type=True),
        nullable=False,
    )
    # Strength of the relationship (0.0–1.0) — used in recommendation weighting
    strength: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=1.0,
    )

    from_skill: Mapped["Skill"] = relationship(
        "Skill", foreign_keys=[from_skill_id], back_populates="outgoing_relationships"
    )
    to_skill: Mapped["Skill"] = relationship(
        "Skill", foreign_keys=[to_skill_id], back_populates="incoming_relationships"
    )
