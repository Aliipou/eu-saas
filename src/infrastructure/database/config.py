"""
Database configuration for the EU-Grade Multi-Tenant Cloud Platform.

Centralises all PostgreSQL connection settings, pool tuning parameters,
and URL builders for both synchronous (psycopg2) and asynchronous
(asyncpg) drivers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from typing import Optional


@dataclass(frozen=True)
class DatabaseSettings:
    """Immutable database connection and pool configuration.

    Values are typically sourced from environment variables at application
    start-up and injected here.  Defaults are suitable for local
    development; production deployments MUST override at minimum
    ``POSTGRES_HOST``, ``POSTGRES_USER``, ``POSTGRES_PASSWORD``, and
    ``POSTGRES_DB``.
    """

    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_DB: str = "eu_multitenant"

    # Connection-pool tuning
    POOL_SIZE: int = 20
    MAX_OVERFLOW: int = 10
    POOL_TIMEOUT: int = 30

    # Optional: SSL mode required for EU-grade production deployments
    SSL_MODE: Optional[str] = None


def get_database_url(settings: Optional[DatabaseSettings] = None) -> str:
    """Build a synchronous ``postgresql+psycopg2://`` DSN.

    Parameters
    ----------
    settings:
        An explicit :class:`DatabaseSettings` instance.  When *None* the
        default settings are used (suitable for local development).

    Returns
    -------
    str
        A fully-qualified SQLAlchemy database URL.
    """
    s = settings or DatabaseSettings()
    url = (
        f"postgresql+psycopg2://{s.POSTGRES_USER}:{s.POSTGRES_PASSWORD}"
        f"@{s.POSTGRES_HOST}:{s.POSTGRES_PORT}/{s.POSTGRES_DB}"
    )
    if s.SSL_MODE:
        url += f"?sslmode={s.SSL_MODE}"
    return url


def get_async_database_url(settings: Optional[DatabaseSettings] = None) -> str:
    """Build an asynchronous ``postgresql+asyncpg://`` DSN.

    Parameters
    ----------
    settings:
        An explicit :class:`DatabaseSettings` instance.  When *None* the
        default settings are used.

    Returns
    -------
    str
        A fully-qualified async SQLAlchemy database URL.
    """
    s = settings or DatabaseSettings()
    url = (
        f"postgresql+asyncpg://{s.POSTGRES_USER}:{s.POSTGRES_PASSWORD}"
        f"@{s.POSTGRES_HOST}:{s.POSTGRES_PORT}/{s.POSTGRES_DB}"
    )
    if s.SSL_MODE:
        url += f"?ssl={s.SSL_MODE}"
    return url


@lru_cache(maxsize=1)
def get_default_settings() -> DatabaseSettings:
    """Return a cached default :class:`DatabaseSettings` singleton.

    This is the recommended way to obtain settings throughout the
    application when no overrides are needed.
    """
    return DatabaseSettings()
