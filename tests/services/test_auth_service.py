"""
Unit tests for AuthService business logic.
Supabase HTTP calls are mocked — we test our application logic only.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import Base
from app.models import Institution, IndustryOrganization, User, UserRole
from app.schemas.auth import RegisterRequest
from app.services.auth_service import AuthService

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="function")
async def engine():
    eng = create_async_engine(TEST_DB_URL, echo=False)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await eng.dispose()


@pytest.fixture(scope="function")
async def db(engine):
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    async with SessionLocal() as session:
        yield session


@pytest.fixture
async def institution(db: AsyncSession) -> Institution:
    inst = Institution(
        name="Demo University",
        short_name="DU",
        is_active=True,
        is_verified=True,
    )
    db.add(inst)
    await db.commit()
    await db.refresh(inst)
    return inst


@pytest.fixture
async def industry_org(db: AsyncSession) -> IndustryOrganization:
    org = IndustryOrganization(
        name="Demo Corp",
        is_active=True,
        is_verified=True,
    )
    db.add(org)
    await db.commit()
    await db.refresh(org)
    return org


class TestAuthServiceRegistration:
    @patch("app.services.auth_service.AuthService._create_supabase_user")
    async def test_register_student_creates_user(
        self, mock_create: AsyncMock, db: AsyncSession, institution: Institution
    ):
        mock_create.return_value = str(uuid.uuid4())

        service = AuthService(db)
        request = RegisterRequest(
            email="student@demo.edu",
            password="SecurePass1",
            full_name="Demo Student",
            role=UserRole.STUDENT,
            institution_id=institution.id,
        )
        result = await service.register(request)

        assert result.email == "student@demo.edu"
        assert result.role == UserRole.STUDENT
        assert result.user_id is not None
        mock_create.assert_called_once()

    @patch("app.services.auth_service.AuthService._create_supabase_user")
    async def test_register_normalizes_email_to_lowercase(
        self, mock_create: AsyncMock, db: AsyncSession, institution: Institution
    ):
        mock_create.return_value = str(uuid.uuid4())

        service = AuthService(db)
        request = RegisterRequest(
            email="UPPER@Demo.EDU",
            password="SecurePass1",
            full_name="Upper Case",
            role=UserRole.STUDENT,
            institution_id=institution.id,
        )
        result = await service.register(request)
        assert result.email == "upper@demo.edu"

    @patch("app.services.auth_service.AuthService._create_supabase_user")
    async def test_register_duplicate_email_raises_409(
        self, mock_create: AsyncMock, db: AsyncSession, institution: Institution
    ):
        mock_create.return_value = str(uuid.uuid4())
        service = AuthService(db)

        request = RegisterRequest(
            email="dup@demo.edu",
            password="SecurePass1",
            full_name="First User",
            role=UserRole.STUDENT,
            institution_id=institution.id,
        )
        await service.register(request)

        mock_create.return_value = str(uuid.uuid4())
        with pytest.raises(HTTPException) as exc:
            await service.register(request)
        assert exc.value.status_code == 409

    async def test_register_student_without_institution_raises_422(
        self, db: AsyncSession
    ):
        service = AuthService(db)
        request = RegisterRequest(
            email="nostudent@demo.edu",
            password="SecurePass1",
            full_name="No Institution",
            role=UserRole.STUDENT,
            # institution_id missing
        )
        with pytest.raises(HTTPException) as exc:
            await service.register(request)
        assert exc.value.status_code == 422

    async def test_register_student_invalid_institution_raises_404(
        self, db: AsyncSession
    ):
        service = AuthService(db)
        request = RegisterRequest(
            email="ghost@demo.edu",
            password="SecurePass1",
            full_name="Ghost Student",
            role=UserRole.STUDENT,
            institution_id=uuid.uuid4(),  # doesn't exist
        )
        with pytest.raises(HTTPException) as exc:
            await service.register(request)
        assert exc.value.status_code == 404

    @patch("app.services.auth_service.AuthService._create_supabase_user")
    async def test_register_recruiter_with_org(
        self, mock_create: AsyncMock, db: AsyncSession, industry_org: IndustryOrganization
    ):
        mock_create.return_value = str(uuid.uuid4())
        service = AuthService(db)

        request = RegisterRequest(
            email="recruiter@corp.com",
            password="SecurePass1",
            full_name="Test Recruiter",
            role=UserRole.RECRUITER,
            industry_org_id=industry_org.id,
        )
        result = await service.register(request)
        assert result.role == UserRole.RECRUITER

    async def test_register_recruiter_without_org_raises_422(
        self, db: AsyncSession
    ):
        service = AuthService(db)
        request = RegisterRequest(
            email="recruiter2@corp.com",
            password="SecurePass1",
            full_name="No Org Recruiter",
            role=UserRole.RECRUITER,
        )
        with pytest.raises(HTTPException) as exc:
            await service.register(request)
        assert exc.value.status_code == 422
