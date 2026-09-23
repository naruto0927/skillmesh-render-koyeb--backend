"""
SkillMesh API — Logging Configuration
Structured logging suitable for production observability.
Never log passwords, tokens, or secrets.
"""

import logging
import sys
from typing import Any

from app.core.config import get_settings

settings = get_settings()


def configure_logging() -> None:
    """Configure application-wide logging."""
    log_level = logging.DEBUG if settings.is_development else logging.INFO

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        stream=sys.stdout,
    )

    # Suppress noisy third-party loggers in production
    if settings.is_production:
        logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
        logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Return a named logger for use within a module."""
    return logging.getLogger(name)


def log_request_info(
    logger: logging.Logger,
    request_id: str,
    method: str,
    path: str,
    status_code: int,
    duration_ms: float,
    user_id: str | None = None,
) -> None:
    """
    Log structured request information.
    user_id is included where available for traceability.
    Sensitive data (tokens, passwords) must never be passed here.
    """
    fields: dict[str, Any] = {
        "request_id": request_id,
        "method": method,
        "path": path,
        "status_code": status_code,
        "duration_ms": round(duration_ms, 2),
        "environment": settings.environment,
    }
    if user_id:
        fields["user_id"] = user_id

    logger.info(" | ".join(f"{k}={v}" for k, v in fields.items()))
