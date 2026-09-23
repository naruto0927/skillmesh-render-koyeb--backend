"""
SkillMesh API — Application Entry Point
Initializes FastAPI, configures CORS, mounts the API router,
and sets up startup/shutdown lifecycle hooks.
"""

import time
import uuid

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger, log_request_info

# ─── Bootstrap ────────────────────────────────────────────────────────────────
configure_logging()
settings = get_settings()
logger = get_logger(__name__)

# ─── Application ──────────────────────────────────────────────────────────────
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=(
        "SkillMesh — Evidence-backed competency intelligence platform. "
        "Connecting students, faculty, institutions, and industry. "
        "SIH 2026 — Problem Statement SIH26044."
    ),
    docs_url="/docs" if not settings.is_production else None,
    redoc_url="/redoc" if not settings.is_production else None,
    openapi_url="/openapi.json" if not settings.is_production else None,
)

# ─── CORS ─────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Request logging middleware ───────────────────────────────────────────────
@app.middleware("http")
async def request_logging_middleware(request: Request, call_next) -> Response:
    """
    Log every request with a unique request_id, method, path, status, and duration.
    Never logs sensitive headers like Authorization tokens.
    """
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    start = time.perf_counter()

    response = await call_next(request)

    duration_ms = (time.perf_counter() - start) * 1000
    log_request_info(
        logger=logger,
        request_id=request_id,
        method=request.method,
        path=request.url.path,
        status_code=response.status_code,
        duration_ms=duration_ms,
    )

    # Propagate request_id back to the client for traceability
    response.headers["X-Request-ID"] = request_id
    return response


# ─── Lifecycle hooks ──────────────────────────────────────────────────────────
@app.on_event("startup")
async def on_startup() -> None:
    logger.info(
        f"SkillMesh API starting | env={settings.environment} | version={settings.app_version}"
    )


@app.on_event("shutdown")
async def on_shutdown() -> None:
    logger.info("SkillMesh API shutting down")


# ─── Global exception handler ─────────────────────────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Catch-all handler for unhandled exceptions.
    Returns a generic error response — never exposes stack traces or internals.
    """
    request_id = getattr(request.state, "request_id", "unknown")
    logger.exception(
        f"Unhandled exception | request_id={request_id} | path={request.url.path}"
    )
    return JSONResponse(
        status_code=500,
        content={
            "error": "internal_server_error",
            "message": "An unexpected error occurred.",
            "request_id": request_id,
        },
    )


# ─── Routes ───────────────────────────────────────────────────────────────────
app.include_router(api_router)


# ─── Root ─────────────────────────────────────────────────────────────────────
@app.get("/", include_in_schema=False)
async def root():
    return {
        "service": "skillmesh-api",
        "version": settings.app_version,
        "status": "running",
        "docs": "/docs" if not settings.is_production else "disabled in production",
    }
