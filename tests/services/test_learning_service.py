"""
Tests for LearningService — enrollment lifecycle, progress tracking,
path completion detection, and gap closure computation.
"""

import uuid
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import Base
from app.models import (
    Institution, User, UserRole,
    Skill, StudentSkill, RolesCatalog, RoleRequirement,
)
from app.models.assessment import EvidenceCredibility
from app.models.gap import StudentTargetRole
from app.models.learning import (
    EnrollmentStatus, LearningPath, LearningPathResource,
    LearningResource, LearningProgress, ProgressStatus,
    ResourceDifficulty, ResourceType,
)
from app.models.skill import SkillCategory, SkillStatus
from app.services.learning_service import LearningService

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
async def institution(db):
    inst = Institution(name="Test Uni", is_active=True, is_verified=True)
    db.add(inst)
    await db.commit()
    await db.refresh(inst)
    return inst


@pytest.fixture
async def student(db, institution):
    user = User(
        supabase_uid=str(uuid.uuid4()),
        email="learn_student@test.edu",
        full_name="Learning Student",
        role=UserRole.STUDENT,
        institution_id=institution.id,
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest.fixture
async def docker_skill(db):
    skill = Skill(
        canonical_name="Docker",
        category=SkillCategory.TOOL,
        status=SkillStatus.ACTIVE,
    )
    db.add(skill)
    await db.commit()
    await db.refresh(skill)
    return skill


async def _make_resource(db, skill_id, title, difficulty=ResourceDifficulty.BEGINNER,
                          rtype=ResourceType.TUTORIAL, gain=10.0) -> LearningResource:
    res = LearningResource(
        skill_id=skill_id,
        title=title,
        resource_type=rtype,
        difficulty=difficulty,
        url=f"https://example.com/{title.lower().replace(' ', '-')}",
        provider="Test Provider",
        estimated_minutes=60,
        is_free=True,
        expected_proficiency_gain=gain,
        is_active=True,
    )
    db.add(res)
    await db.commit()
    await db.refresh(res)
    return res


async def _make_path(db, skill_id, title, target_prof, from_prof=0.0,
                     resources=None) -> LearningPath:
    path = LearningPath(
        skill_id=skill_id,
        title=title,
        target_proficiency=target_prof,
        from_proficiency=from_prof,
        total_estimated_minutes=180,
        is_active=True,
    )
    db.add(path)
    await db.flush()

    for i, res in enumerate(resources or []):
        pr = LearningPathResource(
            path_id=path.id,
            resource_id=res.id,
            order_index=i,
            is_required=True,
        )
        db.add(pr)

    await db.commit()
    await db.refresh(path)
    return path


async def _set_skill(db, student_id, skill_id, proficiency) -> StudentSkill:
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


class TestEnrollment:
    async def test_enroll_creates_enrollment_and_progress(
        self, db: AsyncSession, student: User, docker_skill: Skill
    ):
        r1 = await _make_resource(db, docker_skill.id, "Docker Basics")
        r2 = await _make_resource(db, docker_skill.id, "Docker Compose")
        path = await _make_path(db, docker_skill.id, "Docker Fundamentals", 65.0,
                                resources=[r1, r2])
        await _set_skill(db, student.id, docker_skill.id, 31.0)

        service = LearningService(db)
        enrollment = await service.enroll(student, path.id)

        assert enrollment.student_id == student.id
        assert enrollment.path_id == path.id
        assert enrollment.status == EnrollmentStatus.ACTIVE
        assert enrollment.proficiency_at_enrollment == 31.0

    async def test_enroll_records_proficiency_baseline(
        self, db: AsyncSession, student: User, docker_skill: Skill
    ):
        """proficiency_at_enrollment is the baseline for Gap Closure."""
        r = await _make_resource(db, docker_skill.id, "Docker Intro")
        path = await _make_path(db, docker_skill.id, "Docker Path", 65.0, resources=[r])
        await _set_skill(db, student.id, docker_skill.id, 31.0)

        service = LearningService(db)
        enrollment = await service.enroll(student, path.id)
        assert enrollment.proficiency_at_enrollment == 31.0

    async def test_duplicate_enrollment_raises_409(
        self, db: AsyncSession, student: User, docker_skill: Skill
    ):
        r = await _make_resource(db, docker_skill.id, "Docker 101")
        path = await _make_path(db, docker_skill.id, "Docker Path", 65.0, resources=[r])
        service = LearningService(db)

        await service.enroll(student, path.id)
        with pytest.raises(HTTPException) as exc:
            await service.enroll(student, path.id)
        assert exc.value.status_code == 409

    async def test_enroll_inactive_path_raises_404(
        self, db: AsyncSession, student: User, docker_skill: Skill
    ):
        path = LearningPath(
            skill_id=docker_skill.id, title="Inactive",
            target_proficiency=65.0, is_active=False,
        )
        db.add(path)
        await db.commit()
        await db.refresh(path)

        service = LearningService(db)
        with pytest.raises(HTTPException) as exc:
            await service.enroll(student, path.id)
        assert exc.value.status_code == 404


class TestProgressTracking:
    async def test_update_progress_to_in_progress(
        self, db: AsyncSession, student: User, docker_skill: Skill
    ):
        r = await _make_resource(db, docker_skill.id, "Docker Basics")
        path = await _make_path(db, docker_skill.id, "Docker Path", 65.0, resources=[r])
        service = LearningService(db)
        enrollment = await service.enroll(student, path.id)

        progress = await service.update_progress(
            student=student,
            enrollment_id=enrollment.id,
            resource_id=r.id,
            new_status=ProgressStatus.IN_PROGRESS,
        )
        assert progress.status == ProgressStatus.IN_PROGRESS
        assert progress.completed_at is None

    async def test_complete_resource_sets_completed_at(
        self, db: AsyncSession, student: User, docker_skill: Skill
    ):
        r = await _make_resource(db, docker_skill.id, "Docker Basics")
        path = await _make_path(db, docker_skill.id, "Docker Path", 65.0, resources=[r])
        service = LearningService(db)
        enrollment = await service.enroll(student, path.id)

        progress = await service.update_progress(
            student=student,
            enrollment_id=enrollment.id,
            resource_id=r.id,
            new_status=ProgressStatus.COMPLETED,
        )
        assert progress.status == ProgressStatus.COMPLETED
        assert progress.completed_at is not None

    async def test_completing_all_resources_completes_enrollment(
        self, db: AsyncSession, student: User, docker_skill: Skill
    ):
        """When all required resources are complete, enrollment → COMPLETED."""
        r1 = await _make_resource(db, docker_skill.id, "Docker Basics")
        r2 = await _make_resource(db, docker_skill.id, "Docker Compose")
        path = await _make_path(db, docker_skill.id, "Docker Path", 65.0,
                                resources=[r1, r2])
        service = LearningService(db)
        enrollment = await service.enroll(student, path.id)

        await service.update_progress(student, enrollment.id, r1.id, ProgressStatus.COMPLETED)
        await service.update_progress(student, enrollment.id, r2.id, ProgressStatus.COMPLETED)

        from sqlalchemy import select as sa_select
        from app.models.learning import LearningPathEnrollment
        refreshed = await db.execute(
            sa_select(LearningPathEnrollment).where(LearningPathEnrollment.id == enrollment.id)
        )
        updated = refreshed.scalar_one()
        assert updated.status == EnrollmentStatus.COMPLETED
        assert updated.completed_at is not None

    async def test_completing_only_one_of_two_does_not_complete_enrollment(
        self, db: AsyncSession, student: User, docker_skill: Skill
    ):
        r1 = await _make_resource(db, docker_skill.id, "Part 1")
        r2 = await _make_resource(db, docker_skill.id, "Part 2")
        path = await _make_path(db, docker_skill.id, "Docker Path", 65.0,
                                resources=[r1, r2])
        service = LearningService(db)
        enrollment = await service.enroll(student, path.id)

        await service.update_progress(student, enrollment.id, r1.id, ProgressStatus.COMPLETED)

        from sqlalchemy import select as sa_select
        from app.models.learning import LearningPathEnrollment
        refreshed = await db.execute(
            sa_select(LearningPathEnrollment).where(LearningPathEnrollment.id == enrollment.id)
        )
        updated = refreshed.scalar_one()
        assert updated.status == EnrollmentStatus.ACTIVE

    async def test_wrong_enrollment_raises_404(
        self, db: AsyncSession, student: User, docker_skill: Skill
    ):
        r = await _make_resource(db, docker_skill.id, "Docker 101")
        service = LearningService(db)
        with pytest.raises(HTTPException) as exc:
            await service.update_progress(
                student, uuid.uuid4(), r.id, ProgressStatus.COMPLETED
            )
        assert exc.value.status_code == 404


class TestGapClosure:
    async def test_gap_closure_not_available_for_active_enrollment(
        self, db: AsyncSession, student: User, docker_skill: Skill
    ):
        r = await _make_resource(db, docker_skill.id, "Docker 101")
        path = await _make_path(db, docker_skill.id, "Docker Path", 65.0, resources=[r])
        await _set_skill(db, student.id, docker_skill.id, 31.0)

        service = LearningService(db)
        enrollment = await service.enroll(student, path.id)
        # Don't complete — active enrollment returns None
        result = await service.compute_gap_closure_for_enrollment(student, enrollment.id)
        assert result is None

    async def test_gap_closure_sih_spec_example(
        self, db: AsyncSession, student: User, docker_skill: Skill
    ):
        """
        From spec section 55:
          Required=65 (Docker), Initial=31, After=68
          Initial_gap = 65-31 = 34
          After_gap   = 65-68 = 0 (clamped)
          Closure     = (34-0)/34 * 100 = 100%
        """
        from app.core.gap_engine import compute_gap_closure
        result = compute_gap_closure(
            skill_id="docker",
            skill_name="Docker",
            required_proficiency=65.0,
            initial_proficiency=31.0,
            current_proficiency=68.0,
        )
        assert result.initial_gap == 34.0
        assert result.current_gap == 0.0
        assert result.gap_closure_pct == 100.0

    async def test_partial_gap_closure(
        self, db: AsyncSession, student: User, docker_skill: Skill
    ):
        """
          Required=65, Initial=31, After=48
          Initial_gap=34, After_gap=17
          Closure=(34-17)/34*100=50%
        """
        from app.core.gap_engine import compute_gap_closure
        result = compute_gap_closure("d", "Docker", 65.0, 31.0, 48.0)
        assert result.gap_closure_pct == 50.0
