"""
SkillMesh — Auth Schemas
Pydantic models for authentication request/response validation.
These are the shapes the API accepts and returns — not the ORM models.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.models.user import UserRole


# ─── Registration ──────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=2, max_length=255)
    role: UserRole

    # Optional — provided when role is STUDENT, FACULTY, or INSTITUTION_ADMIN
    institution_id: uuid.UUID | None = None
    # Optional — provided when role is INDUSTRY_ADMIN or RECRUITER
    industry_org_id: uuid.UUID | None = None

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        """
        Basic password strength check.
        Supabase also enforces its own password policy on the auth side.
        """
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter.")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit.")
        return v

    @field_validator("full_name")
    @classmethod
    def full_name_no_scripts(cls, v: str) -> str:
        return v.strip()


class RegisterResponse(BaseModel):
    user_id: uuid.UUID
    email: str
    full_name: str
    role: UserRole
    message: str


# ─── Login ────────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds
    user: "UserPublic"


# ─── User profile ─────────────────────────────────────────────────────────────

class UserPublic(BaseModel):
    """
    Public user representation — safe to include in API responses.
    Never includes: password, supabase_uid, internal FKs.
    """

    id: uuid.UUID
    email: str
    full_name: str
    role: UserRole
    avatar_url: str | None
    is_active: bool
    is_onboarded: bool
    institution_id: uuid.UUID | None
    industry_org_id: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}


class UserUpdateRequest(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=255)
    avatar_url: str | None = None


# ─── Token ────────────────────────────────────────────────────────────────────

class TokenPayload(BaseModel):
    """
    The decoded contents of a Supabase JWT.
    Supabase encodes the user's UUID as `sub`.
    """

    sub: str  # Supabase user UUID (supabase_uid)
    email: str | None = None
    exp: int | None = None
    role: str | None = None  # Supabase's internal role, not our app role


# ─── Me ───────────────────────────────────────────────────────────────────────

class MeResponse(BaseModel):
    user: UserPublic


# ─── Institutions (list for registration form) ────────────────────────────────

class InstitutionSummary(BaseModel):
    id: uuid.UUID
    name: str
    short_name: str | None
    city: str | None
    district: str | None
    state: str | None
    institution_type: str | None = None
    aishe_code: str | None = None

    model_config = {"from_attributes": True}


class IndustryOrgSummary(BaseModel):
    id: uuid.UUID
    name: str
    industry_sector: str | None
    headquarters_city: str | None
    is_verified: bool = False

    model_config = {"from_attributes": True}


class OrgRequestCreate(BaseModel):
    """
    Submitted when a user selects 'Organization not listed'.
    Creates an IndustryOrganization with request_status='pending'.
    Admins review and approve/reject via the admin panel.
    """
    name: str = Field(min_length=2, max_length=255)
    industry_sector: str | None = Field(default=None, max_length=100)
    headquarters_city: str | None = Field(default=None, max_length=100)
    website: str | None = Field(default=None, max_length=500)
    requested_by_email: str  # The registering user's email
    request_notes: str | None = Field(default=None, max_length=500)


class OrgRequestResponse(BaseModel):
    id: uuid.UUID
    name: str
    request_status: str
    message: str
