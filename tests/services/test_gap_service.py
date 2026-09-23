"""
Integration tests for GapService.
Uses in-memory SQLite — tests the full DB round-trip for target role
selection and readiness computation.
"""

import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import Base
from app.core.gap_engine import GapSeverity
from app.models import (
    Institution, User, UserRole,
    Skill, StudentSkill, RolesCatalog, RoleRequirement,
)
from app.models.skill import SkillCategory, SkillStatus
from app.models.assessment import EvidenceCredibility
from app.services.gap_service import GapService

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
        email="gap_student@test.edu",
        full_name="Gap Student",
        role=UserRole.STUDENT,
        institution_id=institution.id,
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def _make_skill(db, name, category=SkillCategory.TECHNICAL) -> Skill:
    skill = Skill(
        canonical_name=name,
        category=category,
        status=SkillStatus.ACTIVE,
    )
    db.add(skill)
    await db.commit()
    await db.refresh(skill)
    return skill


async def _make_role(db, name, requirements: list[dict]) -> RolesCatalog:
    """Create a role with requirements. Each requirement dict has skill, required, mandatory."""
    role = RolesCatalog(name=name, is_active=True, experience_level="entry")
    db.add(role)
    await db.flush()

    for i, r in enumerate(requirements):
        req = RoleRequirement(
            role_id=role.id,
            skill_id=r["skill"].id,
            required_proficiency=r["required"],
            is_mandatory=r.get("mandatory", True),
            relationship_type="required" if r.get("mandatory", True) else "preferred",
            display_order=i,
        )
        db.add(req)

    await db.commit()
    await db.refresh(role)
    return role


async def _set_student_skill(
    db, student_id, skill_id, proficiency: float
) -> StudentSkill:
    ss = StudentSkill(
        student_id=student_id,
        skill_id=skill_id,
        proficiency=proficiency,
        confidence=60.0,
        credibility=EvidenceCredibility.DEMONSTRATED,
        assessment_count=1,
    )
    db.add(ss)
    await db.commit()
    await db.refresh(ss)
    return ss


class TestSetTargetRole:
    async def test_set_target_role_creates_record(
        self, db: AsyncSession, student: User
    ):
        python = await _make_skill(db, "Python")
        role = await _make_role(db, "Backend Dev", [
            {"skill": python, "required": 80, "mandatory": True}
        ])
        service = GapService(db)
        target = await service.set_target_role(student, role.id)
        assert target.student_id == student.id
        assert target.role_id == role.id
        assert target.is_active is True

    async def test_set_new_role_deactivates_previous(
        self, db: AsyncSession, student: User
    ):
        python = await _make_skill(db, "Python")
        sql = await _make_skill(db, "SQL")
        role1 = await _make_role(db, "Backend Dev", [
            {"skill": python, "required": 80, "mandatory": True}
        ])
        role2 = await _make_role(db, "Data Engineer", [
            {"skill": sql, "required": 80, "mandatory": True}
        ])
        service = GapService(db)

        await service.set_target_role(student, role1.id)
        await service.set_target_role(student, role2.id)

        # Only one should be active
        active = await service.get_active_target_role(student.id)
        assert active is not None
        assert active.role_id == role2.id

    async def test_set_inactive_role_raises_404(
        self, db: AsyncSession, student: User
    ):
        python = await _make_skill(db, "Python")
        role = RolesCatalog(name="Inactive Role", is_active=False)
        db.add(role)
        await db.commit()

        service = GapService(db)
        with pytest.raises(HTTPException) as exc:
            await service.set_target_role(student, role.id)
        assert exc.value.status_code == 404

    async def test_get_active_returns_none_when_not_set(
        self, db: AsyncSession, student: User
    ):
        service = GapService(db)
        result = await service.get_active_target_role(student.id)
        assert result is None


class TestComputeReadiness:
    async def test_sih_demo_scenario(self, db: AsyncSession, student: User):
        """
        THE CANONICAL SIH DEMO TEST via the full service layer.

        Student:
          Python=87, SQL=81, REST API=73, Docker=31, AWS=22

        Backend Developer requirements:
          Python required=80 mandatory → STRENGTH
          SQL required=75 mandatory → STRENGTH
          REST API required=75 mandatory → MODERATE_GAP (gap=2)
          Docker required=65 preferred → CRITICAL_GAP (gap=34)
          AWS required=60 preferred → CRITICAL_GAP (gap=38)

        Expected: readiness ~84.9%, label="Ready"
        """
        python = await _make_skill(db, "Python", SkillCategory.LANGUAGE)
        sql = await _make_skill(db, "SQL", SkillCategory.DATABASE)
        rest = await _make_skill(db, "REST API")
        docker = await _make_skill(db, "Docker", SkillCategory.TOOL)
        aws = await _make_skill(db, "AWS", SkillCategory.CLOUD)

        role = await _make_role(db, "Backend Developer", [
            {"skill": python, "required": 80, "mandatory": True},
            {"skill": sql,    "required": 75, "mandatory": True},
            {"skill": rest,   "required": 75, "mandatory": True},
            {"skill": docker, "required": 65, "mandatory": False},
            {"skill": aws,    "required": 60, "mandatory": False},
        ])

        # Set student skills
        for skill, score in [
            (python, 87.0), (sql, 81.0), (rest, 73.0),
            (docker, 31.0), (aws, 22.0),
        ]:
            await _set_student_skill(db, student.id, skill.id, score)

        await _make_skill(db, "_dummy")  # ensures skill list is non-trivial

        service = GapService(db)
        await service.set_target_role(student, role.id)
        report = await service.compute_readiness_for_student(student)

        # Classification checks
        strength_names = {s.skill_name for s in report.strengths}
        assert "Python" in strength_names
        assert "SQL" in strength_names

        moderate_names = {s.skill_name for s in report.moderate_gaps}
        assert "REST API" in moderate_names

        critical_names = {s.skill_name for s in report.critical_gaps}
        assert "Docker" in critical_names
        assert "AWS" in critical_names

        # Readiness score check
        assert 84.0 <= report.readiness_score <= 86.0, (
            f"Expected ~84.9%, got {report.readiness_score}"
        )
        assert report.readiness_label == "Ready"

    async def test_no_target_role_raises_404(
        self, db: AsyncSession, student: User
    ):
        service = GapService(db)
        with pytest.raises(HTTPException) as exc:
            await service.compute_readiness_for_student(student)
        assert exc.value.status_code == 404

    async def test_missing_skills_classified_correctly(
        self, db: AsyncSession, student: User
    ):
        """Skills with no StudentSkill record → MISSING."""
        python = await _make_skill(db, "Python")
        docker = await _make_skill(db, "Docker")
        role = await _make_role(db, "Dev", [
            {"skill": python, "required": 80, "mandatory": True},
            {"skill": docker, "required": 65, "mandatory": False},
        ])
        # Set only Python
        await _set_student_skill(db, student.id, python.id, 85.0)

        service = GapService(db)
        await service.set_target_role(student, role.id)
        report = await service.compute_readiness_for_student(student)

        assert len(report.strengths) == 1
        assert len(report.missing_skills) == 1
        assert report.missing_skills[0].skill_name == "Docker"

    async def test_readiness_by_explicit_role_id(
        self, db: AsyncSession, student: User
    ):
        """compute_readiness_for_student accepts explicit role_id."""
        python = await _make_skill(db, "Python")
        role = await _make_role(db, "Dev", [
            {"skill": python, "required": 80, "mandatory": True}
        ])
        await _set_student_skill(db, student.id, python.id, 90.0)

        service = GapService(db)
        # No target role set, but explicit role_id supplied
        report = await service.compute_readiness_for_student(student, role.id)
        assert report.readiness_score == 100.0

    async def test_perfect_readiness_all_met(
        self, db: AsyncSession, student: User
    ):
        python = await _make_skill(db, "Python")
        sql = await _make_skill(db, "SQL")
        role = await _make_role(db, "Dev", [
            {"skill": python, "required": 80, "mandatory": True},
            {"skill": sql,    "required": 75, "mandatory": True},
        ])
        await _set_student_skill(db, student.id, python.id, 90.0)
        await _set_student_skill(db, student.id, sql.id, 85.0)

        service = GapService(db)
        await service.set_target_role(student, role.id)
        report = await service.compute_readiness_for_student(student)

        assert report.readiness_score == 100.0
        assert report.readiness_label == "Ready"
        assert len(report.critical_gaps) == 0
        assert len(report.missing_skills) == 0

    async def test_improved_readiness_after_upskilling(
        self, db: AsyncSession, student: User
    ):
        """
        SIH demo: student improves Docker from 31 to 68.
        Initial report has Docker as critical gap.
        After update, Docker is a strength.
        """
        docker = await _make_skill(db, "Docker")
        role = await _make_role(db, "Dev", [
            {"skill": docker, "required": 65, "mandatory": False}
        ])
        ss = await _set_student_skill(db, student.id, docker.id, 31.0)

        service = GapService(db)
        await service.set_target_role(student, role.id)
        report_before = await service.compute_readiness_for_student(student)
        assert report_before.critical_gaps[0].skill_name == "Docker"

        # Simulate learning: update proficiency
        ss.proficiency = 68.0
        await db.commit()

        report_after = await service.compute_readiness_for_student(student)
        assert len(report_after.critical_gaps) == 0
        assert report_after.strengths[0].skill_name == "Docker"
        assert report_after.readiness_score > report_before.readiness_score
