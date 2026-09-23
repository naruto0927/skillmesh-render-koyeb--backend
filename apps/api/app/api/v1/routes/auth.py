"""
SkillMesh — Auth Routes
POST /api/v1/auth/register
POST /api/v1/auth/login
GET  /api/v1/auth/me
POST /api/v1/auth/logout
GET  /api/v1/auth/institutions              — searchable institution list
GET  /api/v1/auth/organizations             — searchable org list
POST /api/v1/auth/organizations/request     — "not listed" org request
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import CurrentUser
from app.repositories.organization_repository import (
    IndustryOrganizationRepository,
    InstitutionRepository,
)
from app.schemas.auth import (
    IndustryOrgSummary,
    InstitutionSummary,
    LoginRequest,
    LoginResponse,
    MeResponse,
    OrgRequestCreate,
    OrgRequestResponse,
    RegisterRequest,
    RegisterResponse,
    UserPublic,
)
from app.schemas.common import SuccessResponse
from app.services.auth_service import AuthService

router = APIRouter(tags=["Auth"])


@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=201,
    summary="Register a new user",
)
async def register(
    body: RegisterRequest,
    db: AsyncSession = Depends(get_db),
) -> RegisterResponse:
    service = AuthService(db)
    return await service.register(body)


@router.post(
    "/login",
    response_model=LoginResponse,
    summary="Login and receive a JWT",
)
async def login(
    body: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> LoginResponse:
    service = AuthService(db)
    return await service.login(body)


@router.get(
    "/me",
    response_model=MeResponse,
    summary="Get the current authenticated user",
)
async def me(current_user: CurrentUser) -> MeResponse:
    return MeResponse(user=UserPublic.model_validate(current_user))


@router.post(
    "/logout",
    response_model=SuccessResponse,
    summary="Logout (client should discard the JWT)",
)
async def logout(current_user: CurrentUser) -> SuccessResponse:
    return SuccessResponse(message="Logged out successfully. Discard your access token.")


@router.get(
    "/institutions",
    response_model=list[InstitutionSummary],
    summary="Search institutions (for registration form)",
)
async def list_institutions(
    search: str | None = Query(default=None, max_length=100,
                               description="Filter by name, city, district or state"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> list[InstitutionSummary]:
    """
    Public endpoint — no auth required.
    Returns active institutions matching the search term.
    Without a search term returns the first `limit` institutions alphabetically.
    Designed for use with a searchable combobox — fetch on each keystroke.
    """
    repo = InstitutionRepository(db)
    institutions = await repo.list_active(limit=limit, offset=offset, search=search)
    return [InstitutionSummary.model_validate(i) for i in institutions]


@router.get(
    "/organizations",
    response_model=list[IndustryOrgSummary],
    summary="Search industry organizations (for registration form)",
)
async def list_organizations(
    search: str | None = Query(default=None, max_length=100,
                               description="Filter by name, sector or city"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> list[IndustryOrgSummary]:
    """
    Public endpoint — no auth required.
    Returns approved/platform-created industry organizations.
    Pending requests are excluded — they are not selectable until admin approves.
    """
    repo = IndustryOrganizationRepository(db)
    orgs = await repo.list_active(limit=limit, offset=offset, search=search)
    return [IndustryOrgSummary.model_validate(o) for o in orgs]


@router.post(
    "/organizations/request",
    response_model=OrgRequestResponse,
    status_code=201,
    summary="Request addition of an unlisted organization",
)
async def request_organization(
    body: OrgRequestCreate,
    db: AsyncSession = Depends(get_db),
) -> OrgRequestResponse:
    """
    Public endpoint — no auth required (user may not have an account yet).

    Creates an IndustryOrganization in 'pending' state.
    The requesting user gets back the pending org ID so they can complete
    registration referencing it — but the org won't appear in the public
    list until a SUPER_ADMIN approves it.

    Security: arbitrary users cannot create verified/active organizations.
    Only admins can approve requests.
    """
    repo = IndustryOrganizationRepository(db)
    org = await repo.create_request(
        name=body.name,
        requested_by_email=body.requested_by_email,
        industry_sector=body.industry_sector,
        headquarters_city=body.headquarters_city,
        website=body.website,
        request_notes=body.request_notes,
    )
    await db.commit()
    await db.refresh(org)

    return OrgRequestResponse(
        id=org.id,
        name=org.name,
        request_status=org.request_status or "pending",
        message=(
            f"Your request to add '{org.name}' has been submitted. "
            "You can complete registration now — your account will be linked "
            "once an admin reviews the request (usually within 24 hours)."
        ),
    )
