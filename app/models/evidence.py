"""
SkillMesh — Evidence & Document Models

SkillEvidence: links a piece of evidence to a student's skill claim.
Document: metadata for files stored in Supabase Storage.

Evidence design rules (spec sections 19, 33):
- Every evidence record has an EvidenceType and a VerificationStatus.
- Self-declaration is valid but has lowest credibility.
- Verification requires an actual process — never mark verified without one.
- Files live in Supabase Storage; this model stores only metadata + storage key.
- Sensitive documents must use signed URLs — never public direct links.

Credibility flow:
  Student uploads cert → status=PENDING
  Institution/employer reviews → status=VERIFIED
  StudentSkill.credibility upgrades to VERIFIED
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class EvidenceType(str, enum.Enum):
    ASSESSMENT = "assessment"                   # Platform assessment result
    CERTIFICATION = "certification"             # External certification (AWS, Google, etc.)
    PROJECT = "project"                         # Personal or academic project
    INTERNSHIP = "internship"                   # Internship completion record
    ACADEMIC_RECORD = "academic_record"         # Transcript, grade record
    INDUSTRY_TEST = "industry_test"             # Test administered by an industry partner
    FACULTY_VERIFICATION = "faculty_verification"   # Verified by faculty member
    EMPLOYER_VERIFICATION = "employer_verification" # Verified by employer
    SELF_DECLARATION = "self_declaration"       # Self-declared, lowest credibility


class VerificationStatus(str, enum.Enum):
    UNVERIFIED = "unverified"   # Submitted, not yet reviewed
    PENDING = "pending"         # Under review
    VERIFIED = "verified"       # Confirmed by trusted party
    REJECTED = "rejected"       # Review failed


class PassportVisibility(str, enum.Enum):
    PRIVATE = "private"                 # Only the student
    INSTITUTION_ONLY = "institution_only"   # Student's institution
    RECRUITER_VISIBLE = "recruiter_visible" # Verified recruiters
    PUBLIC = "public"                   # Anyone with the link


# ─── Document ─────────────────────────────────────────────────────────────────

class Document(BaseModel):
    """
    Metadata for a file stored in Supabase Storage.
    The actual file lives in Supabase Storage under storage_key.
    This record stores metadata only — never the file contents.

    Access rules:
    - Private documents → signed URL (time-limited, server-generated)
    - Public documents → only avatars and institution logos
    - Never expose storage_key directly in public API responses
    """

    __tablename__ = "documents"

    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # e.g. "certificates/uuid/aws-cert.pdf" — internal path in Supabase bucket
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False)
    # Supabase bucket name: "resumes", "certificates", "projects", etc.
    bucket: Mapped[str] = mapped_column(String(100), nullable=False)
    # Original filename provided by the user (sanitised)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    # MIME type validated server-side
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    # File size in bytes
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    is_private: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Virus/malware scan status
    scan_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending"
    )

    # ── Relationships ──────────────────────────────────────────────────────────
    owner: Mapped["User"] = relationship("User")  # type: ignore[name-defined]

    def __repr__(self) -> str:
        return f"<Document id={self.id} bucket={self.bucket} file={self.original_filename}>"


# ─── Skill Evidence ───────────────────────────────────────────────────────────

class SkillEvidence(BaseModel):
    """
    A piece of evidence backing a student's claim to a skill.

    Credibility hierarchy:
      SELF_DECLARATION < ASSESSMENT < PROJECT < INTERNSHIP
      < ACADEMIC_RECORD < INDUSTRY_TEST < CERTIFICATION
      < FACULTY_VERIFICATION < EMPLOYER_VERIFICATION

    The evidence type and verification status together determine how much
    weight the evidence carries in the confidence score calculation.

    score: a numeric score associated with this evidence (0–100).
           For certifications: pass score. For projects: supervisor grade.
           For assessments: populated automatically from AssessmentResult.
    """

    __tablename__ = "skill_evidence"

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
    evidence_type: Mapped[EvidenceType] = mapped_column(
        Enum(EvidenceType, name="evidence_type", create_type=True),
        nullable=False,
    )
    verification_status: Mapped[VerificationStatus] = mapped_column(
        Enum(VerificationStatus, name="verification_status", create_type=True),
        nullable=False,
        default=VerificationStatus.UNVERIFIED,
        index=True,
    )
    # Human-readable source (e.g. "AWS Certified Developer", "CS50 Python")
    source_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # URL to external certificate/credential (optional)
    source_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Numeric score (0–100) — None if not applicable
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Who verified this evidence
    verified_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Description / notes
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # When the evidence was issued (e.g. cert issue date)
    issued_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # When this evidence expires (e.g. cert renewal date)
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Optional linked document
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Linked assessment result (for ASSESSMENT type evidence)
    assessment_result_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assessment_results.id", ondelete="SET NULL"),
        nullable=True,
    )

    # ── Relationships ──────────────────────────────────────────────────────────
    student: Mapped["User"] = relationship(  # type: ignore[name-defined]
        "User", foreign_keys=[student_id]
    )
    skill: Mapped["Skill"] = relationship("Skill")  # type: ignore[name-defined]
    verified_by: Mapped["User | None"] = relationship(  # type: ignore[name-defined]
        "User", foreign_keys=[verified_by_id]
    )
    document: Mapped["Document | None"] = relationship("Document")
    assessment_result: Mapped["AssessmentResult | None"] = relationship(  # type: ignore[name-defined]
        "AssessmentResult"
    )

    def __repr__(self) -> str:
        return (
            f"<SkillEvidence id={self.id} type={self.evidence_type} "
            f"status={self.verification_status}>"
        )


# ─── Skill Passport Settings ──────────────────────────────────────────────────

class SkillPassport(BaseModel):
    """
    Per-student Skill Passport configuration.
    Controls what is visible and to whom.
    One row per student — created on first access.
    """

    __tablename__ = "skill_passports"

    student_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    visibility: Mapped[PassportVisibility] = mapped_column(
        Enum(PassportVisibility, name="passport_visibility", create_type=True),
        nullable=False,
        default=PassportVisibility.INSTITUTION_ONLY,
    )
    # Shareable token for public/recruiter access
    share_token: Mapped[str | None] = mapped_column(
        String(64), nullable=True, unique=True, index=True
    )
    # Custom headline set by the student
    headline: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # Target career goal
    target_role: Mapped[str | None] = mapped_column(String(150), nullable=True)

    student: Mapped["User"] = relationship("User")  # type: ignore[name-defined]
