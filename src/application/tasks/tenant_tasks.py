"""Background Celery tasks for tenant provisioning and deprovisioning."""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from application.tasks.celery_app import app

logger = logging.getLogger(__name__)


@app.task(  # type: ignore[untyped-decorator]
    name="application.tasks.tenant_tasks.provision_tenant_async",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
)
def provision_tenant_async(self: Any, tenant_id: str) -> dict[str, str]:
    """Asynchronously provision a tenant's infrastructure."""
    from infrastructure.container import get_container

    logger.info("Starting async provisioning for tenant %s", tenant_id)

    try:
        container = get_container()
        service = container.tenant_service
        tenant = service.get_tenant(UUID(tenant_id))

        from domain.models.tenant import TenantStatus

        # Transition PENDING -> PROVISIONING
        if tenant.status == TenantStatus.PENDING:
            service._transition(tenant, TenantStatus.PROVISIONING)

        # Create schema + run migrations
        container.schema_manager.create_schema(tenant.schema_name)
        container.schema_manager.run_migrations(tenant.schema_name)

        # Transition PROVISIONING -> ACTIVE
        tenant = service.get_tenant(UUID(tenant_id))
        if tenant.status == TenantStatus.PROVISIONING:
            service._transition(tenant, TenantStatus.ACTIVE)

        logger.info("Provisioning complete for tenant %s", tenant_id)
        return {"tenant_id": tenant_id, "status": "provisioned"}

    except Exception as exc:
        logger.exception("Provisioning failed for tenant %s", tenant_id)
        raise self.retry(exc=exc) from exc


@app.task(  # type: ignore[untyped-decorator]
    name="application.tasks.tenant_tasks.deprovision_tenant_async",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def deprovision_tenant_async(self: Any, tenant_id: str) -> dict[str, str]:
    """Asynchronously deprovision a tenant."""
    from infrastructure.container import get_container

    logger.info("Starting async deprovisioning for tenant %s", tenant_id)

    try:
        container = get_container()
        service = container.tenant_service
        tenant = service.get_tenant(UUID(tenant_id))

        # Drop schema, purge caches
        container.schema_manager.drop_schema(tenant.schema_name)
        container.cache_manager.purge_tenant(UUID(tenant_id))

        # Transition to DELETED
        from domain.models.tenant import TenantStatus

        if tenant.status == TenantStatus.DEPROVISIONING:
            service._transition(tenant, TenantStatus.DELETED)

        from domain.models.audit import AuditAction

        service._create_audit_entry(
            tenant_id=UUID(tenant_id),
            action=AuditAction.TENANT_DELETED,
            details={"action": "deprovisioned"},
        )

        logger.info("Deprovisioning complete for tenant %s", tenant_id)
        return {"tenant_id": tenant_id, "status": "deprovisioned"}

    except Exception as exc:
        logger.exception("Deprovisioning failed for tenant %s", tenant_id)
        raise self.retry(exc=exc) from exc


@app.task(  # type: ignore[untyped-decorator]
    name="application.tasks.tenant_tasks.run_tenant_migrations",
    bind=True,
    max_retries=2,
    default_retry_delay=30,
)
def run_tenant_migrations(self: Any, tenant_slug: str) -> dict[str, str]:
    """Run database migrations for a single tenant schema."""
    from infrastructure.container import get_container

    schema_name = f"tenant_{tenant_slug.replace('-', '_')}"
    logger.info("Running migrations for schema %s", schema_name)

    try:
        container = get_container()
        container.schema_manager.run_migrations(schema_name)
        logger.info("Migrations complete for schema %s", schema_name)
        return {"tenant_slug": tenant_slug, "schema": schema_name, "status": "migrated"}
    except Exception as exc:
        logger.exception("Migrations failed for schema %s", schema_name)
        raise self.retry(exc=exc) from exc
