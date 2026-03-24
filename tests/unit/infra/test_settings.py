"""Tests for application settings."""

from __future__ import annotations

from infrastructure.settings import AppSettings, get_settings


class TestAppSettings:
    def test_defaults_are_sane(self):
        s = AppSettings()
        assert s.postgres_host == "localhost"
        assert s.postgres_port == 5432
        assert s.postgres_user == "postgres"
        assert s.postgres_db == "eu_multitenant"
        assert s.db_pool_size == 20
        assert s.db_max_overflow == 10

    def test_redis_default(self):
        s = AppSettings()
        assert s.redis_url == "redis://localhost:6379/0"

    def test_jwt_defaults(self):
        s = AppSettings()
        assert s.jwt_private_key == ""
        assert s.jwt_public_key == ""
        assert s.jwt_issuer == "eu-multi-tenant-platform"
        assert s.jwt_access_token_minutes == 15
        assert s.jwt_refresh_token_days == 7

    def test_celery_defaults(self):
        s = AppSettings()
        assert s.celery_broker_url == "redis://localhost:6379/1"
        assert s.celery_result_backend == "redis://localhost:6379/2"

    def test_log_level_default(self):
        s = AppSettings()
        assert s.log_level == "INFO"

    def test_env_prefix_override(self, monkeypatch):
        monkeypatch.setenv("APP_POSTGRES_HOST", "db.prod.internal")
        monkeypatch.setenv("APP_POSTGRES_PORT", "5433")
        s = AppSettings()
        assert s.postgres_host == "db.prod.internal"
        assert s.postgres_port == 5433

    def test_log_level_override(self, monkeypatch):
        monkeypatch.setenv("APP_LOG_LEVEL", "DEBUG")
        s = AppSettings()
        assert s.log_level == "DEBUG"

    def test_redis_url_override(self, monkeypatch):
        monkeypatch.setenv("APP_REDIS_URL", "redis://redis.prod:6380/3")
        s = AppSettings()
        assert s.redis_url == "redis://redis.prod:6380/3"

    def test_get_settings_returns_app_settings(self):
        s = get_settings()
        assert isinstance(s, AppSettings)

    def test_cors_origins_default(self):
        s = AppSettings()
        assert s.cors_origins == "*"
