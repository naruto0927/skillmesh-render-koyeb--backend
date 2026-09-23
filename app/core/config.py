"""
SkillMesh API — Application Configuration
All settings are read from environment variables.
Never hardcode secrets here.
"""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ─── Application ─────────────────────────────────────────────────────────
    environment: Literal["development", "staging", "production"] = "development"
    app_name: str = "SkillMesh API"
    app_version: str = "0.1.0"
    debug: bool = False

    # ─── Database ─────────────────────────────────────────────────────────────
    database_url: str = (
        "postgresql+asyncpg://skillmesh:skillmesh_dev_password@localhost:5432/skillmesh_dev"
    )

    # ─── Supabase ─────────────────────────────────────────────────────────────
    supabase_url: str = ""
    supabase_anon_key: str = ""
    # Service role key is server-side only — never expose to frontend
    supabase_service_role_key: str = ""

    # ─── Security ─────────────────────────────────────────────────────────────
    jwt_secret: str = "change-this-secret-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    # ─── CORS ─────────────────────────────────────────────────────────────────
    cors_origins: str = "http://localhost:3000"

    # ─── Server ───────────────────────────────────────────────────────────────
    port: int = 8000

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse comma-separated CORS origins into a list."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def is_development(self) -> bool:
        return self.environment == "development"


@lru_cache
def get_settings() -> Settings:
    """
    Return a cached Settings instance.
    lru_cache ensures settings are read once and reused throughout the app.
    """
    return Settings()
