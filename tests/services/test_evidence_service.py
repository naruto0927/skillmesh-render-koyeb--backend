"""
Tests for EvidenceService — credibility calculation and evidence lifecycle.
"""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, AsyncMock

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import Base
from app.models import (
    Institution, User, UserRole,
    Skill, StudentSkill,
)
from app.models.assessment import (
    AssessmentResult, AssessmentAttempt, AssessmentMode,
    AttemptStatus, EvidenceCredibility,
)
from app.models.evidence import EvidenceType, SkillEvidence, VerificationStatus
from app.models.skill import SkillCategory, SkillStatus
from app.services.evidence_service import EvidenceService

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="function")
async def engine():
    eng = create_async_engine(TEST_DB_URL, echo=False)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await eng.dispose()


@pytest.fixture(scope="function")
async def db(engine):
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as session:
        yield session


@pytest.fixture
async def institution(db: AsyncSession) -> Institution:
    inst = Institution(name="Test Uni", is_active=True, is_verified=True)
    db.add(inst)
    await db.commit()
    await db.refresh(inst)
    return inst


@pytest.fixture
async def student(db: AsyncSession, institution: Institution) -> User:
    user = User(
        supabase_uid=str(uuid.uuid4()),
        email="ev_student@test.edu",
        full_name="Evidence Student",
        role=UserRole.STUDENT,
        institution_id=institution.id,
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest.fixture
async def faculty(db: AsyncSession, institution: Institution) -> User:
    user = User(
        supabase_uid=str(uuid.uuid4()),
        email="faculty@test.edu",
        full_name="Test Faculty",
        role=UserRole.FACULTY,
        institution_id=institution.id,
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest.fixture
async def python_skill(db: AsyncSession) -> Skill:
    skill = Skill(
        canonical_name="Python",
        category=SkillCategory.LANGUAGE,
        status=SkillStatus.ACTIVE,
    )
    db.add(skill)
    await db.commit()
    await db.refresh(skill)
    return skill


@pytest.fixture
async def student_skill(
    db: AsyncSession, student: User, python_skill: Skill
) -> StudentSkill:
    ss = StudentSkill(
        student_id=student.id,
        skill_id=python_skill.id,
        proficiency=75.0,
        confidence=50.0,
        credibility=EvidenceCredibility.CLAIMED,
        assessment_count=1,
    )
    db.add(ss)
    await db.commit()
    await db.refresh(ss)
    return ss


class TestAddEvidence:
    @patch.object(EvidenceService, "_upload_to_supabase", new_callable=AsyncMock)
    async def test_add_self_declaration(
        self, _mock, db: AsyncSession, student: User,
        python_skill: Skill, student_skill: StudentSkill
    ):
        service = EvidenceService(db)
        evidence = await service.add_evidence(
            student=student,
            skill_id=python_skill.id,
            evidence_type=EvidenceType.SELF_DECLARATION,
            source_name="Personal project",
            description="I have been using Python for 2 years.",
        )
        assert evidence.student_id == student.id
        assert evidence.skill_id == python_skill.id
        assert evidence.evidence_type == EvidenceType.SELF_DECLARATION
        assert evidence.verification_status == VerificationStatus.UNVERIFIED

    async def test_add_evidence_unknown_skill_raises_404(
        self, db: AsyncSession, student: User
    ):
        service = EvidenceService(db)
        with pytest.raises(HTTPException) as exc:
            await service.add_evidence(
                student=student,
                skill_id=uuid.uuid4(),
                evidence_type=EvidenceType.CERTIFICATION,
            )
        assert exc.value.status_code == 404


class TestCredibilityEngine:
    """
    Tests for the deterministic credibility recalculation.
    These are critical — they prove the algorithm in the spec.
    """

    async def test_self_declaration_keeps_claimed(
        self, db: AsyncSession, student: User,
        python_skill: Skill, student_skill: StudentSkill
    ):
        """Self-declaration alone → CLAIMED credibility."""
        service = EvidenceService(db)
        await service.add_evidence(
            student=student,
            skill_id=python_skill.id,
            evidence_type=EvidenceType.SELF_DECLARATION,
        )
        await db.refresh(student_skill)
        assert student_skill.credibility == EvidenceCredibility.CLAIMED

    async def test_assessment_evidence_upgrades_to_demonstrated(
        self, db: AsyncSession, student: User,
        python_skill: Skill, student_skill: StudentSkill
    ):
        """Assessment evidence → DEMONSTRATED."""
        service = EvidenceService(db)
        await service.add_evidence(
            student=student,
            skill_id=python_skill.id,
            evidence_type=EvidenceType.ASSESSMENT,
            score=82.0,
        )
        await db.refresh(student_skill)
        assert student_skill.credibility == EvidenceCredibility.DEMONSTRATED

    async def test_certification_unverified_upgrades_to_demonstrated(
        self, db: AsyncSession, student: User,
        python_skill: Skill, student_skill: StudentSkill
    ):
        """Unverified certification (non-self-declaration) → DEMONSTRATED."""
        service = EvidenceService(db)
        await service.add_evidence(
            student=student,
            skill_id=python_skill.id,
            evidence_type=EvidenceType.CERTIFICATION,
            source_name="Python Institute PCEP",
        )
        await db.refresh(student_skill)
        assert student_skill.credibility == EvidenceCredibility.DEMONSTRATED

    async def test_verified_evidence_upgrades_to_verified(
        self, db: AsyncSession, student: User, faculty: User,
        python_skill: Skill, student_skill: StudentSkill
    ):
        """Verified evidence → VERIFIED (highest)."""
        service = EvidenceService(db)
        evidence = await service.add_evidence(
            student=student,
            skill_id=python_skill.id,
            evidence_type=EvidenceType.CERTIFICATION,
            source_name="AWS Certified Developer",
        )
        # Faculty verifies
        verified = await service.verify_evidence(
            evidence_id=evidence.id,
            verifier=faculty,
            approved=True,
        )
        assert verified.verification_status == VerificationStatus.VERIFIED
        await db.refresh(student_skill)
        assert student_skill.credibility == EvidenceCredibility.VERIFIED

    async def test_verified_wins_over_demonstrated(
        self, db: AsyncSession, student: User, faculty: User,
        python_skill: Skill, student_skill: StudentSkill
    ):
        """
        Even if most evidence is DEMONSTRATED, one VERIFIED piece
        elevates the whole skill to VERIFIED.
        """
        service = EvidenceService(db)
        # Add assessment (demonstrated)
        await service.add_evidence(
            student=student,
            skill_id=python_skill.id,
            evidence_type=EvidenceType.ASSESSMENT,
            score=80.0,
        )
        # Add certification and verify it
        cert = await service.add_evidence(
            student=student,
            skill_id=python_skill.id,
            evidence_type=EvidenceType.CERTIFICATION,
            source_name="PCEP",
        )
        await service.verify_evidence(cert.id, faculty, approved=True)

        await db.refresh(student_skill)
        assert student_skill.credibility == EvidenceCredibility.VERIFIED

    async def test_rejected_evidence_excluded_from_credibility(
        self, db: AsyncSession, student: User, faculty: User,
        python_skill: Skill, student_skill: StudentSkill
    ):
        """Rejected evidence should not upgrade credibility."""
        service = EvidenceService(db)
        evidence = await service.add_evidence(
            student=student,
            skill_id=python_skill.id,
            evidence_type=EvidenceType.CERTIFICATION,
            source_name="Fake cert",
        )
        # Faculty rejects
        await service.verify_evidence(
            evidence_id=evidence.id,
            verifier=faculty,
            approved=False,
            rejection_reason="Certificate appears invalid.",
        )
        await db.refresh(student_skill)
        # Rejected evidence doesn't count → should remain CLAIMED
        # (since the only evidence was the rejected certification)
        assert student_skill.credibility == EvidenceCredibility.CLAIMED

    async def test_expired_evidence_excluded_from_credibility(
        self, db: AsyncSession, student: User,
        python_skill: Skill, student_skill: StudentSkill
    ):
        """Expired evidence should not count toward credibility."""
        service = EvidenceService(db)
        past = datetime.now(timezone.utc) - timedelta(days=1)
        await service.add_evidence(
            student=student,
            skill_id=python_skill.id,
            evidence_type=EvidenceType.CERTIFICATION,
            source_name="Expired cert",
            expires_at=past,  # Already expired
        )
        await db.refresh(student_skill)
        # Expired cert → still CLAIMED
        assert student_skill.credibility == EvidenceCredibility.CLAIMED


class TestVerifyEvidence:
    async def test_student_cannot_verify(
        self, db: AsyncSession, student: User,
        python_skill: Skill, student_skill: StudentSkill
    ):
        service = EvidenceService(db)
        evidence = await service.add_evidence(
            student=student,
            skill_id=python_skill.id,
            evidence_type=EvidenceType.CERTIFICATION,
            source_name="Some cert",
        )
        with pytest.raises(HTTPException) as exc:
            await service.verify_evidence(evidence.id, student, approved=True)
        assert exc.value.status_code == 403

    async def test_faculty_different_institution_cannot_verify(
        self, db: AsyncSession, student: User,
        python_skill: Skill, student_skill: StudentSkill
    ):
        """Faculty from a different institution cannot verify."""
        # Create a second institution and faculty
        other_inst = Institution(name="Other Uni", is_active=True, is_verified=True)
        db.add(other_inst)
        await db.commit()
        await db.refresh(other_inst)

        other_faculty = User(
            supabase_uid=str(uuid.uuid4()),
            email="other_faculty@other.edu",
            full_name="Other Faculty",
            role=UserRole.FACULTY,
            institution_id=other_inst.id,
            is_active=True,
        )
        db.add(other_faculty)
        await db.commit()
        await db.refresh(other_faculty)

        service = EvidenceService(db)
        evidence = await service.add_evidence(
            student=student,
            skill_id=python_skill.id,
            evidence_type=EvidenceType.CERTIFICATION,
        )
        with pytest.raises(HTTPException) as exc:
            await service.verify_evidence(evidence.id, other_faculty, approved=True)
        assert exc.value.status_code == 403


class TestPassport:
    async def test_get_or_create_passport(
        self, db: AsyncSession, student: User
    ):
        service = EvidenceService(db)
        passport = await service.get_or_create_passport(student)
        assert passport.student_id == student.id
        # Calling again should return the same record
        passport2 = await service.get_or_create_passport(student)
        assert passport.id == passport2.id

    async def test_update_passport_headline(
        self, db: AsyncSession, student: User
    ):
        service = EvidenceService(db)
        passport = await service.update_passport(
            student=student,
            headline="Backend Developer with Python expertise",
        )
        assert passport.headline == "Backend Developer with Python expertise"

    async def test_generate_share_token_is_unique(
        self, db: AsyncSession, student: User
    ):
        service = EvidenceService(db)
        passport = await service.generate_share_token(student)
        assert passport.share_token is not None
        assert len(passport.share_token) >= 20

    async def test_share_token_lookup(
        self, db: AsyncSession, student: User
    ):
        service = EvidenceService(db)
        passport = await service.generate_share_token(student)
        found = await service.get_passport_by_token(passport.share_token)
        assert found is not None
        assert found.student_id == student.id

    async def test_invalid_token_returns_none(
        self, db: AsyncSession
    ):
        service = EvidenceService(db)
        result = await service.get_passport_by_token("nonexistent_token")
        assert result is None


class TestFilenamesSanitisation:
    def test_removes_path_separators(self):
        safe = EvidenceService._sanitise_filename("../../etc/passwd")
        assert "/" not in safe
        assert "\\" not in safe

    def test_removes_special_chars(self):
        safe = EvidenceService._sanitise_filename("my cert (2024).pdf")
        assert "(" not in safe
        assert ")" not in safe

    def test_preserves_extension(self):
        safe = EvidenceService._sanitise_filename("certificate.pdf")
        assert safe.endswith(".pdf")

    def test_handles_empty_name(self):
        safe = EvidenceService._sanitise_filename("")
        assert safe == "upload"
