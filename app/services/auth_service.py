"""
SkillMesh — Auth Service
Coordinates between Supabase Auth and our local user database.

Registration flow:
  1. Create user in Supabase Auth (handles password hashing)
  2. Create matching User record in our DB (stores role, institution link, etc.)
  3. Return the created user

Login flow:
  1. Call Supabase Auth sign-in endpoint (validates password)
  2. Supabase returns access_token (JWT)
  3. We return that JWT to the client — FastAPI validates it on subsequent requests

Why this split?
  - Supabase Auth handles: passwords, sessions, email confirmation, OAuth, MFA
  - Our DB handles: roles, institution assignment, profile data, all business logic
  - The supabase_uid is the permanent link between the two

Security note:
  - We never store passwords — Supabase Auth does
  - The Supabase service-role key is used server-side only for admin operations
  - JWT validation uses the Supabase JWT secret (configured in Settings)
"""

import httpx
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.user import UserRole
from app.repositories.organization_repository import (
    IndustryOrganizationRepository,
    InstitutionRepository,
)
from app.repositories.user_repository import UserRepository
from app.schemas.auth import (
    LoginRequest,
    LoginResponse,
    RegisterRequest,
    RegisterResponse,
    UserPublic,
)

settings = get_settings()
logger = get_logger(__name__)


class AuthService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.user_repo = UserRepository(db)
        self.institution_repo = InstitutionRepository(db)
        self.industry_repo = IndustryOrganizationRepository(db)

    async def register(self, request: RegisterRequest) -> RegisterResponse:
        """
        Register a new user.
        1. Validate tenant assignment
        2. Create Supabase Auth user
        3. Create local User record
        """
        # ── Validate email uniqueness in our DB ───────────────────────────────
        existing = await self.user_repo.get_by_email(request.email)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An account with this email already exists.",
            )

        # ── Validate tenant assignment ────────────────────────────────────────
        await self._validate_tenant_assignment(request)

        # ── Create Supabase Auth user ─────────────────────────────────────────
        supabase_uid = await self._create_supabase_user(
            email=request.email,
            password=request.password,
            full_name=request.full_name,
        )

        # ── Create local User record ──────────────────────────────────────────
        user = await self.user_repo.create(
            supabase_uid=supabase_uid,
            email=request.email,
            full_name=request.full_name,
            role=request.role,
            institution_id=request.institution_id,
            industry_org_id=request.industry_org_id,
        )
        await self.db.commit()
        await self.db.refresh(user)

        logger.info(f"New user registered: id={user.id} role={user.role}")

        return RegisterResponse(
            user_id=user.id,
            email=user.email,
            full_name=user.full_name,
            role=user.role,
            message="Registration successful. Please check your email to confirm your account.",
        )

    async def login(self, request: LoginRequest) -> LoginResponse:
        """
        Authenticate a user via Supabase Auth.
        Returns the Supabase JWT which the client includes in subsequent requests.
        """
        supabase_response = await self._supabase_sign_in(
            email=request.email,
            password=request.password,
        )

        # Load our user record to include role and profile
        supabase_uid = supabase_response["user"]["id"]
        user = await self.user_repo.get_by_supabase_uid(supabase_uid)

        if user is None:
            # Auth succeeded in Supabase but we have no local record.
            # This can happen if registration failed mid-way.
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Account setup incomplete. Please contact support.",
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is deactivated.",
            )

        return LoginResponse(
            access_token=supabase_response["access_token"],
            token_type="bearer",
            expires_in=supabase_response.get("expires_in", 3600),
            user=UserPublic.model_validate(user),
        )

    # ─── Private helpers ──────────────────────────────────────────────────────

    async def _validate_tenant_assignment(self, request: RegisterRequest) -> None:
        """
        Ensure tenant IDs are valid and consistent with the requested role.
        """
        institution_roles = {
            UserRole.STUDENT,
            UserRole.FACULTY,
            UserRole.INSTITUTION_ADMIN,
        }
        industry_roles = {
            UserRole.INDUSTRY_ADMIN,
            UserRole.RECRUITER,
        }

        if request.role in institution_roles:
            if request.institution_id is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"institution_id is required for role {request.role.value}.",
                )
            institution = await self.institution_repo.get_by_id(request.institution_id)
            if institution is None or not institution.is_active:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Institution not found or inactive.",
                )

        elif request.role in industry_roles:
            if request.industry_org_id is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"industry_org_id is required for role {request.role.value}.",
                )
            org = await self.industry_repo.get_by_id(request.industry_org_id)
            if org is None or not org.is_active:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Industry organization not found or inactive.",
                )

        # SUPER_ADMIN requires no tenant

    async def _create_supabase_user(
        self, email: str, password: str, full_name: str
    ) -> str:
        """
        Call Supabase Auth Admin API to create a user.
        Returns the Supabase user UUID (supabase_uid).
        Uses the service-role key — server-side only.
        """
        if not settings.supabase_url or not settings.supabase_service_role_key:
            # Development mode — skip Supabase and generate a mock uid
            # This allows local development without a Supabase project
            import uuid
            mock_uid = str(uuid.uuid4())
            logger.warning(
                f"Supabase not configured — using mock uid={mock_uid} for development."
            )
            return mock_uid

        url = f"{settings.supabase_url}/auth/v1/admin/users"
        headers = {
            "apikey": settings.supabase_service_role_key,
            "Authorization": f"Bearer {settings.supabase_service_role_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "email": email,
            "password": password,
            "email_confirm": True,  # Auto-confirm in Phase 1; add email flow later
            "user_metadata": {"full_name": full_name},
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, json=payload, headers=headers)

        if response.status_code == 422:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An account with this email already exists in the auth system.",
            )
        if response.status_code not in (200, 201):
            logger.error(
                f"Supabase user creation failed: status={response.status_code}"
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Authentication service error. Please try again.",
            )

        data = response.json()
        return data["id"]

    async def _supabase_sign_in(self, email: str, password: str) -> dict:
        """
        Authenticate against Supabase Auth.
        Returns the full Supabase session object including access_token.
        """
        if not settings.supabase_url or not settings.supabase_anon_key:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Authentication service not configured.",
            )

        url = f"{settings.supabase_url}/auth/v1/token?grant_type=password"
        headers = {
            "apikey": settings.supabase_anon_key,
            "Content-Type": "application/json",
        }
        payload = {"email": email, "password": password}

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, json=payload, headers=headers)

        if response.status_code == 400:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password.",
            )
        if response.status_code != 200:
            logger.error(
                f"Supabase sign-in failed: status={response.status_code}"
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Authentication service error. Please try again.",
            )

        return response.json()
