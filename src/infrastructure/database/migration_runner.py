"""
Tenant-aware Alembic migration runner.

Allows running Alembic migrations programmatically against individual
tenant schemas (via ``schema_translate_map``) or in parallel batches
across all tenants.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from alembic import command as alembic_command
from alembic.config import Config as AlembicConfig
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.engine import Engine

from .tenant_schema_manager import TenantSchemaManager

logger = logging.getLogger(__name__)

# Default location of the Alembic directory relative to project root.
_DEFAULT_ALEMBIC_DIR = Path(__file__).resolve().parents[3] / "alembic"
_DEFAULT_ALEMBIC_INI = _DEFAULT_ALEMBIC_DIR.parent / "alembic.ini"


def _tenant_schema_name(slug: str) -> str:
    return f"tenant_{slug.replace('-', '_')}"


@dataclass
class MigrationStatus:
    """Snapshot of migration state for a single tenant schema."""

    tenant_slug: str
    schema_name: str
    current_revision: Optional[str]
    head_revision: Optional[str]
    is_up_to_date: bool


class TenantMigrationRunner:
    """Run Alembic migrations against tenant-specific PostgreSQL schemas.

    Parameters
    ----------
    engine:
        A synchronous SQLAlchemy :class:`Engine`.
    alembic_cfg_path:
        Path to the ``alembic.ini`` file.  If *None* the default
        location is used.
    script_location:
        Alembic script (versions) directory.  If *None* the default
        location is used.
    """

    def __init__(
        self,
        engine: Engine,
        alembic_cfg_path: Optional[str] = None,
        script_location: Optional[str] = None,
    ) -> None:
        self._engine = engine
        self._alembic_cfg_path = alembic_cfg_path or str(_DEFAULT_ALEMBIC_INI)
        self._script_location = script_location or str(_DEFAULT_ALEMBIC_DIR)
        self._schema_manager = TenantSchemaManager(engine)

    # ------------------------------------------------------------------
    # Alembic config helpers
    # ------------------------------------------------------------------

    def _make_alembic_config(self, schema: str) -> AlembicConfig:
        """Build an :class:`AlembicConfig` that targets *schema*."""
        cfg = AlembicConfig(self._alembic_cfg_path)
        cfg.set_main_option("script_location", self._script_location)
        # Encode the target schema so Alembic uses the correct search_path.
        cfg.set_main_option("sqlalchemy.url", str(self._engine.url))
        cfg.attributes["schema"] = schema
        cfg.attributes["engine"] = self._engine
        return cfg

    def _get_script_directory(self) -> ScriptDirectory:
        cfg = AlembicConfig(self._alembic_cfg_path)
        cfg.set_main_option("script_location", self._script_location)
        return ScriptDirectory.from_config(cfg)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run_migrations(self, tenant_slug: str) -> None:
        """Apply all pending Alembic migrations to the given tenant schema.

        The ``search_path`` is set to the tenant schema before migration
        commands execute, ensuring that all DDL lands in the correct
        namespace.

        Parameters
        ----------
        tenant_slug:
            The unique slug identifying the tenant.
        """
        schema = _tenant_schema_name(tenant_slug)
        logger.info("Running migrations for schema %s", schema)

        with self._engine.begin() as conn:
            conn.execute(text(f"SET search_path TO {schema}, public"))

            context = MigrationContext.configure(
                conn,
                opts={"version_table_schema": schema},
            )
            current_rev = context.get_current_revision()

        cfg = self._make_alembic_config(schema)

        # Use env.py-compatible approach: stamp + upgrade
        with self._engine.begin() as conn:
            conn.execute(text(f"SET search_path TO {schema}, public"))
            cfg.attributes["connection"] = conn
            alembic_command.upgrade(cfg, "head")

        logger.info(
            "Migrations complete for schema %s (was at %s)",
            schema,
            current_rev,
        )

    def run_canary_migration(self, tenant_slug: str) -> None:
        """Apply migrations to a single "canary" tenant first.

        This is identical to :meth:`run_migrations` but is semantically
        distinct -- callers use this to validate a migration on one
        tenant before rolling it out to all tenants.

        Parameters
        ----------
        tenant_slug:
            The canary tenant's slug.
        """
        logger.info("Canary migration for tenant %s", tenant_slug)
        self.run_migrations(tenant_slug)
        logger.info("Canary migration succeeded for tenant %s", tenant_slug)

    def rollback_migration(self, tenant_slug: str, revision: str) -> None:
        """Downgrade a tenant schema to a specific Alembic revision.

        Parameters
        ----------
        tenant_slug:
            The unique slug identifying the tenant.
        revision:
            The target Alembic revision identifier (e.g. ``"abc123"`` or
            ``"-1"`` for one step back).
        """
        schema = _tenant_schema_name(tenant_slug)
        logger.info(
            "Rolling back schema %s to revision %s", schema, revision
        )

        cfg = self._make_alembic_config(schema)

        with self._engine.begin() as conn:
            conn.execute(text(f"SET search_path TO {schema}, public"))
            cfg.attributes["connection"] = conn
            alembic_command.downgrade(cfg, revision)

        logger.info("Rollback complete for schema %s", schema)

    def get_migration_status(self, tenant_slug: str) -> MigrationStatus:
        """Return the current migration status of a tenant schema.

        Parameters
        ----------
        tenant_slug:
            The unique slug identifying the tenant.

        Returns
        -------
        MigrationStatus
        """
        schema = _tenant_schema_name(tenant_slug)

        with self._engine.connect() as conn:
            conn.execute(text(f"SET search_path TO {schema}, public"))
            context = MigrationContext.configure(
                conn,
                opts={"version_table_schema": schema},
            )
            current_rev = context.get_current_revision()

        script = self._get_script_directory()
        head_rev = script.get_current_head()

        return MigrationStatus(
            tenant_slug=tenant_slug,
            schema_name=schema,
            current_revision=current_rev,
            head_revision=head_rev,
            is_up_to_date=(current_rev == head_rev),
        )

    def run_all_tenants(self, batch_size: int = 10) -> Dict[str, str]:
        """Run pending migrations across **all** tenant schemas in parallel.

        Parameters
        ----------
        batch_size:
            Maximum number of concurrent migration workers.

        Returns
        -------
        dict
            Mapping of ``schema_name -> "ok"`` or ``schema_name -> error_message``.
        """
        schemas = self._schema_manager.list_schemas()
        if not schemas:
            logger.info("No tenant schemas found; nothing to migrate.")
            return {}

        results: Dict[str, str] = {}

        def _migrate_one(schema_name: str) -> tuple[str, str]:
            # Derive slug back from schema name ("tenant_foo_bar" -> "foo_bar")
            slug = schema_name.removeprefix("tenant_")
            try:
                self.run_migrations(slug)
                return schema_name, "ok"
            except Exception as exc:
                logger.error(
                    "Migration failed for %s: %s", schema_name, exc
                )
                return schema_name, str(exc)

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=batch_size
        ) as executor:
            futures = {
                executor.submit(_migrate_one, s): s for s in schemas
            }
            for future in concurrent.futures.as_completed(futures):
                schema_name, status = future.result()
                results[schema_name] = status

        succeeded = sum(1 for v in results.values() if v == "ok")
        failed = len(results) - succeeded
        logger.info(
            "Batch migration complete: %d succeeded, %d failed out of %d",
            succeeded,
            failed,
            len(results),
        )
        return results
