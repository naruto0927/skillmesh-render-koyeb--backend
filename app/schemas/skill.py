"""
SkillMesh — Skill, Assessment & Student Skill Schemas

CRITICAL: AssessmentQuestionPublic must NEVER include correct_answer.
The internal AssessmentQuestionInternal (used only server-side) includes it.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.models.assessment import (
    AssessmentMode,
    AttemptStatus,
    DifficultyLevel,
    EvidenceCredibility,
)
from app.models.skill import ProficiencyLevel, RelationshipType, SkillCategory, SkillStatus


# ─── Skill schemas ────────────────────────────────────────────────────────────

class CompetencyPublic(BaseModel):
    id: uuid.UUID
    skill_id: uuid.UUID
    name: str
    description: str | None
    weight: float
    display_order: int

    model_config = {"from_attributes": True}


class SkillPublic(BaseModel):
    id: uuid.UUID
    canonical_name: str
    category: SkillCategory
    description: str | None
    status: SkillStatus
    icon_key: str | None
    competencies: list[CompetencyPublic] = []

    model_config = {"from_attributes": True}


class SkillSummary(BaseModel):
    """Lightweight skill representation for list views."""
    id: uuid.UUID
    canonical_name: str
    category: SkillCategory
    icon_key: str | None

    model_config = {"from_attributes": True}


class SkillRelationshipPublic(BaseModel):
    from_skill_id: uuid.UUID
    to_skill_id: uuid.UUID
    to_skill_name: str
    relationship_type: RelationshipType
    strength: float

    model_config = {"from_attributes": True}


# ─── Role schemas ─────────────────────────────────────────────────────────────

class RoleRequirementPublic(BaseModel):
    skill_id: uuid.UUID
    skill_name: str
    required_proficiency: int
    is_mandatory: bool
    relationship_type: str
    display_order: int

    model_config = {"from_attributes": True}


class RolePublic(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    industry_sector: str | None
    experience_level: str
    requirements: list[RoleRequirementPublic] = []

    model_config = {"from_attributes": True}


class RoleSummary(BaseModel):
    id: uuid.UUID
    name: str
    industry_sector: str | None
    experience_level: str

    model_config = {"from_attributes": True}


# ─── Student skill schemas ─────────────────────────────────────────────────────

class StudentSkillPublic(BaseModel):
    """
    A student's skill record — proficiency and confidence are always shown together.
    """
    id: uuid.UUID
    skill_id: uuid.UUID
    skill_name: str
    skill_category: SkillCategory
    proficiency: float
    confidence: float
    credibility: EvidenceCredibility
    proficiency_level: str
    assessment_count: int
    last_assessed_at: datetime | None

    model_config = {"from_attributes": True}


class StudentSkillProfile(BaseModel):
    """Full skill profile for a student — all assessed skills."""
    student_id: uuid.UUID
    skills: list[StudentSkillPublic]
    total_skills_assessed: int
    average_proficiency: float
    average_confidence: float


# ─── Assessment schemas ───────────────────────────────────────────────────────

class AssessmentQuestionPublic(BaseModel):
    """
    Question schema for delivery to the student.
    NEVER includes correct_answer.
    Options are delivered in randomised order by the service layer.
    """
    id: uuid.UUID
    skill_id: uuid.UUID
    competency_id: uuid.UUID | None
    question_type: str
    difficulty: DifficultyLevel
    question_text: str
    options: list[str] | None  # Randomised order
    points: float

    model_config = {"from_attributes": True}


class StartAttemptRequest(BaseModel):
    skill_id: uuid.UUID
    mode: AssessmentMode = AssessmentMode.ADAPTIVE


class StartAttemptResponse(BaseModel):
    attempt_id: uuid.UUID
    skill_id: uuid.UUID
    mode: AssessmentMode
    status: AttemptStatus
    started_at: datetime
    first_question: AssessmentQuestionPublic | None

    model_config = {"from_attributes": True}


class SubmitAnswerRequest(BaseModel):
    question_id: uuid.UUID
    student_answer: str = Field(min_length=1, max_length=500)
    time_taken_seconds: int | None = Field(default=None, ge=0, le=3600)


class SubmitAnswerResponse(BaseModel):
    question_id: uuid.UUID
    is_correct: bool
    next_question: AssessmentQuestionPublic | None
    session_complete: bool
    questions_answered: int
    questions_remaining: int


class CompleteAttemptResponse(BaseModel):
    attempt_id: uuid.UUID
    skill_id: uuid.UUID
    raw_score: float
    proficiency_score: float
    confidence_score: float
    proficiency_level: str
    total_questions: int
    correct_count: int
    competency_scores: dict | None
    # Updated student skill after this attempt
    updated_skill: StudentSkillPublic | None

    model_config = {"from_attributes": True}


class AttemptHistoryItem(BaseModel):
    attempt_id: uuid.UUID
    skill_id: uuid.UUID
    skill_name: str
    mode: AssessmentMode
    status: AttemptStatus
    proficiency_score: float | None
    started_at: datetime
    completed_at: datetime | None

    model_config = {"from_attributes": True}
