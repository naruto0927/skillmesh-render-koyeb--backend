"""SkillMesh API — v1 Router"""

from fastapi import APIRouter

from app.api.v1.routes.health import router as health_router
from app.api.v1.routes.auth import router as auth_router
from app.api.v1.routes.users import router as users_router
from app.api.v1.routes.skills import router as skills_router
from app.api.v1.routes.assessments import router as assessments_router
from app.api.v1.routes.evidence import router as evidence_router
from app.api.v1.routes.gap import router as gap_router
from app.api.v1.routes.learning import router as learning_router

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(health_router)
api_router.include_router(auth_router, prefix="/auth")
api_router.include_router(users_router, prefix="/users")
api_router.include_router(skills_router)
api_router.include_router(assessments_router, prefix="/assessments")
api_router.include_router(evidence_router)
api_router.include_router(gap_router)
api_router.include_router(learning_router)
