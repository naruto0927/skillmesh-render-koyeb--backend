"""
SkillMesh — Gap Engine Schemas
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.core.gap_engine import GapSeverity


class SetTargetRoleRequest(BaseModel):
    role_id: uuid.UUID
    notes: str | None = Field(default=None, max_length=500)


class TargetRoleResponse(BaseModel):
    id: uuid.UUID
    student_id: uuid.UUID
    role_id: uuid.UUID
    role_name: str
    is_active: bool
    notes: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class SkillGapItemResponse(BaseModel):
    skill_id: str
    skill_name: str
    required_proficiency: float
    student_proficiency: float
    gap: float
    severity: GapSeverity
    is_mandatory: bool
    skill_score: float


class ReadinessReportResponse(BaseModel):
    """
    Full readiness report — the primary output of the Skill Gap Engine.
    This is what the student sees on their gap dashboard.
    """
    role_id: str
    role_name: str
    readiness_score: float
    readiness_label: str

    strengths: list[SkillGapItemResponse]
    moderate_gaps: list[SkillGapItemResponse]
    critical_gaps: list[SkillGapItemResponse]
    missing_skills: list[SkillGapItemResponse]

    total_requirements: int
    passed_requirements: int
    mandatory_gaps: int

    # Derived convenience fields
    has_critical_gaps: bool
    priority_gaps: list[SkillGapItemResponse]  # top 3 gaps to focus on


class GapClosureResponse(BaseModel):
    skill_id: str
    skill_name: str
    initial_gap: float
    current_gap: float
    gap_closure_pct: float
    initial_proficiency: float
    current_proficiency: float
    required_proficiency: float
