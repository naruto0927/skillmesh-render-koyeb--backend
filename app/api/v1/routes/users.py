"""
SkillMesh — Users Routes
GET   /api/v1/users/me          — alias for auth/me (convenience)
PATCH /api/v1/users/me          — update own profile
GET   /api/v1/users/{user_id}   — get user by id (admin/institution admin only)
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import CurrentUser, InstitutionAdmin, SuperAdmin
from app.models.user import UserRole
from app.repositories.user_repository import UserRepository
from app.schemas.auth import UserPublic, UserUpdateRequest
from app.schemas.common import PaginatedResponse

router = APIRouter(tags=["Users"])


@router.patch(
    "/me",
    response_model=UserPublic,
    summary="Update own profile",
)
async def update_me(
    body: UserUpdateRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> UserPublic:
    repo = UserRepository(db)
    update_data = body.model_dump(exclude_none=True)
    if update_data:
        user = await repo.update(current_user, **update_data)
        await db.commit()
        await db.refresh(user)
        return UserPublic.model_validate(user)
    return UserPublic.model_validate(current_user)


@router.get(
    "/{user_id}",
    response_model=UserPublic,
    summary="Get user by ID (admin only)",
)
async def get_user(
    user_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> UserPublic:
    """
    SUPER_ADMIN can look up any user.
    INSTITUTION_ADMIN can only look up users in their own institution.
    """
    repo = UserRepository(db)
    user = await repo.get_by_id(user_id)

    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    # Enforce tenant isolation
    if current_user.role == UserRole.SUPER_ADMIN:
        return UserPublic.model_validate(user)

    if current_user.role == UserRole.INSTITUTION_ADMIN:
        if user.institution_id != current_user.institution_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied. User belongs to a different institution.",
            )
        return UserPublic.model_validate(user)

    # Other roles can only look up themselves
    if user.id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")

    return UserPublic.model_validate(user)
