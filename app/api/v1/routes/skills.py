"""
SkillMesh — Skills Routes

GET  /api/v1/skills                    — list active skills
GET  /api/v1/skills/{skill_id}         — get skill with competencies
GET  /api/v1/skills/{skill_id}/relationships — skill graph edges
GET  /api/v1/roles                     — list roles catalog
GET  /api/v1/roles/{role_id}           — role with requirements
GET  /api/v1/students/me/skills        — current student's skill profile
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.scoring import get_proficiency_level
from app.core.security import CurrentUser, StudentUser
from app.models.assessment import EvidenceCredibility, StudentSkill
from app.models.role import RoleRequirement, RolesCatalog
from app.models.skill import Skill, SkillRelationship, SkillStatus
from app.models.user import UserRole
from app.schemas.skill import (
    RolePublic,
    RoleRequirementPublic,
    RoleSummary,
    SkillPublic,
    SkillRelationshipPublic,
    SkillSummary,
    StudentSkillProfile,
    StudentSkillPublic,
)

router = APIRouter(tags=["Skills"])


@router.get("/skills", response_model=list[SkillSummary])
async def list_skills(
    category: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> list[SkillSummary]:
    """List all active skills. Optional category filter."""
    query = select(Skill).where(Skill.status == SkillStatus.ACTIVE)
    if category:
        query = query.where(Skill.category == category)
    query = query.order_by(Skill.canonical_name)

    result = await db.execute(query)
    return [SkillSummary.model_validate(s) for s in result.scalars().all()]


@router.get("/skills/{skill_id}", response_model=SkillPublic)
async def get_skill(
    skill_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> SkillPublic:
    """Get a skill with all its competencies."""
    result = await db.execute(
        select(Skill)
        .options(selectinload(Skill.competencies))
        .where(Skill.id == skill_id, Skill.status == SkillStatus.ACTIVE)
    )
    skill = result.scalar_one_or_none()
    if skill is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Skill not found.")
    return SkillPublic.model_validate(skill)


@router.get("/skills/{skill_id}/relationships", response_model=list[SkillRelationshipPublic])
async def get_skill_relationships(
    skill_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> list[SkillRelationshipPublic]:
    """Get outgoing graph relationships for a skill."""
    result = await db.execute(
        select(SkillRelationship)
        .options(
            selectinload(SkillRelationship.from_skill),
            selectinload(SkillRelationship.to_skill),
        )
        .where(SkillRelationship.from_skill_id == skill_id)
    )
    rels = result.scalars().all()
    return [
        SkillRelationshipPublic(
            from_skill_id=r.from_skill_id,
            to_skill_id=r.to_skill_id,
            to_skill_name=r.to_skill.canonical_name,
            relationship_type=r.relationship_type,
            strength=r.strength,
        )
        for r in rels
    ]


@router.get("/roles", response_model=list[RoleSummary])
async def list_roles(
    db: AsyncSession = Depends(get_db),
) -> list[RoleSummary]:
    """List all active roles in the catalog."""
    result = await db.execute(
        select(RolesCatalog)
        .where(RolesCatalog.is_active.is_(True))
        .order_by(RolesCatalog.name)
    )
    return [RoleSummary.model_validate(r) for r in result.scalars().all()]


@router.get("/roles/{role_id}", response_model=RolePublic)
async def get_role(
    role_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> RolePublic:
    """Get a role with its full skill requirements."""
    result = await db.execute(
        select(RolesCatalog)
        .options(
            selectinload(RolesCatalog.requirements).selectinload(RoleRequirement.skill)
        )
        .where(RolesCatalog.id == role_id, RolesCatalog.is_active.is_(True))
    )
    role = result.scalar_one_or_none()
    if role is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found.")

    requirements = [
        RoleRequirementPublic(
            skill_id=req.skill_id,
            skill_name=req.skill.canonical_name,
            required_proficiency=req.required_proficiency,
            is_mandatory=req.is_mandatory,
            relationship_type=req.relationship_type,
            display_order=req.display_order,
        )
        for req in sorted(role.requirements, key=lambda r: r.display_order)
    ]
    return RolePublic(
        id=role.id,
        name=role.name,
        description=role.description,
        industry_sector=role.industry_sector,
        experience_level=role.experience_level,
        requirements=requirements,
    )


@router.get("/students/me/skills", response_model=StudentSkillProfile)
async def get_my_skill_profile(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> StudentSkillProfile:
    """
    Get the authenticated student's full skill profile.
    Returns all assessed skills with proficiency and confidence scores.
    """
    if current_user.role != UserRole.STUDENT:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only students have a skill profile.",
        )

    result = await db.execute(
        select(StudentSkill)
        .options(selectinload(StudentSkill.skill))
        .where(StudentSkill.student_id == current_user.id)
        .order_by(StudentSkill.proficiency.desc())
    )
    student_skills = list(result.scalars().all())

    skill_items = [
        StudentSkillPublic(
            id=ss.id,
            skill_id=ss.skill_id,
            skill_name=ss.skill.canonical_name,
            skill_category=ss.skill.category,
            proficiency=ss.proficiency,
            confidence=ss.confidence,
            credibility=ss.credibility,
            proficiency_level=get_proficiency_level(ss.proficiency),
            assessment_count=ss.assessment_count,
            last_assessed_at=ss.last_assessed_at,
        )
        for ss in student_skills
    ]

    avg_proficiency = (
        sum(s.proficiency for s in skill_items) / len(skill_items)
        if skill_items else 0.0
    )
    avg_confidence = (
        sum(s.confidence for s in skill_items) / len(skill_items)
        if skill_items else 0.0
    )

    return StudentSkillProfile(
        student_id=current_user.id,
        skills=skill_items,
        total_skills_assessed=len(skill_items),
        average_proficiency=round(avg_proficiency, 2),
        average_confidence=round(avg_confidence, 2),
    )
