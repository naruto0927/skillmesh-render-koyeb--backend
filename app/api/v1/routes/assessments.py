"""
SkillMesh — Assessment Routes

POST /api/v1/assessments/start                     — start adaptive attempt
GET  /api/v1/assessments/{attempt_id}/next          — get next question
POST /api/v1/assessments/{attempt_id}/answer        — submit an answer
POST /api/v1/assessments/{attempt_id}/complete      — finalise attempt
GET  /api/v1/assessments/history                    — student's attempt history
GET  /api/v1/assessments/{attempt_id}/result        — get attempt result
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.scoring import get_proficiency_level
from app.core.security import CurrentUser
from app.models.assessment import (
    AssessmentAnswer,
    AssessmentAttempt,
    AssessmentQuestion,
    AssessmentResult,
    AttemptStatus,
    StudentSkill,
)
from app.models.skill import Skill
from app.models.user import UserRole
from app.schemas.skill import (
    AssessmentQuestionPublic,
    AttemptHistoryItem,
    CompleteAttemptResponse,
    StartAttemptRequest,
    StartAttemptResponse,
    StudentSkillPublic,
    SubmitAnswerRequest,
    SubmitAnswerResponse,
)
from app.services.assessment_service import ADAPTIVE_SESSION_LENGTH, AssessmentService

router = APIRouter(tags=["Assessments"])


def _question_to_public(q: AssessmentQuestion) -> AssessmentQuestionPublic:
    """Convert a question to its public schema — options shuffled, no correct_answer."""
    import random
    options = list(q.options) if q.options else None
    if options:
        random.shuffle(options)
    return AssessmentQuestionPublic(
        id=q.id,
        skill_id=q.skill_id,
        competency_id=q.competency_id,
        question_type=q.question_type.value,
        difficulty=q.difficulty,
        question_text=q.question_text,
        options=options,
        points=q.points,
    )


@router.post("/start", response_model=StartAttemptResponse, status_code=201)
async def start_attempt(
    body: StartAttemptRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> StartAttemptResponse:
    """Start a new assessment attempt. Students only."""
    if current_user.role != UserRole.STUDENT:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only students can take assessments.",
        )

    service = AssessmentService(db)
    attempt = await service.start_attempt(
        student=current_user,
        skill_id=body.skill_id,
        mode=body.mode,
    )

    # Fetch first question immediately
    first_q = await service.get_next_question(attempt.id, current_user.id)

    return StartAttemptResponse(
        attempt_id=attempt.id,
        skill_id=attempt.skill_id,
        mode=attempt.mode,
        status=attempt.status,
        started_at=attempt.started_at,
        first_question=_question_to_public(first_q) if first_q else None,
    )


@router.get("/{attempt_id}/next", response_model=AssessmentQuestionPublic | None)
async def get_next_question(
    attempt_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> AssessmentQuestionPublic | None:
    """Get the next question in an adaptive session."""
    service = AssessmentService(db)
    question = await service.get_next_question(attempt_id, current_user.id)
    if question is None:
        return None
    return _question_to_public(question)


@router.post("/{attempt_id}/answer", response_model=SubmitAnswerResponse)
async def submit_answer(
    attempt_id: uuid.UUID,
    body: SubmitAnswerRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> SubmitAnswerResponse:
    """Submit an answer to a question. Returns correctness + next question."""
    service = AssessmentService(db)
    answer = await service.submit_answer(
        attempt_id=attempt_id,
        student_id=current_user.id,
        question_id=body.question_id,
        student_answer=body.student_answer,
        time_taken_seconds=body.time_taken_seconds,
    )

    # Count answers so far
    count_result = await db.execute(
        select(AssessmentAnswer).where(AssessmentAnswer.attempt_id == attempt_id)
    )
    answered_count = len(list(count_result.scalars().all()))
    remaining = max(0, ADAPTIVE_SESSION_LENGTH - answered_count)
    session_complete = remaining == 0

    next_q = None
    if not session_complete:
        next_q_model = await service.get_next_question(attempt_id, current_user.id)
        if next_q_model:
            next_q = _question_to_public(next_q_model)
        else:
            session_complete = True

    return SubmitAnswerResponse(
        question_id=body.question_id,
        is_correct=answer.is_correct,
        next_question=next_q,
        session_complete=session_complete,
        questions_answered=answered_count,
        questions_remaining=remaining,
    )


@router.post("/{attempt_id}/complete", response_model=CompleteAttemptResponse)
async def complete_attempt(
    attempt_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> CompleteAttemptResponse:
    """Finalise an attempt and get the scored result."""
    service = AssessmentService(db)
    result = await service.complete_attempt(attempt_id, current_user.id)

    # Load the updated StudentSkill
    ss_result = await db.execute(
        select(StudentSkill)
        .options(selectinload(StudentSkill.skill))
        .where(
            StudentSkill.student_id == current_user.id,
            StudentSkill.skill_id == result.skill_id,
        )
    )
    student_skill = ss_result.scalar_one_or_none()

    updated_skill = None
    if student_skill:
        updated_skill = StudentSkillPublic(
            id=student_skill.id,
            skill_id=student_skill.skill_id,
            skill_name=student_skill.skill.canonical_name,
            skill_category=student_skill.skill.category,
            proficiency=student_skill.proficiency,
            confidence=student_skill.confidence,
            credibility=student_skill.credibility,
            proficiency_level=get_proficiency_level(student_skill.proficiency),
            assessment_count=student_skill.assessment_count,
            last_assessed_at=student_skill.last_assessed_at,
        )

    # Load attempt for counts
    att_result = await db.execute(
        select(AssessmentAttempt).where(AssessmentAttempt.id == attempt_id)
    )
    attempt = att_result.scalar_one_or_none()

    return CompleteAttemptResponse(
        attempt_id=result.attempt_id,
        skill_id=result.skill_id,
        raw_score=result.raw_score,
        proficiency_score=result.proficiency_score,
        confidence_score=result.confidence_score,
        proficiency_level=result.proficiency_level,
        total_questions=attempt.total_questions if attempt else 0,
        correct_count=attempt.correct_count if attempt else 0,
        competency_scores=result.competency_scores,
        updated_skill=updated_skill,
    )


@router.get("/history", response_model=list[AttemptHistoryItem])
async def get_attempt_history(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> list[AttemptHistoryItem]:
    """Get the current student's assessment attempt history."""
    result = await db.execute(
        select(AssessmentAttempt, Skill)
        .join(Skill, AssessmentAttempt.skill_id == Skill.id)
        .where(AssessmentAttempt.student_id == current_user.id)
        .order_by(AssessmentAttempt.started_at.desc())
        .limit(50)
    )
    rows = result.all()

    history = []
    for attempt, skill in rows:
        # Get proficiency from result if completed
        proficiency = None
        if attempt.status == AttemptStatus.COMPLETED:
            res_q = await db.execute(
                select(AssessmentResult).where(AssessmentResult.attempt_id == attempt.id)
            )
            res = res_q.scalar_one_or_none()
            proficiency = res.proficiency_score if res else None

        history.append(
            AttemptHistoryItem(
                attempt_id=attempt.id,
                skill_id=attempt.skill_id,
                skill_name=skill.canonical_name,
                mode=attempt.mode,
                status=attempt.status,
                proficiency_score=proficiency,
                started_at=attempt.started_at,
                completed_at=attempt.completed_at,
            )
        )
    return history
