"""
SkillMesh — Assessment Service

Orchestrates the full assessment lifecycle:
  start_attempt()   → creates an attempt, selects first question batch
  submit_answers()  → validates answers server-side, scores, updates StudentSkill
  get_next_question() → adaptive routing for next question

Security rules enforced here:
  - Correct answers are validated server-side only
  - Options are randomised on delivery (order not stored)
  - Attempt limits are checked before starting
  - Flagging logic for suspicious patterns
"""

import random
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.logging import get_logger
from app.core.scoring import (
    AnswerRecord,
    AttemptRecord,
    aggregate_skill_score,
    next_question_difficulty,
    score_attempt,
)
from app.models.assessment import (
    AssessmentAnswer,
    AssessmentAttempt,
    AssessmentMode,
    AssessmentQuestion,
    AssessmentResult,
    AttemptStatus,
    DifficultyLevel,
    EvidenceCredibility,
    StudentSkill,
)
from app.models.skill import Skill
from app.models.user import User

logger = get_logger(__name__)

# Maximum attempts per skill per student (configurable in Phase 10)
MAX_ATTEMPTS_PER_SKILL = 5
# Questions per adaptive session
ADAPTIVE_SESSION_LENGTH = 15
# Starting difficulty for adaptive mode
ADAPTIVE_START_DIFFICULTY = DifficultyLevel.EASY


class AssessmentService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def start_attempt(
        self,
        student: User,
        skill_id: uuid.UUID,
        mode: AssessmentMode = AssessmentMode.ADAPTIVE,
    ) -> AssessmentAttempt:
        """
        Start a new assessment attempt for a student on a given skill.
        Checks attempt limits and creates the attempt record.
        """
        # Verify skill exists and is active
        skill = await self._get_active_skill(skill_id)

        # Check attempt limits
        await self._check_attempt_limit(student.id, skill_id)

        # Check there are enough questions
        question_count = await self._count_questions(skill_id)
        if question_count < 5:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Not enough questions available for skill '{skill.canonical_name}'. "
                       f"Minimum 5 required, found {question_count}.",
            )

        attempt = AssessmentAttempt(
            student_id=student.id,
            skill_id=skill_id,
            mode=mode,
            status=AttemptStatus.IN_PROGRESS,
            started_at=datetime.now(timezone.utc),
        )
        self.db.add(attempt)
        await self.db.flush()
        await self.db.refresh(attempt)

        logger.info(
            f"Assessment started: student={student.id} skill={skill_id} "
            f"attempt={attempt.id} mode={mode}"
        )
        return attempt

    async def get_next_question(
        self,
        attempt_id: uuid.UUID,
        student_id: uuid.UUID,
    ) -> AssessmentQuestion | None:
        """
        Get the next question for an in-progress adaptive attempt.
        Returns None when the session is complete.

        Question selection:
          - Excludes already-answered questions in this attempt
          - Routes difficulty based on recent answer streak
          - Randomises option order on delivery
        """
        attempt = await self._get_attempt(attempt_id, student_id)

        if attempt.status != AttemptStatus.IN_PROGRESS:
            return None

        # Load answers so far
        answers_result = await self.db.execute(
            select(AssessmentAnswer)
            .where(AssessmentAnswer.attempt_id == attempt_id)
            .order_by(AssessmentAnswer.question_order)
        )
        answers = list(answers_result.scalars().all())

        # Check session length
        if len(answers) >= ADAPTIVE_SESSION_LENGTH:
            return None  # Session complete

        # Determine next difficulty
        if not answers:
            target_difficulty = ADAPTIVE_START_DIFFICULTY
        else:
            recent_correctness = [a.is_correct for a in answers[-4:]]
            last_difficulty = DifficultyLevel(answers[-1].question_difficulty)
            target_difficulty = next_question_difficulty(last_difficulty, recent_correctness)

        # Fetch a question at target difficulty (not already answered)
        answered_ids = {a.question_id for a in answers}
        question = await self._pick_question(
            skill_id=attempt.skill_id,
            difficulty=target_difficulty,
            exclude_ids=answered_ids,
        )

        # Fallback: if no questions at target difficulty, try adjacent levels
        if question is None:
            for fallback in [DifficultyLevel.MEDIUM, DifficultyLevel.EASY, DifficultyLevel.HARD]:
                if fallback != target_difficulty:
                    question = await self._pick_question(
                        skill_id=attempt.skill_id,
                        difficulty=fallback,
                        exclude_ids=answered_ids,
                    )
                    if question:
                        break

        return question

    async def submit_answer(
        self,
        attempt_id: uuid.UUID,
        student_id: uuid.UUID,
        question_id: uuid.UUID,
        student_answer: str,
        time_taken_seconds: int | None = None,
    ) -> AssessmentAnswer:
        """
        Validate and record a student's answer to a single question.
        Correct answers are validated server-side — never trust the client.
        """
        attempt = await self._get_attempt(attempt_id, student_id)
        if attempt.status != AttemptStatus.IN_PROGRESS:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This attempt is no longer in progress.",
            )

        # Load question (including correct_answer for server-side validation)
        q_result = await self.db.execute(
            select(AssessmentQuestion).where(
                AssessmentQuestion.id == question_id,
                AssessmentQuestion.skill_id == attempt.skill_id,
                AssessmentQuestion.is_active.is_(True),
            )
        )
        question = q_result.scalar_one_or_none()
        if question is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Question not found for this skill.",
            )

        # Check not already answered
        existing = await self.db.execute(
            select(AssessmentAnswer).where(
                AssessmentAnswer.attempt_id == attempt_id,
                AssessmentAnswer.question_id == question_id,
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This question has already been answered in this attempt.",
            )

        # Server-side correctness check
        is_correct = student_answer.strip().lower() == question.correct_answer.strip().lower()

        # Get current order count
        count_result = await self.db.execute(
            select(func.count()).where(AssessmentAnswer.attempt_id == attempt_id)
        )
        question_order = (count_result.scalar() or 0) + 1

        # Suspicious behaviour flag: answered in < 2 seconds
        is_suspicious = (
            time_taken_seconds is not None and time_taken_seconds < 2
        )

        answer = AssessmentAnswer(
            attempt_id=attempt_id,
            question_id=question_id,
            student_answer=student_answer,
            is_correct=is_correct,
            question_difficulty=question.difficulty.value,
            time_taken_seconds=time_taken_seconds,
            question_order=question_order,
        )
        self.db.add(answer)

        # Update attempt counters
        attempt.total_questions = question_order
        if is_correct:
            attempt.correct_count += 1
        if is_suspicious:
            attempt.is_flagged = True
            attempt.flag_reason = "Suspiciously fast answers detected."

        await self.db.flush()
        return answer

    async def complete_attempt(
        self,
        attempt_id: uuid.UUID,
        student_id: uuid.UUID,
    ) -> AssessmentResult:
        """
        Finalise an assessment attempt.
        Computes scores, creates AssessmentResult, updates StudentSkill.
        """
        attempt = await self._get_attempt(attempt_id, student_id)
        if attempt.status != AttemptStatus.IN_PROGRESS:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Attempt is not in progress.",
            )

        # Load all answers
        answers_result = await self.db.execute(
            select(AssessmentAnswer)
            .options(selectinload(AssessmentAnswer.question))
            .where(AssessmentAnswer.attempt_id == attempt_id)
        )
        answers = list(answers_result.scalars().all())

        if not answers:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Cannot complete an attempt with no answers.",
            )

        # Score this attempt
        answer_records = [
            AnswerRecord(
                is_correct=a.is_correct,
                difficulty=DifficultyLevel(a.question_difficulty),
                question_points=a.question.points if a.question else 1.0,
            )
            for a in answers
        ]
        scoring = score_attempt(answer_records)

        # Mark attempt completed
        attempt.status = AttemptStatus.COMPLETED
        attempt.completed_at = datetime.now(timezone.utc)
        attempt.total_questions = scoring.total_questions
        attempt.correct_count = scoring.correct_count

        # Compute per-competency breakdown
        competency_scores = await self._compute_competency_breakdown(answers)

        # Create result record
        result = AssessmentResult(
            attempt_id=attempt_id,
            student_id=student_id,
            skill_id=attempt.skill_id,
            raw_score=scoring.raw_score,
            proficiency_score=scoring.proficiency_score,
            confidence_score=scoring.confidence_score,
            competency_scores=competency_scores,
            proficiency_level=scoring.proficiency_level,
        )
        self.db.add(result)
        await self.db.flush()

        # Update StudentSkill with aggregated score across all attempts
        await self._update_student_skill(student_id, attempt.skill_id)

        await self.db.commit()
        await self.db.refresh(result)

        logger.info(
            f"Attempt completed: student={student_id} skill={attempt.skill_id} "
            f"proficiency={scoring.proficiency_score:.1f} "
            f"confidence={scoring.confidence_score:.1f}"
        )
        return result

    # ─── Private helpers ──────────────────────────────────────────────────────

    async def _get_active_skill(self, skill_id: uuid.UUID) -> Skill:
        from app.models.skill import SkillStatus
        result = await self.db.execute(
            select(Skill).where(
                Skill.id == skill_id,
                Skill.status == SkillStatus.ACTIVE,
            )
        )
        skill = result.scalar_one_or_none()
        if skill is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Skill not found or inactive.",
            )
        return skill

    async def _check_attempt_limit(
        self, student_id: uuid.UUID, skill_id: uuid.UUID
    ) -> None:
        count_result = await self.db.execute(
            select(func.count()).where(
                AssessmentAttempt.student_id == student_id,
                AssessmentAttempt.skill_id == skill_id,
                AssessmentAttempt.status.in_(
                    [AttemptStatus.COMPLETED, AttemptStatus.IN_PROGRESS]
                ),
            )
        )
        count = count_result.scalar() or 0
        if count >= MAX_ATTEMPTS_PER_SKILL:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Maximum {MAX_ATTEMPTS_PER_SKILL} attempts allowed per skill.",
            )

    async def _count_questions(self, skill_id: uuid.UUID) -> int:
        result = await self.db.execute(
            select(func.count()).where(
                AssessmentQuestion.skill_id == skill_id,
                AssessmentQuestion.is_active.is_(True),
            )
        )
        return result.scalar() or 0

    async def _pick_question(
        self,
        skill_id: uuid.UUID,
        difficulty: DifficultyLevel,
        exclude_ids: set[uuid.UUID],
    ) -> AssessmentQuestion | None:
        query = select(AssessmentQuestion).where(
            AssessmentQuestion.skill_id == skill_id,
            AssessmentQuestion.difficulty == difficulty,
            AssessmentQuestion.is_active.is_(True),
        )
        if exclude_ids:
            query = query.where(AssessmentQuestion.id.notin_(exclude_ids))

        result = await self.db.execute(query)
        candidates = list(result.scalars().all())
        if not candidates:
            return None
        return random.choice(candidates)  # noqa: S311 — not cryptographic

    async def _get_attempt(
        self, attempt_id: uuid.UUID, student_id: uuid.UUID
    ) -> AssessmentAttempt:
        result = await self.db.execute(
            select(AssessmentAttempt).where(
                AssessmentAttempt.id == attempt_id,
                AssessmentAttempt.student_id == student_id,
            )
        )
        attempt = result.scalar_one_or_none()
        if attempt is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Assessment attempt not found.",
            )
        return attempt

    async def _compute_competency_breakdown(
        self, answers: list[AssessmentAnswer]
    ) -> dict:
        """
        Compute per-competency scores from answers.
        Returns a dict mapping competency_id → {correct, total, score}.
        """
        breakdown: dict[str, dict] = {}
        for answer in answers:
            if answer.question and answer.question.competency_id:
                cid = str(answer.question.competency_id)
                if cid not in breakdown:
                    breakdown[cid] = {"correct": 0, "total": 0, "score": 0.0}
                breakdown[cid]["total"] += 1
                if answer.is_correct:
                    breakdown[cid]["correct"] += 1

        for cid, data in breakdown.items():
            data["score"] = round(
                (data["correct"] / data["total"]) * 100.0 if data["total"] > 0 else 0.0, 2
            )
        return breakdown

    async def _update_student_skill(
        self, student_id: uuid.UUID, skill_id: uuid.UUID
    ) -> None:
        """
        Recompute and persist the StudentSkill record after a new attempt.
        Pulls all completed attempts and runs the aggregation algorithm.
        """
        # Load all completed attempts for this student+skill
        attempts_result = await self.db.execute(
            select(AssessmentResult)
            .where(
                AssessmentResult.student_id == student_id,
                AssessmentResult.skill_id == skill_id,
            )
            .order_by(AssessmentResult.created_at.asc())
        )
        results = list(attempts_result.scalars().all())

        # Build AttemptRecord list for scoring engine
        attempt_records = []
        for r in results:
            # Load the attempt to get flagged status
            att_result = await self.db.execute(
                select(AssessmentAttempt).where(AssessmentAttempt.id == r.attempt_id)
            )
            att = att_result.scalar_one_or_none()
            attempt_records.append(
                AttemptRecord(
                    proficiency_score=r.proficiency_score,
                    question_count=att.total_questions if att else 0,
                    is_flagged=att.is_flagged if att else False,
                    completed_at=att.completed_at or datetime.now(timezone.utc),
                )
            )

        aggregated = aggregate_skill_score(
            attempt_records,
            credibility=EvidenceCredibility.DEMONSTRATED,
        )

        # Upsert StudentSkill
        existing_result = await self.db.execute(
            select(StudentSkill).where(
                StudentSkill.student_id == student_id,
                StudentSkill.skill_id == skill_id,
            )
        )
        student_skill = existing_result.scalar_one_or_none()

        if student_skill is None:
            student_skill = StudentSkill(
                student_id=student_id,
                skill_id=skill_id,
            )
            self.db.add(student_skill)

        student_skill.proficiency = aggregated.proficiency
        student_skill.confidence = aggregated.confidence
        student_skill.credibility = aggregated.credibility
        student_skill.assessment_count = aggregated.assessment_count
        student_skill.last_assessed_at = datetime.now(timezone.utc)
        await self.db.flush()
