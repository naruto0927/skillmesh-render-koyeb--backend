"""
SkillMesh — Security / Auth Dependencies

This module provides FastAPI dependencies for:
1. Extracting and validating JWTs from request headers
2. Loading the current authenticated user from the database
3. Enforcing role-based access control

Flow:
  Request
    → Authorization: Bearer <supabase_jwt>
    → decode_jwt()           — validates signature and expiry
    → get_current_user()     — loads User from DB using supabase_uid
    → require_role(...)      — raises 403 if role doesn't match

Security rules:
- All JWT validation is server-side — never trust the frontend
- The JWT secret must match the Supabase JWT secret in production
- supabase_uid is the bridge between Supabase Auth and our User table
- Never trust institution_id or role from the request body for auth checks
"""

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.logging import get_logger
from app.models.user import User, UserRole
from app.repositories.user_repository import UserRepository
from app.schemas.auth import TokenPayload

settings = get_settings()
logger = get_logger(__name__)

# HTTPBearer extracts the token from "Authorization: Bearer <token>"
# auto_error=False so we can return a clean 401 rather than FastAPI's default
bearer_scheme = HTTPBearer(auto_error=False)


def decode_jwt(token: str) -> TokenPayload:
    """
    Decode and validate a Supabase-issued JWT.
    Raises HTTP 401 if the token is missing, malformed, or expired.

    In production the jwt_secret must be the Supabase JWT secret from
    Project Settings → API → JWT Settings.
    """
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            options={"verify_aud": False},  # Supabase doesn't set `aud` by default
        )
        return TokenPayload(**payload)
    except JWTError as exc:
        logger.warning(f"JWT decode failure: {exc}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    FastAPI dependency — resolves the authenticated User from the JWT.

    Usage:
        async def my_route(user: User = Depends(get_current_user)):
            ...
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_jwt(credentials.credentials)

    repo = UserRepository(db)
    user = await repo.get_by_supabase_uid(payload.sub)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account not found. Please complete registration.",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated. Contact support.",
        )

    return user


# ─── Role enforcement ─────────────────────────────────────────────────────────

def require_role(*allowed_roles: UserRole):
    """
    Dependency factory for role-based access control.

    Usage:
        @router.get("/admin-only")
        async def admin_route(
            user: User = Depends(require_role(UserRole.SUPER_ADMIN))
        ):
            ...

        @router.get("/institution-or-admin")
        async def route(
            user: User = Depends(require_role(UserRole.INSTITUTION_ADMIN, UserRole.SUPER_ADMIN))
        ):
            ...
    """

    async def _check(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required role(s): {[r.value for r in allowed_roles]}.",
            )
        return user

    return _check


# ─── Convenience dependencies ─────────────────────────────────────────────────
# Import these directly in route files for common role checks.

CurrentUser = Annotated[User, Depends(get_current_user)]

SuperAdmin = Annotated[User, Depends(require_role(UserRole.SUPER_ADMIN))]

InstitutionAdmin = Annotated[
    User,
    Depends(require_role(UserRole.INSTITUTION_ADMIN, UserRole.SUPER_ADMIN)),
]

StudentUser = Annotated[User, Depends(require_role(UserRole.STUDENT))]

FacultyUser = Annotated[User, Depends(require_role(UserRole.FACULTY))]

IndustryAdminUser = Annotated[
    User,
    Depends(require_role(UserRole.INDUSTRY_ADMIN, UserRole.SUPER_ADMIN)),
]

RecruiterUser = Annotated[
    User,
    Depends(require_role(UserRole.RECRUITER, UserRole.INDUSTRY_ADMIN, UserRole.SUPER_ADMIN)),
]
