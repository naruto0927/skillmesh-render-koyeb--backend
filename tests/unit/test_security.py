"""
Tests for authorization logic — role enforcement, tenant isolation.
These test the security layer in isolation.
"""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from jose import jwt

from app.core.config import get_settings
from app.core.security import decode_jwt, require_role
from app.models.user import User, UserRole
from app.schemas.auth import TokenPayload

settings = get_settings()


def make_token(sub: str, exp_delta_seconds: int = 3600) -> str:
    """Generate a test JWT signed with the test JWT secret."""
    payload = {
        "sub": sub,
        "email": "test@example.com",
        "exp": int((datetime.now(timezone.utc) + timedelta(seconds=exp_delta_seconds)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


class TestDecodeJWT:
    def test_valid_token_decodes(self):
        sub = str(uuid.uuid4())
        token = make_token(sub)
        payload = decode_jwt(token)
        assert payload.sub == sub

    def test_expired_token_raises_401(self):
        token = make_token(sub=str(uuid.uuid4()), exp_delta_seconds=-1)
        with pytest.raises(HTTPException) as exc_info:
            decode_jwt(token)
        assert exc_info.value.status_code == 401

    def test_invalid_token_raises_401(self):
        with pytest.raises(HTTPException) as exc_info:
            decode_jwt("not.a.valid.jwt")
        assert exc_info.value.status_code == 401

    def test_wrong_secret_raises_401(self):
        payload = {
            "sub": str(uuid.uuid4()),
            "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
        }
        token = jwt.encode(payload, "wrong-secret", algorithm="HS256")
        with pytest.raises(HTTPException) as exc_info:
            decode_jwt(token)
        assert exc_info.value.status_code == 401


class TestRequireRole:
    def _make_user(self, role: UserRole) -> User:
        user = MagicMock(spec=User)
        user.role = role
        user.is_active = True
        return user

    async def test_correct_role_passes(self):
        user = self._make_user(UserRole.STUDENT)
        check_fn = require_role(UserRole.STUDENT)
        # Simulate FastAPI calling the dependency
        result = await check_fn(user=user)
        assert result is user

    async def test_wrong_role_raises_403(self):
        user = self._make_user(UserRole.STUDENT)
        check_fn = require_role(UserRole.SUPER_ADMIN)
        with pytest.raises(HTTPException) as exc_info:
            await check_fn(user=user)
        assert exc_info.value.status_code == 403

    async def test_multiple_roles_any_passes(self):
        user = self._make_user(UserRole.INSTITUTION_ADMIN)
        check_fn = require_role(UserRole.INSTITUTION_ADMIN, UserRole.SUPER_ADMIN)
        result = await check_fn(user=user)
        assert result is user

    async def test_multiple_roles_none_match_raises_403(self):
        user = self._make_user(UserRole.STUDENT)
        check_fn = require_role(UserRole.INSTITUTION_ADMIN, UserRole.SUPER_ADMIN)
        with pytest.raises(HTTPException) as exc_info:
            await check_fn(user=user)
        assert exc_info.value.status_code == 403
