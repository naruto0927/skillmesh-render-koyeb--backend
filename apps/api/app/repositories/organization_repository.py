"""
SkillMesh — Institution & Industry Organization Repositories
"""

import uuid

from sqlalchemy import select, or_, func
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
        self,
        limit: int = 100,
        offset: int = 0,
        search: str | None = None,
    ) -> list[Institution]:
        """
        List active institutions, optionally filtered by search term.
        Search is case-insensitive and matches against name, short_name,
        city, and district. Uses ILIKE for PostgreSQL (trigram index helps).
        Falls back to simple contains for SQLite (tests).
        """
        query = select(Institution).where(Institution.is_active.is_(True))

        if search and search.strip():
            term = f"%{search.strip()}%"
            query = query.where(
                or_(
                    Institution.name.ilike(term),
                    Institution.short_name.ilike(term),
                    Institution.city.ilike(term),
                    Institution.district.ilike(term),
                    Institution.state.ilike(term),
                )
            )

        query = query.order_by(Institution.name).limit(limit).offset(offset)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def count_active(self, search: str | None = None) -> int:
        query = select(func.count()).select_from(Institution).where(
            Institution.is_active.is_(True)
        )
        if search and search.strip():
            term = f"%{search.strip()}%"
            query = query.where(
                or_(
                    Institution.name.ilike(term),
                    Institution.short_name.ilike(term),
                    Institution.city.ilike(term),
                    Institution.district.ilike(term),
                )
            )
        result = await self.db.execute(query)
        return result.scalar() or 0

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
        self,
        limit: int = 50,
        offset: int = 0,
        search: str | None = None,
    ) -> list[IndustryOrganization]:
        """
        List approved/platform-created industry organizations.
        Excludes pending and rejected requests.
        """
        query = select(IndustryOrganization).where(
            IndustryOrganization.is_active.is_(True),
            # Include: platform-created (request_status IS NULL) or approved
            or_(
                IndustryOrganization.request_status.is_(None),
                IndustryOrganization.request_status == "approved",
            ),
        )

        if search and search.strip():
            term = f"%{search.strip()}%"
            query = query.where(
                or_(
                    IndustryOrganization.name.ilike(term),
                    IndustryOrganization.industry_sector.ilike(term),
                    IndustryOrganization.headquarters_city.ilike(term),
                )
            )

        query = query.order_by(IndustryOrganization.name).limit(limit).offset(offset)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def create_request(
        self,
        name: str,
        requested_by_email: str,
        industry_sector: str | None = None,
        headquarters_city: str | None = None,
        website: str | None = None,
        request_notes: str | None = None,
    ) -> IndustryOrganization:
        """
        Create an IndustryOrganization in 'pending' state.
        Not shown to users until a SUPER_ADMIN approves it.
        """
        org = IndustryOrganization(
            name=name,
            industry_sector=industry_sector,
            headquarters_city=headquarters_city,
            website=website,
            is_active=False,   # Not active until approved
            is_verified=False,
            request_status="pending",
            requested_by_email=requested_by_email,
            request_notes=request_notes,
        )
        self.db.add(org)
        await self.db.flush()
        return org

    async def create(self, name: str, **kwargs) -> IndustryOrganization:
        org = IndustryOrganization(name=name, **kwargs)
        self.db.add(org)
        await self.db.flush()
        return org
