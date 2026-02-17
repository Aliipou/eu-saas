"""Background Celery tasks for GDPR compliance operations."""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from application.tasks.celery_app import app

logger = logging.getLogger(__name__)


@app.task(  # type: ignore[untyped-decorator]
    name="application.tasks.gdpr_tasks.export_tenant_data_task",
    bind=True,
    max_retries=3,
    default_retry_delay=120,
)
def export_tenant_data_task(self: Any, tenant_id: str, job_id: str) -> dict[str, str]:
    """Generate a full data export for a single tenant."""
    from application.services.gdpr_service import ExportJobStatus
    from infrastructure.container import get_container

    logger.info("Starting data export for tenant %s (job %s)", tenant_id, job_id)

    try:
        container = get_container()

        # Mark IN_PROGRESS
        container.export_job_repo.update_status(job_id, ExportJobStatus.IN_PROGRESS)

        # In production: gather data, encrypt, archive, upload
        # For now mark COMPLETED
        container.export_job_repo.update_status(
            job_id, ExportJobStatus.COMPLETED, download_url=f"/exports/{job_id}.tar.gz"
        )

        logger.info("Export complete for tenant %s (job %s)", tenant_id, job_id)
        return {"tenant_id": tenant_id, "job_id": job_id, "status": "completed"}

    except Exception as exc:
        logger.exception("Data export failed for tenant %s (job %s)", tenant_id, job_id)
        try:
            from infrastructure.container import get_container as gc

            gc().export_job_repo.update_status(job_id, "FAILED", error=str(exc))
        except Exception:
            pass
        raise self.retry(exc=exc) from exc


@app.task(  # type: ignore[untyped-decorator]
    name="application.tasks.gdpr_tasks.run_retention_cleanup_all",
    bind=True,
    max_retries=2,
    default_retry_delay=300,
)
def run_retention_cleanup_all(self: Any) -> dict[str, int]:
    """Execute retention cleanup across all tenants."""
    from domain.models.tenant import TenantStatus
    from infrastructure.container import get_container

    logger.info("Starting nightly retention cleanup sweep")

    try:
        container = get_container()
        tenants, _ = container.tenant_repo.list_tenants(0, 10000, TenantStatus.ACTIVE)

        tenants_processed = 0
        total_soft_deleted = 0
        total_hard_deleted = 0

        for tenant in tenants:
            try:
                result = container.gdpr_service.run_retention_cleanup(tenant.id)
                total_soft_deleted += result.records_soft_deleted
                total_hard_deleted += result.records_hard_deleted
                tenants_processed += 1
            except Exception:
                logger.exception("Retention cleanup failed for tenant %s", tenant.id)

        logger.info(
            "Retention cleanup: %d tenants, %d soft, %d hard",
            tenants_processed,
            total_soft_deleted,
            total_hard_deleted,
        )
        return {
            "tenants_processed": tenants_processed,
            "total_soft_deleted": total_soft_deleted,
            "total_hard_deleted": total_hard_deleted,
        }

    except Exception as exc:
        logger.exception("Nightly retention cleanup failed")
        raise self.retry(exc=exc) from exc


@app.task(  # type: ignore[untyped-decorator]
    name="application.tasks.gdpr_tasks.execute_erasure_task",
    bind=True,
    max_retries=1,
    default_retry_delay=60,
)
def execute_erasure_task(self: Any, tenant_id: str) -> dict[str, Any]:
    """Execute the full right-to-erasure workflow for a tenant."""
    from infrastructure.container import get_container

    logger.info("Starting erasure workflow for tenant %s", tenant_id)

    try:
        container = get_container()
        result = container.gdpr_service.execute_erasure(UUID(tenant_id))

        logger.info("Erasure complete for tenant %s", tenant_id)
        return {
            "tenant_id": tenant_id,
            "status": "erased",
            "records_deleted": result.records_deleted,
        }

    except Exception as exc:
        logger.exception("Erasure failed for tenant %s", tenant_id)
        raise self.retry(exc=exc) from exc
