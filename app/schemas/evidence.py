"""
SkillMesh — Evidence & Passport Schemas

SECURITY: Document.storage_key must NEVER appear in any response schema.
All file access goes through signed URLs.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, HttpUrl, field_validator

from app.models.evidence import EvidenceType, PassportVisibility, VerificationStatus
from app.schemas.skill import StudentSkillPublic


# ─── Document schemas ─────────────────────────────────────────────────────────

class DocumentPublic(BaseModel):
    """
    Public document metadata.
    storage_key is intentionally excluded — use signed_url for access.
    """
    id: uuid.UUID
    original_filename: str
    mime_type: str
    file_size_bytes: int
    is_private: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class DocumentWithUrl(DocumentPublic):
    """Document metadata plus a time-limited signed download URL."""
    signed_url: str
    url_expires_in_seconds: int = 3600


# ─── Evidence schemas ─────────────────────────────────────────────────────────

class AddEvidenceRequest(BaseModel):
    skill_id: uuid.UUID
    evidence_type: EvidenceType
    source_name: str | None = Field(default=None, max_length=255)
    source_url: str | None = Field(default=None, max_length=500)
    score: float | None = Field(default=None, ge=0, le=100)
    description: str | None = Field(default=None, max_length=1000)
    issued_at: datetime | None = None
    expires_at: datetime | None = None
    document_id: uuid.UUID | None = None

    @field_validator("source_url")
    @classmethod
    def validate_url(cls, v: str | None) -> str | None:
        if v and not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError("source_url must be a valid HTTP/HTTPS URL.")
        return v


class EvidencePublic(BaseModel):
    id: uuid.UUID
    student_id: uuid.UUID
    skill_id: uuid.UUID
    skill_name: str | None = None
    evidence_type: EvidenceType
    verification_status: VerificationStatus
    source_name: str | None
    source_url: str | None
    score: float | None
    description: str | None
    issued_at: datetime | None
    verified_at: datetime | None
    expires_at: datetime | None
    document_id: uuid.UUID | None
    assessment_result_id: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}


class VerifyEvidenceRequest(BaseModel):
    approved: bool
    rejection_reason: str | None = Field(default=None, max_length=500)


# ─── Evidence coverage metric ─────────────────────────────────────────────────

class EvidenceCoverageReport(BaseModel):
    """
    Evidence Coverage = skills with meaningful evidence / total assessed skills.
    This is one of the two signature metrics in the project spec (section 56).
    """
    total_skills: int
    evidenced_skills: int
    evidence_coverage_pct: float
    skills_by_credibility: dict[str, int]  # credibility → count


# ─── Passport schemas ─────────────────────────────────────────────────────────

class PassportUpdateRequest(BaseModel):
    visibility: PassportVisibility | None = None
    headline: str | None = Field(default=None, max_length=200)
    target_role: str | None = Field(default=None, max_length=150)


class PassportPublic(BaseModel):
    student_id: uuid.UUID
    visibility: PassportVisibility
    headline: str | None
    target_role: str | None
    has_share_link: bool

    model_config = {"from_attributes": True}


class FullSkillPassport(BaseModel):
    """
    The complete Skill Passport — everything a recruiter or institution sees.

    Clearly distinguishes:
    - CLAIMED skills (self-declared)
    - DEMONSTRATED skills (assessment-backed)
    - VERIFIED skills (verified by institution/employer)
    """
    student_id: uuid.UUID
    student_name: str
    headline: str | None
    target_role: str | None
    visibility: PassportVisibility

    # Skill profile
    skills: list[StudentSkillPublic]
    total_skills_assessed: int
    average_proficiency: float

    # Evidence summary per skill
    evidence_by_skill: dict[str, list[EvidencePublic]]  # skill_id → evidence list

    # Coverage metric
    evidence_coverage: EvidenceCoverageReport

    # Passport metadata
    generated_at: datetime


class ShareTokenResponse(BaseModel):
    share_token: str
    share_url: str
    visibility: PassportVisibility
