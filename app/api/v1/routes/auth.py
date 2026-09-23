"""
SkillMesh — Auth Routes
POST /api/v1/auth/register
POST /api/v1/auth/login
GET  /api/v1/auth/me
POST /api/v1/auth/logout
GET  /api/v1/auth/institutions   — list institutions for registration form
GET  /api/v1/auth/organizations  — list industry orgs for registration form
"""

from fastapi import APIRouter, Depends
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
    # Supabase JWTs are stateless — there is no server-side session to invalidate.
    # The client must discard the token.
    # Token revocation can be added via Supabase's sign-out endpoint in Phase 9.
    return SuccessResponse(message="Logged out successfully. Discard your access token.")


@router.get(
    "/institutions",
    response_model=list[InstitutionSummary],
    summary="List institutions (for registration form)",
)
async def list_institutions(
    db: AsyncSession = Depends(get_db),
) -> list[InstitutionSummary]:
    """
    Public endpoint — no auth required.
    Returns active institutions for the registration form dropdown.
    """
    repo = InstitutionRepository(db)
    institutions = await repo.list_active(limit=200)
    return [InstitutionSummary.model_validate(i) for i in institutions]


@router.get(
    "/organizations",
    response_model=list[IndustryOrgSummary],
    summary="List industry organizations (for registration form)",
)
async def list_organizations(
    db: AsyncSession = Depends(get_db),
) -> list[IndustryOrgSummary]:
    """
    Public endpoint — no auth required.
    Returns active industry organizations for the registration form dropdown.
    """
    repo = IndustryOrganizationRepository(db)
    orgs = await repo.list_active(limit=200)
    return [IndustryOrgSummary.model_validate(o) for o in orgs]
