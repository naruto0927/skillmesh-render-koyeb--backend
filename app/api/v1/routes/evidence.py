"""
SkillMesh — Evidence & Passport Routes

POST /api/v1/evidence                       — add evidence record
GET  /api/v1/evidence                       — list my evidence
GET  /api/v1/evidence/{evidence_id}         — get single evidence record
POST /api/v1/evidence/{evidence_id}/verify  — verify/reject (faculty/admin)
POST /api/v1/documents/upload               — upload document to Supabase Storage
GET  /api/v1/documents/{doc_id}/url         — get signed download URL
GET  /api/v1/passport                       — get my full Skill Passport
PATCH /api/v1/passport                      — update passport settings
POST /api/v1/passport/share                 — generate shareable link
GET  /api/v1/passport/public/{token}        — view passport by share token (no auth)
GET  /api/v1/evidence/coverage              — evidence coverage metric
"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.scoring import get_proficiency_level
from app.core.security import CurrentUser
from app.models.assessment import EvidenceCredibility, StudentSkill
from app.models.evidence import Document, SkillEvidence, SkillPassport
from app.models.user import User, UserRole
from app.schemas.evidence import (
    AddEvidenceRequest,
    DocumentPublic,
    DocumentWithUrl,
    EvidenceCoverageReport,
    EvidencePublic,
    FullSkillPassport,
    PassportPublic,
    PassportUpdateRequest,
    ShareTokenResponse,
    VerifyEvidenceRequest,
)
from app.schemas.skill import StudentSkillPublic
from app.services.evidence_service import EvidenceService

router = APIRouter(tags=["Evidence & Passport"])


# ─── Evidence ─────────────────────────────────────────────────────────────────

@router.post("/evidence", response_model=EvidencePublic, status_code=201)
async def add_evidence(
    body: AddEvidenceRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> EvidencePublic:
    """Add a new evidence record for a skill. Students only."""
    if current_user.role != UserRole.STUDENT:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only students can add evidence.",
        )
    service = EvidenceService(db)
    evidence = await service.add_evidence(
        student=current_user,
        skill_id=body.skill_id,
        evidence_type=body.evidence_type,
        source_name=body.source_name,
        source_url=body.source_url,
        score=body.score,
        description=body.description,
        issued_at=body.issued_at,
        expires_at=body.expires_at,
        document_id=body.document_id,
    )

    # Load skill name for response
    from app.models.skill import Skill
    skill_result = await db.execute(select(Skill).where(Skill.id == evidence.skill_id))
    skill = skill_result.scalar_one_or_none()

    return EvidencePublic(
        id=evidence.id,
        student_id=evidence.student_id,
        skill_id=evidence.skill_id,
        skill_name=skill.canonical_name if skill else None,
        evidence_type=evidence.evidence_type,
        verification_status=evidence.verification_status,
        source_name=evidence.source_name,
        source_url=evidence.source_url,
        score=evidence.score,
        description=evidence.description,
        issued_at=evidence.issued_at,
        verified_at=evidence.verified_at,
        expires_at=evidence.expires_at,
        document_id=evidence.document_id,
        assessment_result_id=evidence.assessment_result_id,
        created_at=evidence.created_at,
    )


@router.get("/evidence", response_model=list[EvidencePublic])
async def list_evidence(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> list[EvidencePublic]:
    """List all evidence for the current student."""
    service = EvidenceService(db)
    all_evidence = await service.list_all_evidence(current_user.id)

    result = []
    for ev in all_evidence:
        skill_name = ev.skill.canonical_name if ev.skill else None
        result.append(
            EvidencePublic(
                id=ev.id,
                student_id=ev.student_id,
                skill_id=ev.skill_id,
                skill_name=skill_name,
                evidence_type=ev.evidence_type,
                verification_status=ev.verification_status,
                source_name=ev.source_name,
                source_url=ev.source_url,
                score=ev.score,
                description=ev.description,
                issued_at=ev.issued_at,
                verified_at=ev.verified_at,
                expires_at=ev.expires_at,
                document_id=ev.document_id,
                assessment_result_id=ev.assessment_result_id,
                created_at=ev.created_at,
            )
        )
    return result


@router.post(
    "/evidence/{evidence_id}/verify",
    response_model=EvidencePublic,
)
async def verify_evidence(
    evidence_id: uuid.UUID,
    body: VerifyEvidenceRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> EvidencePublic:
    """Verify or reject evidence. Faculty/admin only."""
    service = EvidenceService(db)
    evidence = await service.verify_evidence(
        evidence_id=evidence_id,
        verifier=current_user,
        approved=body.approved,
        rejection_reason=body.rejection_reason,
    )
    from app.models.skill import Skill
    skill_result = await db.execute(select(Skill).where(Skill.id == evidence.skill_id))
    skill = skill_result.scalar_one_or_none()
    return EvidencePublic(
        id=evidence.id,
        student_id=evidence.student_id,
        skill_id=evidence.skill_id,
        skill_name=skill.canonical_name if skill else None,
        evidence_type=evidence.evidence_type,
        verification_status=evidence.verification_status,
        source_name=evidence.source_name,
        source_url=evidence.source_url,
        score=evidence.score,
        description=evidence.description,
        issued_at=evidence.issued_at,
        verified_at=evidence.verified_at,
        expires_at=evidence.expires_at,
        document_id=evidence.document_id,
        assessment_result_id=evidence.assessment_result_id,
        created_at=evidence.created_at,
    )


@router.get("/evidence/coverage", response_model=EvidenceCoverageReport)
async def get_evidence_coverage(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> EvidenceCoverageReport:
    """
    Evidence Coverage metric: skills with meaningful evidence / total assessed skills.
    Signature metric from project spec section 56.
    """
    ss_result = await db.execute(
        select(StudentSkill).where(StudentSkill.student_id == current_user.id)
    )
    student_skills = list(ss_result.scalars().all())
    total = len(student_skills)

    if total == 0:
        return EvidenceCoverageReport(
            total_skills=0,
            evidenced_skills=0,
            evidence_coverage_pct=0.0,
            skills_by_credibility={},
        )

    by_credibility: dict[str, int] = {}
    evidenced = 0
    for ss in student_skills:
        key = ss.credibility.value
        by_credibility[key] = by_credibility.get(key, 0) + 1
        if ss.credibility != EvidenceCredibility.CLAIMED:
            evidenced += 1

    coverage_pct = round((evidenced / total) * 100, 1)
    return EvidenceCoverageReport(
        total_skills=total,
        evidenced_skills=evidenced,
        evidence_coverage_pct=coverage_pct,
        skills_by_credibility=by_credibility,
    )


# ─── Documents ────────────────────────────────────────────────────────────────

@router.post("/documents/upload", response_model=DocumentPublic, status_code=201)
async def upload_document(
    current_user: CurrentUser,
    bucket: str = "certificates",
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
) -> DocumentPublic:
    """
    Upload a document to Supabase Storage.
    Returns document metadata — NOT the storage key or raw URL.
    Use GET /documents/{id}/url to get a time-limited signed URL.
    """
    valid_buckets = {"certificates", "resumes", "projects"}
    if bucket not in valid_buckets:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid bucket. Choose from: {sorted(valid_buckets)}",
        )
    service = EvidenceService(db)
    document = await service.upload_document(
        owner=current_user, file=file, bucket=bucket
    )
    return DocumentPublic(
        id=document.id,
        original_filename=document.original_filename,
        mime_type=document.mime_type,
        file_size_bytes=document.file_size_bytes,
        is_private=document.is_private,
        created_at=document.created_at,
    )


@router.get("/documents/{doc_id}/url", response_model=DocumentWithUrl)
async def get_document_url(
    doc_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> DocumentWithUrl:
    """
    Get a time-limited signed URL for a private document.
    storage_key is never returned — only the signed URL.
    """
    doc_result = await db.execute(
        select(Document).where(Document.id == doc_id)
    )
    document = doc_result.scalar_one_or_none()
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")

    service = EvidenceService(db)
    signed_url = await service.get_signed_url(document, current_user)
    return DocumentWithUrl(
        id=document.id,
        original_filename=document.original_filename,
        mime_type=document.mime_type,
        file_size_bytes=document.file_size_bytes,
        is_private=document.is_private,
        created_at=document.created_at,
        signed_url=signed_url,
        url_expires_in_seconds=3600,
    )


# ─── Skill Passport ───────────────────────────────────────────────────────────

@router.get("/passport", response_model=FullSkillPassport)
async def get_my_passport(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> FullSkillPassport:
    """Get the full Skill Passport for the current student."""
    if current_user.role != UserRole.STUDENT:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only students have a Skill Passport.",
        )
    return await _build_passport(current_user, db)


@router.patch("/passport", response_model=PassportPublic)
async def update_passport(
    body: PassportUpdateRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> PassportPublic:
    """Update passport visibility and profile fields."""
    if current_user.role != UserRole.STUDENT:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only students have a Skill Passport.",
        )
    service = EvidenceService(db)
    passport = await service.update_passport(
        student=current_user,
        visibility=body.visibility,
        headline=body.headline,
        target_role=body.target_role,
    )
    return PassportPublic(
        student_id=passport.student_id,
        visibility=passport.visibility,
        headline=passport.headline,
        target_role=passport.target_role,
        has_share_link=passport.share_token is not None,
    )


@router.post("/passport/share", response_model=ShareTokenResponse)
async def generate_share_link(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> ShareTokenResponse:
    """Generate a shareable link for the Skill Passport."""
    if current_user.role != UserRole.STUDENT:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only students have a Skill Passport.",
        )
    service = EvidenceService(db)
    passport = await service.generate_share_token(current_user)

    base_url = settings.cors_origins_list[0] if settings.cors_origins_list else "http://localhost:3000"
    share_url = f"{base_url}/passport/{passport.share_token}"

    return ShareTokenResponse(
        share_token=passport.share_token,
        share_url=share_url,
        visibility=passport.visibility,
    )


@router.get("/passport/public/{share_token}", response_model=FullSkillPassport)
async def view_public_passport(
    share_token: str,
    db: AsyncSession = Depends(get_db),
) -> FullSkillPassport:
    """
    View a student's Skill Passport via share token.
    No authentication required — access is controlled by the token + visibility setting.
    """
    service = EvidenceService(db)
    passport = await service.get_passport_by_token(share_token)
    if passport is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Passport not found or link has been revoked.",
        )
    from app.models.evidence import PassportVisibility
    if passport.visibility == PassportVisibility.PRIVATE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This passport is set to private.",
        )

    student_result = await db.execute(select(User).where(User.id == passport.student_id))
    student = student_result.scalar_one_or_none()
    if student is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found.")

    return await _build_passport(student, db)


# ─── Passport builder ─────────────────────────────────────────────────────────

async def _build_passport(student: User, db: AsyncSession) -> FullSkillPassport:
    """Build the full passport data structure for a student."""
    from app.core.config import get_settings as _get_settings
    settings = _get_settings()

    service = EvidenceService(db)
    passport = await service.get_or_create_passport(student)

    # Load skills
    ss_result = await db.execute(
        select(StudentSkill)
        .options(selectinload(StudentSkill.skill))
        .where(StudentSkill.student_id == student.id)
        .order_by(StudentSkill.proficiency.desc())
    )
    student_skills = list(ss_result.scalars().all())

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

    # Load evidence grouped by skill
    ev_result = await db.execute(
        select(SkillEvidence)
        .options(selectinload(SkillEvidence.skill))
        .where(SkillEvidence.student_id == student.id)
        .order_by(SkillEvidence.created_at.desc())
    )
    all_evidence = list(ev_result.scalars().all())

    evidence_by_skill: dict[str, list[EvidencePublic]] = {}
    for ev in all_evidence:
        key = str(ev.skill_id)
        if key not in evidence_by_skill:
            evidence_by_skill[key] = []
        evidence_by_skill[key].append(
            EvidencePublic(
                id=ev.id,
                student_id=ev.student_id,
                skill_id=ev.skill_id,
                skill_name=ev.skill.canonical_name if ev.skill else None,
                evidence_type=ev.evidence_type,
                verification_status=ev.verification_status,
                source_name=ev.source_name,
                source_url=ev.source_url,
                score=ev.score,
                description=ev.description,
                issued_at=ev.issued_at,
                verified_at=ev.verified_at,
                expires_at=ev.expires_at,
                document_id=ev.document_id,
                assessment_result_id=ev.assessment_result_id,
                created_at=ev.created_at,
            )
        )

    # Evidence coverage
    total = len(student_skills)
    evidenced = sum(
        1 for ss in student_skills
        if ss.credibility != EvidenceCredibility.CLAIMED
    )
    by_cred: dict[str, int] = {}
    for ss in student_skills:
        key = ss.credibility.value
        by_cred[key] = by_cred.get(key, 0) + 1

    coverage = EvidenceCoverageReport(
        total_skills=total,
        evidenced_skills=evidenced,
        evidence_coverage_pct=round((evidenced / total * 100), 1) if total else 0.0,
        skills_by_credibility=by_cred,
    )

    return FullSkillPassport(
        student_id=student.id,
        student_name=student.full_name,
        headline=passport.headline,
        target_role=passport.target_role,
        visibility=passport.visibility,
        skills=skill_items,
        total_skills_assessed=len(skill_items),
        average_proficiency=round(avg_proficiency, 2),
        evidence_by_skill=evidence_by_skill,
        evidence_coverage=coverage,
        generated_at=datetime.now(timezone.utc),
    )


# import settings for share URL construction
from app.core.config import get_settings as _settings_getter
settings = _settings_getter()
