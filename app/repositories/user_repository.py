"""
SkillMesh — User Repository
All database operations for the User model.
The service layer calls this — routes never query the DB directly.

Security rule: tenant isolation is enforced here.
Never return users from a different institution without an explicit admin check.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User, UserRole


class UserRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        result = await self.db.execute(
            select(User).where(User.id == user_id, User.is_active.is_(True))
        )
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        result = await self.db.execute(
            select(User).where(User.email == email.lower())
        )
        return result.scalar_one_or_none()

    async def get_by_supabase_uid(self, supabase_uid: str) -> User | None:
        """
        Primary lookup for JWT → User resolution.
        Called on every authenticated request.
        """
        result = await self.db.execute(
            select(User).where(User.supabase_uid == supabase_uid)
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        supabase_uid: str,
        email: str,
        full_name: str,
        role: UserRole,
        institution_id: uuid.UUID | None = None,
        industry_org_id: uuid.UUID | None = None,
    ) -> User:
        user = User(
            supabase_uid=supabase_uid,
            email=email.lower(),
            full_name=full_name.strip(),
            role=role,
            institution_id=institution_id,
            industry_org_id=industry_org_id,
        )
        self.db.add(user)
        await self.db.flush()  # Gets the generated id without committing
        return user

    async def update(self, user: User, **fields) -> User:
        for key, value in fields.items():
            if hasattr(user, key):
                setattr(user, key, value)
        await self.db.flush()
        return user

    async def list_by_institution(
        self,
        institution_id: uuid.UUID,
        role: UserRole | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[User], int]:
        """
        List users belonging to an institution.
        Optionally filter by role (e.g. fetch only students).
        Returns (users, total_count) for pagination.
        """
        query = select(User).where(
            User.institution_id == institution_id,
            User.is_active.is_(True),
        )
        if role:
            query = query.where(User.role == role)

        count_result = await self.db.execute(
            select(User.id).where(
                User.institution_id == institution_id,
                User.is_active.is_(True),
                *([User.role == role] if role else []),
            )
        )
        total = len(count_result.all())

        result = await self.db.execute(
            query.order_by(User.created_at.desc()).limit(limit).offset(offset)
        )
        return result.scalars().all(), total  # type: ignore[return-value]

    async def list_by_industry_org(
        self,
        industry_org_id: uuid.UUID,
        role: UserRole | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[User], int]:
        query = select(User).where(
            User.industry_org_id == industry_org_id,
            User.is_active.is_(True),
        )
        if role:
            query = query.where(User.role == role)

        count_result = await self.db.execute(
            select(User.id).where(
                User.industry_org_id == industry_org_id,
                User.is_active.is_(True),
                *([User.role == role] if role else []),
            )
        )
        total = len(count_result.all())

        result = await self.db.execute(
            query.order_by(User.created_at.desc()).limit(limit).offset(offset)
        )
        return result.scalars().all(), total  # type: ignore[return-value]
