"""
Tests for the health endpoints.
These are the first tests — they verify the API is wired up correctly
and the health endpoints return the expected shape and values.
"""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
async def client():
    """Provide an async test client for the FastAPI application."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


class TestHealthEndpoint:
    async def test_health_returns_200(self, client: AsyncClient):
        response = await client.get("/api/v1/health")
        assert response.status_code == 200

    async def test_health_response_shape(self, client: AsyncClient):
        response = await client.get("/api/v1/health")
        data = response.json()
        assert "status" in data
        assert "service" in data
        assert "version" in data
        assert "environment" in data

    async def test_health_status_is_ok(self, client: AsyncClient):
        response = await client.get("/api/v1/health")
        data = response.json()
        assert data["status"] == "ok"

    async def test_health_service_name(self, client: AsyncClient):
        response = await client.get("/api/v1/health")
        data = response.json()
        assert data["service"] == "skillmesh-api"

    async def test_health_does_not_expose_secrets(self, client: AsyncClient):
        response = await client.get("/api/v1/health")
        body = response.text
        # Ensure no secret-like values are leaked
        assert "password" not in body.lower()
        assert "secret" not in body.lower()
        assert "token" not in body.lower()
        assert "key" not in body.lower()

    async def test_health_response_has_request_id_header(self, client: AsyncClient):
        response = await client.get("/api/v1/health")
        assert "x-request-id" in response.headers

    async def test_root_endpoint(self, client: AsyncClient):
        response = await client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["service"] == "skillmesh-api"
        assert "status" in data


class TestHealthDbEndpoint:
    async def test_health_db_returns_200_or_200_degraded(self, client: AsyncClient):
        """
        /health/db may return 'degraded' if DB is unreachable in test environment.
        We only assert it doesn't crash (500).
        """
        response = await client.get("/api/v1/health/db")
        assert response.status_code == 200

    async def test_health_db_response_shape(self, client: AsyncClient):
        response = await client.get("/api/v1/health/db")
        data = response.json()
        assert "status" in data
        assert "service" in data
        assert "database" in data

    async def test_health_db_database_field_is_valid(self, client: AsyncClient):
        response = await client.get("/api/v1/health/db")
        data = response.json()
        assert data["database"] in ("ok", "unreachable")
