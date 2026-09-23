"""
Tests for the Settings configuration.
"""

from app.core.config import get_settings


class TestSettings:
    def test_settings_loads(self):
        settings = get_settings()
        assert settings is not None

    def test_cors_origins_list_parses_correctly(self):
        settings = get_settings()
        origins = settings.cors_origins_list
        assert isinstance(origins, list)
        assert len(origins) >= 1

    def test_environment_is_valid(self):
        settings = get_settings()
        assert settings.environment in ("development", "staging", "production")

    def test_app_name(self):
        settings = get_settings()
        assert settings.app_name == "SkillMesh API"

    def test_app_version_exists(self):
        settings = get_settings()
        assert settings.app_version
        assert "." in settings.app_version  # e.g. "0.1.0"
