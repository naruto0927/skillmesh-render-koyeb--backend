"""
Tests for authentication endpoints.
Uses an in-memory SQLite DB for speed (or async PostgreSQL if available).
Supabase calls are mocked — we test our application logic, not Supabase.
"""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import Base, get_db
from app.main import app
from app.models import Institution, IndustryOrganization, User, UserRole

# Use SQLite for tests — fast and no external dependency
TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="function")
async def test_engine():
    engine = create_async_engine(TEST_DB_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture(scope="function")
async def db_session(test_engine):
    AsyncTestSession = async_sessionmaker(test_engine, expire_on_commit=False)
    async with AsyncTestSession() as session:
        yield session


@pytest.fixture(scope="function")
async def client(db_session: AsyncSession):
    """Override get_db to use test session."""

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest.fixture
async def institution(db_session: AsyncSession) -> Institution:
    inst = Institution(
        name="Test University",
        short_name="TU",
        city="Delhi",
        state="Delhi",
        is_active=True,
        is_verified=True,
    )
    db_session.add(inst)
    await db_session.commit()
    await db_session.refresh(inst)
    return inst


@pytest.fixture
async def industry_org(db_session: AsyncSession) -> IndustryOrganization:
    org = IndustryOrganization(
        name="Test Corp",
        industry_sector="Software",
        is_active=True,
        is_verified=True,
    )
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)
    return org


@pytest.fixture
async def student_user(db_session: AsyncSession, institution: Institution) -> User:
    user = User(
        supabase_uid=str(uuid.uuid4()),
        email="student@test.com",
        full_name="Test Student",
        role=UserRole.STUDENT,
        institution_id=institution.id,
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


# ─── Registration tests ────────────────────────────────────────────────────────

class TestRegister:
    @patch("app.services.auth_service.AuthService._create_supabase_user")
    async def test_register_student_success(
        self, mock_supabase, client: AsyncClient, institution: Institution
    ):
        mock_supabase.return_value = str(uuid.uuid4())

        response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "newstudent@test.com",
                "password": "SecurePass1",
                "full_name": "New Student",
                "role": "STUDENT",
                "institution_id": str(institution.id),
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["email"] == "newstudent@test.com"
        assert data["role"] == "STUDENT"
        assert "user_id" in data

    @patch("app.services.auth_service.AuthService._create_supabase_user")
    async def test_register_student_missing_institution(
        self, mock_supabase, client: AsyncClient
    ):
        mock_supabase.return_value = str(uuid.uuid4())

        response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "student2@test.com",
                "password": "SecurePass1",
                "full_name": "Student Two",
                "role": "STUDENT",
                # institution_id intentionally missing
            },
        )
        assert response.status_code == 422

    async def test_register_weak_password(
        self, client: AsyncClient, institution: Institution
    ):
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "student3@test.com",
                "password": "weak",
                "full_name": "Student Three",
                "role": "STUDENT",
                "institution_id": str(institution.id),
            },
        )
        assert response.status_code == 422

    async def test_register_password_no_uppercase(
        self, client: AsyncClient, institution: Institution
    ):
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "student4@test.com",
                "password": "lowercase123",
                "full_name": "Student Four",
                "role": "STUDENT",
                "institution_id": str(institution.id),
            },
        )
        assert response.status_code == 422

    async def test_register_invalid_institution_id(self, client: AsyncClient):
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "student5@test.com",
                "password": "SecurePass1",
                "full_name": "Student Five",
                "role": "STUDENT",
                "institution_id": str(uuid.uuid4()),  # Doesn't exist
            },
        )
        assert response.status_code == 404

    @patch("app.services.auth_service.AuthService._create_supabase_user")
    async def test_register_duplicate_email(
        self, mock_supabase, client: AsyncClient, student_user: User
    ):
        mock_supabase.return_value = str(uuid.uuid4())

        response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "student@test.com",  # Already exists
                "password": "SecurePass1",
                "full_name": "Duplicate",
                "role": "STUDENT",
                "institution_id": str(student_user.institution_id),
            },
        )
        assert response.status_code == 409

    @patch("app.services.auth_service.AuthService._create_supabase_user")
    async def test_register_recruiter_requires_industry_org(
        self, mock_supabase, client: AsyncClient, industry_org: IndustryOrganization
    ):
        mock_supabase.return_value = str(uuid.uuid4())

        response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "recruiter@corp.com",
                "password": "SecurePass1",
                "full_name": "Test Recruiter",
                "role": "RECRUITER",
                "industry_org_id": str(industry_org.id),
            },
        )
        assert response.status_code == 201
        assert response.json()["role"] == "RECRUITER"


# ─── Public endpoints ─────────────────────────────────────────────────────────

class TestPublicEndpoints:
    async def test_list_institutions(
        self, client: AsyncClient, institution: Institution
    ):
        response = await client.get("/api/v1/auth/institutions")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        assert data[0]["name"] == "Test University"

    async def test_list_organizations(
        self, client: AsyncClient, industry_org: IndustryOrganization
    ):
        response = await client.get("/api/v1/auth/organizations")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1


# ─── Protected endpoint tests ─────────────────────────────────────────────────

class TestProtectedEndpoints:
    async def test_me_without_token_returns_401(self, client: AsyncClient):
        response = await client.get("/api/v1/auth/me")
        assert response.status_code == 401

    async def test_logout_without_token_returns_401(self, client: AsyncClient):
        response = await client.post("/api/v1/auth/logout")
        assert response.status_code == 401

    async def test_update_profile_without_token_returns_401(self, client: AsyncClient):
        response = await client.patch(
            "/api/v1/users/me", json={"full_name": "New Name"}
        )
        assert response.status_code == 401
