"""
SkillMesh — Institution & Industry Organization Models

Two tenant types in the system:
1. Institution  — educational institutions (colleges, universities, institutes)
2. IndustryOrganization — companies and industry partners

Multi-tenancy rule: data belonging to Institution A must never be
accessible to users of Institution B. This is enforced at the
service/repository layer — never rely on the frontend to pass the
correct institution_id.
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


class Institution(BaseModel):
    """
    Educational institution record.
    All students, faculty, and institution admins belong to an Institution.

    Departments are a Phase 1 stub — full department management is Phase 1+.
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
    state: Mapped[str | None] = mapped_column(String(100), nullable=True)
    country: Mapped[str] = mapped_column(String(100), nullable=False, default="India")
    pincode: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # ─── Verification & Status ────────────────────────────────────────────────
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

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
    INDUSTRY_ADMIN and RECRUITER users belong to an IndustryOrganization.
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
