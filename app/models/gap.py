"""
SkillMesh — Student Target Role Model

A student selects a target role from the RolesCatalog.
The Skill Gap Engine compares the student's current proficiency
against that role's RoleRequirements to produce the readiness report.

A student can have only one active target role at a time.
Previous selections are preserved for history/analytics.
"""

import uuid

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class StudentTargetRole(BaseModel):
    """
    A student's selected target career role.

    is_active: only one record per student should be active at any time.
    Previous targets are kept (is_active=False) for analytics.
    """

    __tablename__ = "student_target_roles"

    student_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("roles_catalog.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Free-text notes from student (e.g. "I want to specialise in ML backends")
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # ── Relationships ──────────────────────────────────────────────────────────
    student: Mapped["User"] = relationship("User")  # type: ignore[name-defined]
    role: Mapped["RolesCatalog"] = relationship("RolesCatalog")  # type: ignore[name-defined]

    def __repr__(self) -> str:
        return (
            f"<StudentTargetRole student={self.student_id} "
            f"role={self.role_id} active={self.is_active}>"
        )
