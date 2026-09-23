"""
SkillMesh — Institution & Industry Organization Models

Institution: educational institutions. Schema is GCAS-import ready —
  aishe_code, source, source_id, district allow idempotent import
  from Gujarat GCAS and other external registries.

IndustryOrganization: companies and industry partners. Supports a
  user-initiated "not listed" request flow (request_status).
"""

import enum

from sqlalchemy import Boolean, Enum, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class InstitutionType(str, enum.Enum):
    UNIVERSITY = "UNIVERSITY"
    DEEMED_UNIVERSITY = "DEEMED_UNIVERSITY"
    AUTONOMOUS_COLLEGE = "AUTONOMOUS_COLLEGE"
    AFFILIATED_COLLEGE = "AFFILIATED_COLLEGE"
    INSTITUTE_OF_TECHNOLOGY = "INSTITUTE_OF_TECHNOLOGY"
    POLYTECHNIC = "POLYTECHNIC"
    OTHER = "OTHER"


class OrgRequestStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class Institution(BaseModel):
    """
    Educational institution record.

    GCAS import fields:
      aishe_code — All India Survey on Higher Education code (unique per institution)
      source     — origin of record: "manual" | "gcas" | "ugc" | etc.
      source_id  — ID in the external system (enables idempotent re-import)
      district   — district within state (needed for GCAS data)

    The (source, source_id) pair has a partial unique index so GCAS import
    can upsert records without creating duplicates.
    """

    __tablename__ = "institutions"

    # ─── Identity ─────────────────────────────────────────────────────────────
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    short_name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    institution_type: Mapped[InstitutionType] = mapped_column(
        Enum(InstitutionType, name="institution_type", create_type=True),
        nullable=False,
        default=InstitutionType.OTHER,
    )

    # ─── Contact & Location ───────────────────────────────────────────────────
    website: Mapped[str | None] = mapped_column(String(500), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    district: Mapped[str | None] = mapped_column(String(100), nullable=True)
    state: Mapped[str | None] = mapped_column(String(100), nullable=True)
    country: Mapped[str] = mapped_column(String(100), nullable=False, default="India")
    pincode: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # ─── Verification & Status ────────────────────────────────────────────────
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # ─── GCAS / External import fields ───────────────────────────────────────
    aishe_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    source: Mapped[str] = mapped_column(String(50), nullable=False, default="manual")
    source_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # ─── Branding ─────────────────────────────────────────────────────────────
    logo_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ─── Relationships ────────────────────────────────────────────────────────
    members: Mapped[list["User"]] = relationship(  # type: ignore[name-defined]
        "User",
        back_populates="institution",
        foreign_keys="User.institution_id",
    )

    def __repr__(self) -> str:
        return f"<Institution id={self.id} name={self.name}>"


class IndustryOrganization(BaseModel):
    """
    Industry partner / company record.

    request_status flow:
      NULL      — platform-created or admin-added (always treated as approved)
      pending   — user submitted "not listed" request, awaiting admin review
      approved  — admin approved, users can now select it during registration
      rejected  — admin rejected the request
    """

    __tablename__ = "industry_organizations"

    # ─── Identity ─────────────────────────────────────────────────────────────
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    industry_sector: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # ─── Contact & Location ───────────────────────────────────────────────────
    website: Mapped[str | None] = mapped_column(String(500), nullable=True)
    headquarters_city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    headquarters_country: Mapped[str] = mapped_column(
        String(100), nullable=False, default="India"
    )

    # ─── Verification & Status ────────────────────────────────────────────────
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # ─── Request flow (for "not listed" self-registration) ────────────────────
    request_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    requested_by_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    request_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ─── Branding ─────────────────────────────────────────────────────────────
    logo_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ─── Relationships ────────────────────────────────────────────────────────
    members: Mapped[list["User"]] = relationship(  # type: ignore[name-defined]
        "User",
        back_populates="industry_org",
        foreign_keys="User.industry_org_id",
    )

    def __repr__(self) -> str:
        return f"<IndustryOrganization id={self.id} name={self.name}>"
