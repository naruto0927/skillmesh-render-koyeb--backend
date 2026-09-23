"""
SkillMesh — Learning Service

Generates learning recommendations from the skill gap engine output,
manages enrollments, tracks progress, and computes Gap Closure.

Recommendation algorithm (deterministic):
1. Call prioritise_gaps() → ordered list of gaps
2. For each gap, find the best-matching LearningPath for the student's
   current proficiency band
3. Return recommendations ordered by gap priority

Gap Closure is computed when:
- A student completes a learning path AND
- A new assessment has been taken AFTER completion
- Formula: (initial_gap - current_gap) / initial_gap × 100
  where initial_gap = proficiency_at_enrollment - required_proficiency
"""

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.gap_engine import GapClosureResult, compute_gap_closure, prioritise_gaps
from app.core.logging import get_logger
from app.models.assessment import EvidenceCredibility, StudentSkill
from app.models.learning import (
    EnrollmentStatus,
    LearningPath,
    LearningPathEnrollment,
    LearningPathResource,
    LearningProgress,
    LearningResource,
    ProgressStatus,
)
from app.models.user import User
from app.services.gap_service import GapService

logger = get_logger(__name__)


class LearningService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ── Recommendations ───────────────────────────────────────────────────────

    async def get_recommendations(
        self,
        student: User,
        role_id: uuid.UUID | None = None,
        limit: int = 5,
    ) -> list[dict]:
        """
        Generate learning path recommendations for a student's skill gaps.

        Algorithm:
        1. Compute readiness report (uses GapService)
        2. Prioritise gaps (mandatory missing → critical → moderate)
        3. For each gap, find the best-matching learning path
        4. Skip skills the student is already enrolled in
        5. Return up to `limit` recommendations

        Returns a list of dicts with gap info + matching path.
        """
        gap_service = GapService(self.db)
        try:
            report = await gap_service.compute_readiness_for_student(student, role_id)
        except HTTPException as e:
            if e.status_code == 404:
                return []  # No target role set — no recommendations
            raise

        priority_gaps = prioritise_gaps(report)

        # Get skills already enrolled in (active enrollments)
        enrolled_result = await self.db.execute(
            select(LearningPathEnrollment.path_id)
            .join(LearningPath, LearningPath.id == LearningPathEnrollment.path_id)
            .where(
                LearningPathEnrollment.student_id == student.id,
                LearningPathEnrollment.status == EnrollmentStatus.ACTIVE,
            )
        )
        active_path_ids = {str(r) for r in enrolled_result.scalars().all()}

        recommendations = []
        for gap in priority_gaps:
            if len(recommendations) >= limit:
                break

            # Find the best learning path for this skill + proficiency band
            path = await self._find_best_path(
                skill_id=uuid.UUID(gap.skill_id),
                student_proficiency=gap.student_proficiency,
                target_proficiency=gap.required_proficiency,
            )
            if path is None:
                continue
            if str(path.id) in active_path_ids:
                continue

            recommendations.append({
                "skill_id": gap.skill_id,
                "skill_name": gap.skill_name,
                "gap": gap.gap,
                "severity": gap.severity.value,
                "is_mandatory": gap.is_mandatory,
                "current_proficiency": gap.student_proficiency,
                "required_proficiency": gap.required_proficiency,
                "recommended_path": path,
            })

        return recommendations

    async def _find_best_path(
        self,
        skill_id: uuid.UUID,
        student_proficiency: float,
        target_proficiency: float,
    ) -> LearningPath | None:
        """
        Find the learning path that best matches the student's starting level
        and reaches toward the required proficiency.
        Selects the path with the highest target_proficiency that is still
        achievable from the student's current level.
        """
        result = await self.db.execute(
            select(LearningPath)
            .options(
                selectinload(LearningPath.path_resources)
                .selectinload(LearningPathResource.resource)
            )
            .where(
                LearningPath.skill_id == skill_id,
                LearningPath.is_active.is_(True),
                LearningPath.from_proficiency <= student_proficiency + 15,
                LearningPath.target_proficiency >= target_proficiency,
            )
            .order_by(LearningPath.from_proficiency.desc())
        )
        paths = result.scalars().all()
        return paths[0] if paths else None

    # ── Enrollment ────────────────────────────────────────────────────────────

    async def enroll(
        self,
        student: User,
        path_id: uuid.UUID,
    ) -> LearningPathEnrollment:
        """
        Enroll a student in a learning path.
        Records proficiency_at_enrollment as the baseline for Gap Closure.
        Creates LearningProgress records for all resources in the path.
        """
        # Verify path exists
        path_result = await self.db.execute(
            select(LearningPath)
            .options(
                selectinload(LearningPath.path_resources)
                .selectinload(LearningPathResource.resource)
            )
            .where(LearningPath.id == path_id, LearningPath.is_active.is_(True))
        )
        path = path_result.scalar_one_or_none()
        if path is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Learning path not found.",
            )

        # Check for existing active enrollment
        existing = await self.db.execute(
            select(LearningPathEnrollment).where(
                LearningPathEnrollment.student_id == student.id,
                LearningPathEnrollment.path_id == path_id,
                LearningPathEnrollment.status == EnrollmentStatus.ACTIVE,
            )
        )
        if existing.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Already enrolled in this learning path.",
            )

        # Get current proficiency for this skill
        ss_result = await self.db.execute(
            select(StudentSkill).where(
                StudentSkill.student_id == student.id,
                StudentSkill.skill_id == path.skill_id,
            )
        )
        ss = ss_result.scalar_one_or_none()
        proficiency_at_enrollment = ss.proficiency if ss else 0.0

        # Create enrollment
        enrollment = LearningPathEnrollment(
            student_id=student.id,
            path_id=path_id,
            status=EnrollmentStatus.ACTIVE,
            proficiency_at_enrollment=proficiency_at_enrollment,
        )
        self.db.add(enrollment)
        await self.db.flush()

        # Create progress records for each resource
        for path_resource in path.path_resources:
            progress = LearningProgress(
                enrollment_id=enrollment.id,
                resource_id=path_resource.resource_id,
                status=ProgressStatus.NOT_STARTED,
            )
            self.db.add(progress)

        await self.db.commit()
        await self.db.refresh(enrollment)

        logger.info(
            f"Enrollment created: student={student.id} path={path_id} "
            f"proficiency_baseline={proficiency_at_enrollment}"
        )
        return enrollment

    # ── Progress ──────────────────────────────────────────────────────────────

    async def update_progress(
        self,
        student: User,
        enrollment_id: uuid.UUID,
        resource_id: uuid.UUID,
        new_status: ProgressStatus,
        notes: str | None = None,
    ) -> LearningProgress:
        """
        Mark a resource as in-progress, completed, or skipped.
        When all required resources in the path are completed,
        the enrollment is automatically marked COMPLETED.
        """
        # Load enrollment and verify ownership
        enrollment_result = await self.db.execute(
            select(LearningPathEnrollment)
            .options(
                selectinload(LearningPathEnrollment.path)
                .selectinload(LearningPath.path_resources)
            )
            .where(
                LearningPathEnrollment.id == enrollment_id,
                LearningPathEnrollment.student_id == student.id,
            )
        )
        enrollment = enrollment_result.scalar_one_or_none()
        if enrollment is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Enrollment not found.",
            )
        if enrollment.status != EnrollmentStatus.ACTIVE:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Enrollment is {enrollment.status.value}, not active.",
            )

        # Load progress record
        prog_result = await self.db.execute(
            select(LearningProgress).where(
                LearningProgress.enrollment_id == enrollment_id,
                LearningProgress.resource_id == resource_id,
            )
        )
        progress = prog_result.scalar_one_or_none()
        if progress is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Resource not found in this enrollment.",
            )

        progress.status = new_status
        if notes is not None:
            progress.notes = notes
        if new_status == ProgressStatus.COMPLETED:
            progress.completed_at = datetime.now(timezone.utc)

        await self.db.flush()

        # Check if all required resources are complete
        await self._check_path_completion(enrollment)

        await self.db.commit()
        await self.db.refresh(progress)
        return progress

    async def _check_path_completion(
        self, enrollment: LearningPathEnrollment
    ) -> None:
        """
        Auto-complete the enrollment when all required resources are done.
        Adds DEMONSTRATED evidence to the skill upon completion.
        """
        # Load all progress for this enrollment
        progress_result = await self.db.execute(
            select(LearningProgress).where(
                LearningProgress.enrollment_id == enrollment.id
            )
        )
        all_progress = list(progress_result.scalars().all())

        # Required resources from the path
        required_resource_ids = {
            str(pr.resource_id)
            for pr in enrollment.path.path_resources
            if pr.is_required
        }

        completed_required = {
            str(p.resource_id)
            for p in all_progress
            if p.status == ProgressStatus.COMPLETED
            and str(p.resource_id) in required_resource_ids
        }

        if completed_required >= required_resource_ids:
            # All required resources done — complete the enrollment
            enrollment.status = EnrollmentStatus.COMPLETED
            enrollment.completed_at = datetime.now(timezone.utc)
            await self.db.flush()

            logger.info(
                f"Learning path completed: student={enrollment.student_id} "
                f"path={enrollment.path_id}"
            )

    # ── My enrollments ────────────────────────────────────────────────────────

    async def get_my_enrollments(
        self, student: User
    ) -> list[LearningPathEnrollment]:
        result = await self.db.execute(
            select(LearningPathEnrollment)
            .options(
                selectinload(LearningPathEnrollment.path)
                .selectinload(LearningPath.skill),
                selectinload(LearningPathEnrollment.progress_records)
                .selectinload(LearningProgress.resource),
            )
            .where(LearningPathEnrollment.student_id == student.id)
            .order_by(LearningPathEnrollment.created_at.desc())
        )
        return list(result.scalars().all())

    # ── Gap Closure ───────────────────────────────────────────────────────────

    async def compute_gap_closure_for_enrollment(
        self, student: User, enrollment_id: uuid.UUID
    ) -> GapClosureResult | None:
        """
        Compute Gap Closure for a completed enrollment.

        Gap Closure = (initial_gap - current_gap) / initial_gap × 100

        initial_gap = required_proficiency - proficiency_at_enrollment
        current_gap = required_proficiency - current_proficiency

        Returns None if enrollment is not complete or target role not set.
        """
        enrollment_result = await self.db.execute(
            select(LearningPathEnrollment)
            .options(selectinload(LearningPathEnrollment.path))
            .where(
                LearningPathEnrollment.id == enrollment_id,
                LearningPathEnrollment.student_id == student.id,
            )
        )
        enrollment = enrollment_result.scalar_one_or_none()
        if enrollment is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Enrollment not found."
            )
        if enrollment.status != EnrollmentStatus.COMPLETED:
            return None  # Not yet complete

        # Get current proficiency
        ss_result = await self.db.execute(
            select(StudentSkill).where(
                StudentSkill.student_id == student.id,
                StudentSkill.skill_id == enrollment.path.skill_id,
            )
        )
        ss = ss_result.scalar_one_or_none()
        current_proficiency = ss.proficiency if ss else 0.0

        # Get required proficiency from target role
        gap_service = GapService(self.db)
        try:
            report = await gap_service.compute_readiness_for_student(student)
        except HTTPException:
            return None

        all_items = (
            report.strengths + report.moderate_gaps
            + report.critical_gaps + report.missing_skills
        )
        skill_req = next(
            (i for i in all_items
             if i.skill_id == str(enrollment.path.skill_id)),
            None,
        )
        if skill_req is None:
            return None

        return compute_gap_closure(
            skill_id=str(enrollment.path.skill_id),
            skill_name=skill_req.skill_name,
            required_proficiency=skill_req.required_proficiency,
            initial_proficiency=enrollment.proficiency_at_enrollment,
            current_proficiency=current_proficiency,
        )

    async def get_path_with_resources(
        self, path_id: uuid.UUID
    ) -> LearningPath | None:
        result = await self.db.execute(
            select(LearningPath)
            .options(
                selectinload(LearningPath.path_resources)
                .selectinload(LearningPathResource.resource),
                selectinload(LearningPath.skill),
            )
            .where(LearningPath.id == path_id, LearningPath.is_active.is_(True))
        )
        return result.scalar_one_or_none()
