"""
SkillMesh — Common Response Schemas
Standardized response envelopes used across all API endpoints.
"""

from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ErrorResponse(BaseModel):
    """Standard error response shape — consistent across all endpoints."""

    error: str          # Machine-readable error code, e.g. "invalid_credentials"
    message: str        # Human-readable message safe to show the user
    request_id: str | None = None


class SuccessResponse(BaseModel):
    """Simple success acknowledgment for operations that don't return data."""

    success: bool = True
    message: str


class PaginatedResponse(BaseModel, Generic[T]):
    """
    Generic paginated response wrapper.
    Usage: PaginatedResponse[UserPublic]
    """

    items: list[T]
    total: int
    page: int
    page_size: int
    has_next: bool
    has_prev: bool
