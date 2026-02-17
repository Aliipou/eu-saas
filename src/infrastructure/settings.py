"""Application settings loaded from environment variables via Pydantic."""

from __future__ import annotations

from pydantic_settings import BaseSettings


class AppSettings(BaseSettings):
    """Central configuration for the EU Multi-Tenant Cloud Platform."""

    model_config = {"env_prefix": "APP_", "case_sensitive": False}

    # Database
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "postgres"
    postgres_password: str = "postgres"
    postgres_db: str = "eu_multitenant"
    db_pool_size: int = 20
    db_max_overflow: int = 10

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # JWT
    jwt_private_key: str = ""
    jwt_public_key: str = ""
    jwt_issuer: str = "eu-multi-tenant-platform"
    jwt_access_token_minutes: int = 15
    jwt_refresh_token_days: int = 7

    # Celery
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    # Prometheus
    prometheus_url: str = "http://localhost:9090"

    # Logging
    log_level: str = "INFO"

    # CORS
    cors_origins: str = "*"


def get_settings() -> AppSettings:
    """Return the application settings singleton."""
    return AppSettings()
