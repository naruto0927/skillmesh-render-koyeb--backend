"""
SkillMesh — Student Skills & Assessment Models

StudentSkill: the computed skill record for a student — proficiency + confidence.
AssessmentQuestion: the question bank.
AssessmentAttempt: one attempt at an assessment session.
AssessmentAnswer: the student's answer to a single question in an attempt.
AssessmentResult: the computed result for a completed attempt.

Key design rules (from project spec sections 12, 20, 21, 22):
- Proficiency and Confidence are separate values — never collapse them.
- Correct answers MUST NEVER be exposed via any public API.
- Scoring is deterministic — no LLM involvement.
- Attempt history is preserved for audit.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class QuestionType(str, enum.Enum):
    MULTIPLE_CHOICE = "multiple_choice"   # One correct answer from options
    MULTI_SELECT = "multi_select"         # Multiple correct answers
    TRUE_FALSE = "true_false"
    SHORT_ANSWER = "short_answer"         # Free-text, manually graded


class DifficultyLevel(str, enum.Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class AssessmentMode(str, enum.Enum):
    DIAGNOSTIC = "diagnostic"       # Quick proficiency estimate
    CERTIFICATION = "certification" # Comprehensive controlled exam
    ADAPTIVE = "adaptive"           # Difficulty adjusts based on responses


class AttemptStatus(str, enum.Enum):
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    ABANDONED = "abandoned"
    TIMED_OUT = "timed_out"


class EvidenceCredibility(str, enum.Enum):
    """How trustworthy is the evidence backing a skill score."""
    CLAIMED = "claimed"           # Self-declared, no assessment
    DEMONSTRATED = "demonstrated" # Passed an assessment
    VERIFIED = "verified"         # Verified by institution/employer


# ─── Student Skill ────────────────────────────────────────────────────────────

class StudentSkill(BaseModel):
    """
    A student's computed skill record.

    proficiency (0–100): How capable the student is at this skill.
    confidence  (0–100): How reliable the evidence backing the proficiency is.

    These are ALWAYS computed by the scoring engine — never set directly by the student.
    The student's answers to assessments drive these values.

    Evidence credibility determines the confidence ceiling:
      claimed       → confidence ≤ 30
      demonstrated  → confidence ≤ 75
      verified      → confidence ≤ 100
    """

    __tablename__ = "student_skills"
    __table_args__ = (
        UniqueConstraint("student_id", "skill_id", name="uq_student_skill"),
        CheckConstraint("proficiency >= 0 AND proficiency <= 100", name="ck_proficiency_range"),
        CheckConstraint("confidence >= 0 AND confidence <= 100", name="ck_confidence_range"),
    )

    student_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    skill_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("skills.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    proficiency: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    credibility: Mapped[EvidenceCredibility] = mapped_column(
        Enum(EvidenceCredibility, name="evidence_credibility", create_type=True),
        nullable=False,
        default=EvidenceCredibility.CLAIMED,
    )
    # Number of assessments that contributed to this score
    assessment_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Timestamp of last assessment that updated this record
    last_assessed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # ── Relationships ──────────────────────────────────────────────────────────
    student: Mapped["User"] = relationship("User")  # type: ignore[name-defined]
    skill: Mapped["Skill"] = relationship("Skill", back_populates="student_skills")  # type: ignore[name-defined]

    def __repr__(self) -> str:
        return (
            f"<StudentSkill student={self.student_id} skill={self.skill_id} "
            f"proficiency={self.proficiency:.1f} confidence={self.confidence:.1f}>"
        )


# ─── Assessment Question ──────────────────────────────────────────────────────

class AssessmentQuestion(BaseModel):
    """
    A question in the assessment question bank.

    Security rules:
    - correct_answer is NEVER returned in any public API response.
    - Options are stored as JSON array of strings.
    - Questions are versioned — retiring a question doesn't delete its history.
    """

    __tablename__ = "assessment_questions"

    skill_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("skills.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    competency_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("competencies.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    question_type: Mapped[QuestionType] = mapped_column(
        Enum(QuestionType, name="question_type", create_type=True),
        nullable=False,
        default=QuestionType.MULTIPLE_CHOICE,
    )
    difficulty: Mapped[DifficultyLevel] = mapped_column(
        Enum(DifficultyLevel, name="difficulty_level", create_type=True),
        nullable=False,
        default=DifficultyLevel.MEDIUM,
        index=True,
    )
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    # JSON array of option strings: ["Option A", "Option B", "Option C", "Option D"]
    options: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # NEVER exposed in public APIs — server-side validation only
    correct_answer: Mapped[str] = mapped_column(Text, nullable=False)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Version counter — increment when question text changes significantly
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    # Points this question is worth in scoring (default 1.0)
    points: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)

    # ── Relationships ──────────────────────────────────────────────────────────
    skill: Mapped["Skill"] = relationship("Skill", back_populates="assessment_questions")  # type: ignore[name-defined]
    competency: Mapped["Competency | None"] = relationship(  # type: ignore[name-defined]
        "Competency", back_populates="assessment_questions"
    )
    answers: Mapped[list["AssessmentAnswer"]] = relationship(
        "AssessmentAnswer", back_populates="question"
    )

    def __repr__(self) -> str:
        return (
            f"<AssessmentQuestion id={self.id} skill={self.skill_id} "
            f"difficulty={self.difficulty}>"
        )


# ─── Assessment Attempt ───────────────────────────────────────────────────────

class AssessmentAttempt(BaseModel):
    """
    One assessment session by a student.
    A student can have multiple attempts on the same skill (within attempt limits).
    """

    __tablename__ = "assessment_attempts"

    student_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    skill_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("skills.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    mode: Mapped[AssessmentMode] = mapped_column(
        Enum(AssessmentMode, name="assessment_mode", create_type=True),
        nullable=False,
        default=AssessmentMode.ADAPTIVE,
    )
    status: Mapped[AttemptStatus] = mapped_column(
        Enum(AttemptStatus, name="attempt_status", create_type=True),
        nullable=False,
        default=AttemptStatus.IN_PROGRESS,
        index=True,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Time allowed in seconds (None = no limit)
    time_limit_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Total questions presented in this attempt
    total_questions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Questions answered correctly
    correct_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Suspicious behaviour flag (rapid answering, unusual patterns)
    is_flagged: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    flag_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # ── Relationships ──────────────────────────────────────────────────────────
    answers: Mapped[list["AssessmentAnswer"]] = relationship(
        "AssessmentAnswer", back_populates="attempt", cascade="all, delete-orphan"
    )
    result: Mapped["AssessmentResult | None"] = relationship(
        "AssessmentResult", back_populates="attempt", uselist=False
    )

    def __repr__(self) -> str:
        return (
            f"<AssessmentAttempt id={self.id} student={self.student_id} "
            f"status={self.status}>"
        )


# ─── Assessment Answer ────────────────────────────────────────────────────────

class AssessmentAnswer(BaseModel):
    """
    The student's answer to a single question within an attempt.
    Preserves the full answer history — never deleted, never modified.
    """

    __tablename__ = "assessment_answers"

    attempt_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assessment_attempts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assessment_questions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    # The answer the student gave (index into options array or text)
    student_answer: Mapped[str] = mapped_column(Text, nullable=False)
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
    # Difficulty of the question at time of answering (for adaptive routing)
    question_difficulty: Mapped[DifficultyLevel] = mapped_column(
        String(10), nullable=False
    )
    # Time taken to answer this question in seconds
    time_taken_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Order this question was presented in the attempt
    question_order: Mapped[int] = mapped_column(Integer, nullable=False)

    # ── Relationships ──────────────────────────────────────────────────────────
    attempt: Mapped["AssessmentAttempt"] = relationship(
        "AssessmentAttempt", back_populates="answers"
    )
    question: Mapped["AssessmentQuestion"] = relationship(
        "AssessmentQuestion", back_populates="answers"
    )


# ─── Assessment Result ────────────────────────────────────────────────────────

class AssessmentResult(BaseModel):
    """
    Computed result for a completed assessment attempt.
    All scores here are produced by the deterministic scoring engine —
    never set by the student or by an LLM.
    """

    __tablename__ = "assessment_results"
    __table_args__ = (
        UniqueConstraint("attempt_id", name="uq_result_attempt"),
    )

    attempt_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assessment_attempts.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    student_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    skill_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("skills.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Raw score as a percentage (correct_points / total_points * 100)
    raw_score: Mapped[float] = mapped_column(Float, nullable=False)
    # Proficiency score after adaptive weighting (0–100)
    proficiency_score: Mapped[float] = mapped_column(Float, nullable=False)
    # Confidence score reflecting evidence quality (0–100)
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False)
    # Per-competency breakdown stored as JSON
    competency_scores: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Performance band
    proficiency_level: Mapped[str] = mapped_column(String(20), nullable=False)

    # ── Relationships ──────────────────────────────────────────────────────────
    attempt: Mapped["AssessmentAttempt"] = relationship(
        "AssessmentAttempt", back_populates="result"
    )

    def __repr__(self) -> str:
        return (
            f"<AssessmentResult attempt={self.attempt_id} "
            f"proficiency={self.proficiency_score:.1f} "
            f"confidence={self.confidence_score:.1f}>"
        )
