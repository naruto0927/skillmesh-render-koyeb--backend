"""
SkillMesh — Gap Engine Routes

POST /api/v1/gap/target-role          — set student's target role
GET  /api/v1/gap/target-role          — get active target role
GET  /api/v1/gap/readiness            — full readiness report (active target)
GET  /api/v1/gap/readiness/{role_id}  — readiness against a specific role
GET  /api/v1/gap/priorities           — ordered list of gaps to close
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.gap_engine import GapSeverity, prioritise_gaps
from app.core.security import CurrentUser
from app.models.user import UserRole
from app.schemas.gap import (
    GapClosureResponse,
    ReadinessReportResponse,
    SetTargetRoleRequest,
    SkillGapItemResponse,
    TargetRoleResponse,
)
from app.services.gap_service import GapService

router = APIRouter(tags=["Skill Gap"])


def _to_skill_gap_response(item) -> SkillGapItemResponse:
    return SkillGapItemResponse(
        skill_id=item.skill_id,
        skill_name=item.skill_name,
        required_proficiency=item.required_proficiency,
        student_proficiency=item.student_proficiency,
        gap=item.gap,
        severity=item.severity,
        is_mandatory=item.is_mandatory,
        skill_score=item.skill_score,
    )


def _build_readiness_response(report, priority_gaps) -> ReadinessReportResponse:
    return ReadinessReportResponse(
        role_id=report.role_id,
        role_name=report.role_name,
        readiness_score=report.readiness_score,
        readiness_label=report.readiness_label,
        strengths=[_to_skill_gap_response(i) for i in report.strengths],
        moderate_gaps=[_to_skill_gap_response(i) for i in report.moderate_gaps],
        critical_gaps=[_to_skill_gap_response(i) for i in report.critical_gaps],
        missing_skills=[_to_skill_gap_response(i) for i in report.missing_skills],
        total_requirements=report.total_requirements,
        passed_requirements=report.passed_requirements,
        mandatory_gaps=report.mandatory_gaps,
        has_critical_gaps=bool(report.critical_gaps or report.missing_skills),
        priority_gaps=[_to_skill_gap_response(i) for i in priority_gaps[:3]],
    )


@router.post("/gap/target-role", response_model=TargetRoleResponse, status_code=201)
async def set_target_role(
    body: SetTargetRoleRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> TargetRoleResponse:
    """Set the student's target career role."""
    if current_user.role != UserRole.STUDENT:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only students can set a target role.",
        )
    service = GapService(db)
    target = await service.set_target_role(
        student=current_user,
        role_id=body.role_id,
        notes=body.notes,
    )
    return TargetRoleResponse(
        id=target.id,
        student_id=target.student_id,
        role_id=target.role_id,
        role_name=target.role.name if target.role else "",
        is_active=target.is_active,
        notes=target.notes,
        created_at=target.created_at,
    )


@router.get("/gap/target-role", response_model=TargetRoleResponse | None)
async def get_target_role(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> TargetRoleResponse | None:
    """Get the student's active target role."""
    service = GapService(db)
    target = await service.get_active_target_role(current_user.id)
    if target is None:
        return None
    return TargetRoleResponse(
        id=target.id,
        student_id=target.student_id,
        role_id=target.role_id,
        role_name=target.role.name if target.role else "",
        is_active=target.is_active,
        notes=target.notes,
        created_at=target.created_at,
    )


@router.get("/gap/readiness", response_model=ReadinessReportResponse)
async def get_readiness(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> ReadinessReportResponse:
    """
    Get the full readiness report against the student's active target role.
    This is the main Skill Gap dashboard endpoint.
    """
    service = GapService(db)
    report = await service.compute_readiness_for_student(current_user)
    priorities = prioritise_gaps(report)
    return _build_readiness_response(report, priorities)


@router.get("/gap/readiness/{role_id}", response_model=ReadinessReportResponse)
async def get_readiness_for_role(
    role_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> ReadinessReportResponse:
    """Get readiness against a specific role (for exploration before committing)."""
    service = GapService(db)
    report = await service.compute_readiness_for_student(current_user, role_id)
    priorities = prioritise_gaps(report)
    return _build_readiness_response(report, priorities)


@router.get("/gap/priorities", response_model=list[SkillGapItemResponse])
async def get_gap_priorities(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> list[SkillGapItemResponse]:
    """
    Get the student's gaps in learning priority order.
    Used by the Learning Engine (Phase 5) to generate recommendations.
    Mandatory gaps first, then by severity and gap size.
    """
    service = GapService(db)
    gaps = await service.get_prioritised_gaps(current_user)
    return [_to_skill_gap_response(g) for g in gaps]
