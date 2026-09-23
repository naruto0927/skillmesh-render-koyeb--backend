"""
SkillMesh — Institution & Industry Organization Repositories
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.organization import Institution, IndustryOrganization


class InstitutionRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(self, institution_id: uuid.UUID) -> Institution | None:
        result = await self.db.execute(
            select(Institution).where(Institution.id == institution_id)
        )
        return result.scalar_one_or_none()

    async def list_active(
        self, limit: int = 100, offset: int = 0
    ) -> list[Institution]:
        result = await self.db.execute(
            select(Institution)
            .where(Institution.is_active.is_(True))
            .order_by(Institution.name)
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def create(self, name: str, **kwargs) -> Institution:
        institution = Institution(name=name, **kwargs)
        self.db.add(institution)
        await self.db.flush()
        return institution


class IndustryOrganizationRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(self, org_id: uuid.UUID) -> IndustryOrganization | None:
        result = await self.db.execute(
            select(IndustryOrganization).where(IndustryOrganization.id == org_id)
        )
        return result.scalar_one_or_none()

    async def list_active(
        self, limit: int = 100, offset: int = 0
    ) -> list[IndustryOrganization]:
        result = await self.db.execute(
            select(IndustryOrganization)
            .where(IndustryOrganization.is_active.is_(True))
            .order_by(IndustryOrganization.name)
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def create(self, name: str, **kwargs) -> IndustryOrganization:
        org = IndustryOrganization(name=name, **kwargs)
        self.db.add(org)
        await self.db.flush()
        return org
