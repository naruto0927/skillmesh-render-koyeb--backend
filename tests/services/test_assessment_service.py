"""
Tests for the AssessmentService.
Uses in-memory SQLite — no real DB or Supabase required.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import Base
from app.models import (
    Institution, User, UserRole,
    Skill, Competency, AssessmentQuestion,
    AssessmentAttempt, AssessmentResult, StudentSkill,
)
from app.models.assessment import (
    AssessmentMode, AttemptStatus, DifficultyLevel, EvidenceCredibility,
)
from app.models.skill import SkillCategory, SkillStatus
from app.services.assessment_service import AssessmentService, MAX_ATTEMPTS_PER_SKILL

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
    inst = Institution(name="Test University", is_active=True, is_verified=True)
    db.add(inst)
    await db.commit()
    await db.refresh(inst)
    return inst


@pytest.fixture
async def student(db: AsyncSession, institution: Institution) -> User:
    user = User(
        supabase_uid=str(uuid.uuid4()),
        email="student@test.edu",
        full_name="Test Student",
        role=UserRole.STUDENT,
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
async def questions(db: AsyncSession, python_skill: Skill) -> list[AssessmentQuestion]:
    """Create 15 questions (5 per difficulty) so all adaptive sessions can run."""
    qs = []
    for difficulty in [DifficultyLevel.EASY, DifficultyLevel.MEDIUM, DifficultyLevel.HARD]:
        for i in range(5):
            q = AssessmentQuestion(
                skill_id=python_skill.id,
                question_type="multiple_choice",
                difficulty=difficulty,
                question_text=f"Question {difficulty.value} #{i+1}",
                options=["A", "B", "C", "D"],
                correct_answer="A",
                is_active=True,
                points=1.0,
            )
            db.add(q)
            qs.append(q)
    await db.commit()
    for q in qs:
        await db.refresh(q)
    return qs


class TestStartAttempt:
    async def test_start_attempt_creates_record(
        self, db: AsyncSession, student: User, python_skill: Skill, questions: list
    ):
        service = AssessmentService(db)
        attempt = await service.start_attempt(student, python_skill.id)

        assert attempt.student_id == student.id
        assert attempt.skill_id == python_skill.id
        assert attempt.status == AttemptStatus.IN_PROGRESS
        assert attempt.mode == AssessmentMode.ADAPTIVE

    async def test_start_attempt_inactive_skill_raises_404(
        self, db: AsyncSession, student: User
    ):
        inactive_skill = Skill(
            canonical_name="InactiveSkill",
            category=SkillCategory.OTHER,
            status=SkillStatus.DEPRECATED,
        )
        db.add(inactive_skill)
        await db.commit()
        await db.refresh(inactive_skill)

        service = AssessmentService(db)
        with pytest.raises(HTTPException) as exc:
            await service.start_attempt(student, inactive_skill.id)
        assert exc.value.status_code == 404

    async def test_start_attempt_not_enough_questions_raises_422(
        self, db: AsyncSession, student: User
    ):
        empty_skill = Skill(
            canonical_name="EmptySkill",
            category=SkillCategory.OTHER,
            status=SkillStatus.ACTIVE,
        )
        db.add(empty_skill)
        await db.commit()
        await db.refresh(empty_skill)

        service = AssessmentService(db)
        with pytest.raises(HTTPException) as exc:
            await service.start_attempt(student, empty_skill.id)
        assert exc.value.status_code == 422

    async def test_attempt_limit_enforced(
        self, db: AsyncSession, student: User, python_skill: Skill, questions: list
    ):
        """Cannot start more than MAX_ATTEMPTS_PER_SKILL attempts."""
        service = AssessmentService(db)

        for _ in range(MAX_ATTEMPTS_PER_SKILL):
            attempt = await service.start_attempt(student, python_skill.id)
            attempt.status = AttemptStatus.COMPLETED
            await db.commit()

        with pytest.raises(HTTPException) as exc:
            await service.start_attempt(student, python_skill.id)
        assert exc.value.status_code == 429


class TestSubmitAnswer:
    async def test_correct_answer_recorded(
        self, db: AsyncSession, student: User, python_skill: Skill, questions: list
    ):
        service = AssessmentService(db)
        attempt = await service.start_attempt(student, python_skill.id)

        # Get first question
        first_q = questions[0]  # First easy question, correct_answer = "A"
        answer = await service.submit_answer(
            attempt_id=attempt.id,
            student_id=student.id,
            question_id=first_q.id,
            student_answer="A",
        )
        assert answer.is_correct is True

    async def test_wrong_answer_recorded(
        self, db: AsyncSession, student: User, python_skill: Skill, questions: list
    ):
        service = AssessmentService(db)
        attempt = await service.start_attempt(student, python_skill.id)

        first_q = questions[0]
        answer = await service.submit_answer(
            attempt_id=attempt.id,
            student_id=student.id,
            question_id=first_q.id,
            student_answer="B",  # Wrong (correct is "A")
        )
        assert answer.is_correct is False

    async def test_duplicate_answer_raises_409(
        self, db: AsyncSession, student: User, python_skill: Skill, questions: list
    ):
        service = AssessmentService(db)
        attempt = await service.start_attempt(student, python_skill.id)
        first_q = questions[0]

        await service.submit_answer(
            attempt_id=attempt.id,
            student_id=student.id,
            question_id=first_q.id,
            student_answer="A",
        )
        with pytest.raises(HTTPException) as exc:
            await service.submit_answer(
                attempt_id=attempt.id,
                student_id=student.id,
                question_id=first_q.id,
                student_answer="A",
            )
        assert exc.value.status_code == 409

    async def test_answer_to_completed_attempt_raises_409(
        self, db: AsyncSession, student: User, python_skill: Skill, questions: list
    ):
        service = AssessmentService(db)
        attempt = await service.start_attempt(student, python_skill.id)
        attempt.status = AttemptStatus.COMPLETED
        await db.commit()

        with pytest.raises(HTTPException) as exc:
            await service.submit_answer(
                attempt_id=attempt.id,
                student_id=student.id,
                question_id=questions[0].id,
                student_answer="A",
            )
        assert exc.value.status_code == 409

    async def test_fast_answer_sets_flag(
        self, db: AsyncSession, student: User, python_skill: Skill, questions: list
    ):
        """Answering in < 2 seconds should flag the attempt."""
        service = AssessmentService(db)
        attempt = await service.start_attempt(student, python_skill.id)

        await service.submit_answer(
            attempt_id=attempt.id,
            student_id=student.id,
            question_id=questions[0].id,
            student_answer="A",
            time_taken_seconds=1,  # Suspicious
        )
        await db.refresh(attempt)
        assert attempt.is_flagged is True


class TestCompleteAttempt:
    async def test_complete_attempt_creates_result(
        self, db: AsyncSession, student: User, python_skill: Skill, questions: list
    ):
        service = AssessmentService(db)
        attempt = await service.start_attempt(student, python_skill.id)

        # Submit one answer
        await service.submit_answer(
            attempt_id=attempt.id,
            student_id=student.id,
            question_id=questions[0].id,
            student_answer="A",
        )

        result = await service.complete_attempt(attempt.id, student.id)
        assert result.attempt_id == attempt.id
        assert result.student_id == student.id
        assert result.skill_id == python_skill.id
        assert 0.0 <= result.proficiency_score <= 100.0
        assert 0.0 <= result.confidence_score <= 100.0

    async def test_complete_attempt_updates_student_skill(
        self, db: AsyncSession, student: User, python_skill: Skill, questions: list
    ):
        from sqlalchemy import select
        service = AssessmentService(db)
        attempt = await service.start_attempt(student, python_skill.id)

        await service.submit_answer(
            attempt_id=attempt.id,
            student_id=student.id,
            question_id=questions[0].id,
            student_answer="A",
        )
        await service.complete_attempt(attempt.id, student.id)

        ss_result = await db.execute(
            select(StudentSkill).where(
                StudentSkill.student_id == student.id,
                StudentSkill.skill_id == python_skill.id,
            )
        )
        student_skill = ss_result.scalar_one_or_none()
        assert student_skill is not None
        assert student_skill.proficiency > 0.0
        assert student_skill.assessment_count == 1

    async def test_complete_empty_attempt_raises_422(
        self, db: AsyncSession, student: User, python_skill: Skill, questions: list
    ):
        service = AssessmentService(db)
        attempt = await service.start_attempt(student, python_skill.id)
        # Don't submit any answers
        with pytest.raises(HTTPException) as exc:
            await service.complete_attempt(attempt.id, student.id)
        assert exc.value.status_code == 422

    async def test_correct_answers_yield_higher_proficiency(
        self, db: AsyncSession, student: User, python_skill: Skill, questions: list
    ):
        """All-correct attempt should yield higher proficiency than all-wrong."""
        service = AssessmentService(db)

        # Attempt 1: all correct
        attempt1 = await service.start_attempt(student, python_skill.id)
        await service.submit_answer(attempt1.id, student.id, questions[0].id, "A")
        await service.submit_answer(attempt1.id, student.id, questions[1].id, "A")
        result1 = await service.complete_attempt(attempt1.id, student.id)

        # Attempt 2: all wrong
        attempt2 = await service.start_attempt(student, python_skill.id)
        await service.submit_answer(attempt2.id, student.id, questions[2].id, "B")
        await service.submit_answer(attempt2.id, student.id, questions[3].id, "C")
        result2 = await service.complete_attempt(attempt2.id, student.id)

        assert result1.proficiency_score > result2.proficiency_score
