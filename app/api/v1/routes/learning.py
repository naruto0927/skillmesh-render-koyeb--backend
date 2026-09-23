"""
SkillMesh — Learning Schemas & Routes

GET  /api/v1/learning/recommendations        — gap-driven path recommendations
GET  /api/v1/learning/paths/{skill_id}        — all paths for a skill
GET  /api/v1/learning/paths/detail/{path_id} — path with resources
POST /api/v1/learning/enroll                  — enroll in a path
GET  /api/v1/learning/enrollments             — my enrollments
PATCH /api/v1/learning/enrollments/{id}/progress — mark resource progress
GET  /api/v1/learning/enrollments/{id}/closure   — gap closure metric
"""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.security import CurrentUser
from app.models.learning import (
    EnrollmentStatus,
    LearningPath,
    LearningPathEnrollment,
    LearningPathResource,
    LearningProgress,
    LearningResource,
    ProgressStatus,
    ResourceDifficulty,
    ResourceType,
)
from app.models.user import UserRole
from app.services.learning_service import LearningService

router = APIRouter(tags=["Learning"])


# ─── Schemas ──────────────────────────────────────────────────────────────────

class LearningResourcePublic(BaseModel):
    id: uuid.UUID
    skill_id: uuid.UUID
    title: str
    description: str | None
    resource_type: ResourceType
    difficulty: ResourceDifficulty
    url: str | None
    provider: str | None
    estimated_minutes: int | None
    is_free: bool
    expected_proficiency_gain: float

    model_config = {"from_attributes": True}


class LearningPathResourcePublic(BaseModel):
    order_index: int
    is_required: bool
    resource: LearningResourcePublic

    model_config = {"from_attributes": True}


class LearningPathPublic(BaseModel):
    id: uuid.UUID
    skill_id: uuid.UUID
    skill_name: str
    title: str
    description: str | None
    target_proficiency: float
    from_proficiency: float
    total_estimated_minutes: int
    resource_count: int

    model_config = {"from_attributes": True}


class LearningPathDetail(LearningPathPublic):
    resources: list[LearningPathResourcePublic]


class RecommendationItem(BaseModel):
    skill_id: str
    skill_name: str
    gap: float
    severity: str
    is_mandatory: bool
    current_proficiency: float
    required_proficiency: float
    recommended_path: LearningPathPublic


class EnrollRequest(BaseModel):
    path_id: uuid.UUID


class ProgressUpdateRequest(BaseModel):
    resource_id: uuid.UUID
    status: ProgressStatus
    notes: str | None = Field(default=None, max_length=500)


class ProgressItemPublic(BaseModel):
    resource_id: uuid.UUID
    resource_title: str
    resource_type: ResourceType
    status: ProgressStatus
    completed_at: datetime | None
    order_index: int

    model_config = {"from_attributes": True}


class EnrollmentPublic(BaseModel):
    id: uuid.UUID
    path_id: uuid.UUID
    path_title: str
    skill_name: str
    status: EnrollmentStatus
    proficiency_at_enrollment: float
    completed_at: datetime | None
    created_at: datetime
    resources_total: int
    resources_completed: int
    completion_pct: float
    progress: list[ProgressItemPublic]

    model_config = {"from_attributes": True}


class GapClosurePublic(BaseModel):
    skill_id: str
    skill_name: str
    initial_gap: float
    current_gap: float
    gap_closure_pct: float
    initial_proficiency: float
    current_proficiency: float
    required_proficiency: float


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _path_to_public(path: LearningPath) -> LearningPathPublic:
    return LearningPathPublic(
        id=path.id,
        skill_id=path.skill_id,
        skill_name=path.skill.canonical_name if path.skill else "",
        title=path.title,
        description=path.description,
        target_proficiency=path.target_proficiency,
        from_proficiency=path.from_proficiency,
        total_estimated_minutes=path.total_estimated_minutes,
        resource_count=len(path.path_resources),
    )


def _enrollment_to_public(enrollment: LearningPathEnrollment) -> EnrollmentPublic:
    path = enrollment.path
    skill_name = path.skill.canonical_name if path and path.skill else ""
    path_title = path.title if path else ""

    # Build progress items
    # Build order map from path resources
    order_map: dict[str, int] = {}
    if path and path.path_resources:
        for pr in path.path_resources:
            order_map[str(pr.resource_id)] = pr.order_index

    progress_items = []
    for prog in sorted(
        enrollment.progress_records,
        key=lambda p: order_map.get(str(p.resource_id), 0),
    ):
        res = prog.resource
        if res:
            progress_items.append(ProgressItemPublic(
                resource_id=prog.resource_id,
                resource_title=res.title,
                resource_type=res.resource_type,
                status=prog.status,
                completed_at=prog.completed_at,
                order_index=order_map.get(str(prog.resource_id), 0),
            ))

    completed = sum(
        1 for p in enrollment.progress_records
        if p.status == ProgressStatus.COMPLETED
    )
    total = len(enrollment.progress_records)
    completion_pct = round((completed / total * 100), 1) if total > 0 else 0.0

    return EnrollmentPublic(
        id=enrollment.id,
        path_id=enrollment.path_id,
        path_title=path_title,
        skill_name=skill_name,
        status=enrollment.status,
        proficiency_at_enrollment=enrollment.proficiency_at_enrollment,
        completed_at=enrollment.completed_at,
        created_at=enrollment.created_at,
        resources_total=total,
        resources_completed=completed,
        completion_pct=completion_pct,
        progress=progress_items,
    )


# ─── Routes ───────────────────────────────────────────────────────────────────

@router.get("/learning/recommendations", response_model=list[RecommendationItem])
async def get_recommendations(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> list[RecommendationItem]:
    """
    Get gap-driven learning path recommendations.
    Ordered by gap priority: mandatory missing → critical → moderate.
    Skips skills already actively enrolled in.
    """
    if current_user.role != UserRole.STUDENT:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only students receive learning recommendations.",
        )
    service = LearningService(db)
    recs = await service.get_recommendations(current_user)
    return [
        RecommendationItem(
            skill_id=r["skill_id"],
            skill_name=r["skill_name"],
            gap=r["gap"],
            severity=r["severity"],
            is_mandatory=r["is_mandatory"],
            current_proficiency=r["current_proficiency"],
            required_proficiency=r["required_proficiency"],
            recommended_path=_path_to_public(r["recommended_path"]),
        )
        for r in recs
    ]


@router.get("/learning/paths/{skill_id}", response_model=list[LearningPathPublic])
async def get_paths_for_skill(
    skill_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> list[LearningPathPublic]:
    """List all active learning paths for a specific skill."""
    result = await db.execute(
        select(LearningPath)
        .options(
            selectinload(LearningPath.skill),
            selectinload(LearningPath.path_resources),
        )
        .where(LearningPath.skill_id == skill_id, LearningPath.is_active.is_(True))
        .order_by(LearningPath.from_proficiency.asc())
    )
    return [_path_to_public(p) for p in result.scalars().all()]


@router.get("/learning/paths/detail/{path_id}", response_model=LearningPathDetail)
async def get_path_detail(
    path_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> LearningPathDetail:
    """Get a learning path with all its resources."""
    service = LearningService(db)
    path = await service.get_path_with_resources(path_id)
    if path is None:
        raise HTTPException(status_code=404, detail="Learning path not found.")

    return LearningPathDetail(
        id=path.id,
        skill_id=path.skill_id,
        skill_name=path.skill.canonical_name if path.skill else "",
        title=path.title,
        description=path.description,
        target_proficiency=path.target_proficiency,
        from_proficiency=path.from_proficiency,
        total_estimated_minutes=path.total_estimated_minutes,
        resource_count=len(path.path_resources),
        resources=[
            LearningPathResourcePublic(
                order_index=pr.order_index,
                is_required=pr.is_required,
                resource=LearningResourcePublic.model_validate(pr.resource),
            )
            for pr in sorted(path.path_resources, key=lambda x: x.order_index)
        ],
    )


@router.post("/learning/enroll", response_model=EnrollmentPublic, status_code=201)
async def enroll_in_path(
    body: EnrollRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> EnrollmentPublic:
    """Enroll the current student in a learning path."""
    if current_user.role != UserRole.STUDENT:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only students can enroll in learning paths.",
        )
    service = LearningService(db)
    enrollment = await service.enroll(current_user, body.path_id)

    # Reload with relationships
    result = await db.execute(
        select(LearningPathEnrollment)
        .options(
            selectinload(LearningPathEnrollment.path)
            .selectinload(LearningPath.skill),
            selectinload(LearningPathEnrollment.path)
            .selectinload(LearningPath.path_resources),
            selectinload(LearningPathEnrollment.progress_records)
            .selectinload(LearningProgress.resource),
        )
        .where(LearningPathEnrollment.id == enrollment.id)
    )
    enrollment = result.scalar_one()
    return _enrollment_to_public(enrollment)


@router.get("/learning/enrollments", response_model=list[EnrollmentPublic])
async def get_my_enrollments(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> list[EnrollmentPublic]:
    """Get all enrollments for the current student."""
    service = LearningService(db)
    enrollments = await service.get_my_enrollments(current_user)
    return [_enrollment_to_public(e) for e in enrollments]


@router.patch(
    "/learning/enrollments/{enrollment_id}/progress",
    response_model=ProgressItemPublic,
)
async def update_progress(
    enrollment_id: uuid.UUID,
    body: ProgressUpdateRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> ProgressItemPublic:
    """Mark a resource as in-progress, completed, or skipped."""
    service = LearningService(db)
    progress = await service.update_progress(
        student=current_user,
        enrollment_id=enrollment_id,
        resource_id=body.resource_id,
        new_status=body.status,
        notes=body.notes,
    )
    res = progress.resource
    return ProgressItemPublic(
        resource_id=progress.resource_id,
        resource_title=res.title if res else "",
        resource_type=res.resource_type if res else ResourceType.TUTORIAL,
        status=progress.status,
        completed_at=progress.completed_at,
        order_index=0,
    )


@router.get(
    "/learning/enrollments/{enrollment_id}/closure",
    response_model=GapClosurePublic | None,
)
async def get_gap_closure(
    enrollment_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> GapClosurePublic | None:
    """
    Compute Gap Closure for a completed enrollment.
    Returns null if the enrollment is not yet complete.

    Gap Closure = (initial_gap - current_gap) / initial_gap × 100

    This is the signature metric from project spec section 55.
    """
    service = LearningService(db)
    result = await service.compute_gap_closure_for_enrollment(
        current_user, enrollment_id
    )
    if result is None:
        return None
    return GapClosurePublic(
        skill_id=result.skill_id,
        skill_name=result.skill_name,
        initial_gap=result.initial_gap,
        current_gap=result.current_gap,
        gap_closure_pct=result.gap_closure_pct,
        initial_proficiency=result.initial_proficiency,
        current_proficiency=result.current_proficiency,
        required_proficiency=result.required_proficiency,
    )
