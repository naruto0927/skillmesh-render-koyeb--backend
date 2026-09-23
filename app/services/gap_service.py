"""
SkillMesh — Gap Service

Orchestrates:
1. Setting a student's target role
2. Loading requirements + student skills from the DB
3. Running the gap engine
4. Returning the ReadinessReport
"""

import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.gap_engine import (
    ReadinessReport,
    SkillRequirementInput,
    compute_readiness,
    prioritise_gaps,
)
from app.core.logging import get_logger
from app.models.assessment import StudentSkill
from app.models.gap import StudentTargetRole
from app.models.role import RoleRequirement, RolesCatalog
from app.models.user import User

logger = get_logger(__name__)


class GapService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def set_target_role(
        self,
        student: User,
        role_id: uuid.UUID,
        notes: str | None = None,
    ) -> StudentTargetRole:
        """
        Set the student's active target role.
        Deactivates any previous active target role.
        """
        # Verify role exists and is active
        role_result = await self.db.execute(
            select(RolesCatalog).where(
                RolesCatalog.id == role_id,
                RolesCatalog.is_active.is_(True),
            )
        )
        role = role_result.scalar_one_or_none()
        if role is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Role not found or inactive.",
            )

        # Deactivate existing active targets
        existing_result = await self.db.execute(
            select(StudentTargetRole).where(
                StudentTargetRole.student_id == student.id,
                StudentTargetRole.is_active.is_(True),
            )
        )
        for existing in existing_result.scalars().all():
            existing.is_active = False

        # Create new target
        target = StudentTargetRole(
            student_id=student.id,
            role_id=role_id,
            is_active=True,
            notes=notes,
        )
        self.db.add(target)
        await self.db.commit()
        await self.db.refresh(target)

        logger.info(
            f"Target role set: student={student.id} role={role.name}"
        )
        return target

    async def get_active_target_role(
        self, student_id: uuid.UUID
    ) -> StudentTargetRole | None:
        result = await self.db.execute(
            select(StudentTargetRole)
            .options(selectinload(StudentTargetRole.role))
            .where(
                StudentTargetRole.student_id == student_id,
                StudentTargetRole.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def compute_readiness_for_student(
        self,
        student: User,
        role_id: uuid.UUID | None = None,
    ) -> ReadinessReport:
        """
        Compute the full readiness report for a student against a role.

        If role_id is None, uses the student's active target role.
        Raises 404 if no role is specified and no active target exists.
        """
        if role_id is None:
            target = await self.get_active_target_role(student.id)
            if target is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="No target role set. Select a target role first.",
                )
            role_id = target.role_id

        # Load role with requirements
        role_result = await self.db.execute(
            select(RolesCatalog)
            .options(
                selectinload(RolesCatalog.requirements)
                .selectinload(RoleRequirement.skill)
            )
            .where(RolesCatalog.id == role_id, RolesCatalog.is_active.is_(True))
        )
        role = role_result.scalar_one_or_none()
        if role is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Role not found.",
            )

        # Load student's skill scores
        ss_result = await self.db.execute(
            select(StudentSkill).where(StudentSkill.student_id == student.id)
        )
        student_skills: dict[str, float] = {
            str(ss.skill_id): ss.proficiency
            for ss in ss_result.scalars().all()
        }

        # Build requirement inputs
        requirements = [
            SkillRequirementInput(
                skill_id=str(req.skill_id),
                skill_name=req.skill.canonical_name,
                required_proficiency=float(req.required_proficiency),
                is_mandatory=req.is_mandatory,
                student_proficiency=student_skills.get(str(req.skill_id)),
            )
            for req in sorted(role.requirements, key=lambda r: r.display_order)
        ]

        report = compute_readiness(
            role_id=str(role.id),
            role_name=role.name,
            requirements=requirements,
        )

        logger.info(
            f"Readiness computed: student={student.id} role={role.name} "
            f"score={report.readiness_score}"
        )
        return report

    async def get_prioritised_gaps(
        self, student: User, role_id: uuid.UUID | None = None
    ) -> list:
        """Return gaps ordered by learning priority."""
        report = await self.compute_readiness_for_student(student, role_id)
        return prioritise_gaps(report)
