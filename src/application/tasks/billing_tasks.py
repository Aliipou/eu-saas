"""Background Celery tasks for billing operations."""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

from application.tasks.celery_app import app

logger = logging.getLogger(__name__)


@app.task(  # type: ignore[untyped-decorator]
    name="application.tasks.billing_tasks.aggregate_daily_costs",
    bind=True,
    max_retries=3,
    default_retry_delay=120,
)
def aggregate_daily_costs(self: Any) -> dict[str, Any]:
    """Calculate and store cost records for all active tenants."""
    from domain.models.tenant import TenantStatus
    from infrastructure.container import get_container

    target_date = date.today() - timedelta(days=1)
    logger.info("Aggregating daily costs for %s", target_date.isoformat())

    try:
        container = get_container()
        tenants, _ = container.tenant_repo.list_tenants(0, 10000, TenantStatus.ACTIVE)
        processed = 0
        errors: list[str] = []

        for tenant in tenants:
            try:
                container.billing_service.calculate_daily_costs(tenant.id, target_date)
                processed += 1
            except Exception as exc:
                errors.append(f"{tenant.id}: {exc}")

        logger.info("Daily costs aggregated: %d processed, %d errors", processed, len(errors))
        return {"date": target_date.isoformat(), "tenants_processed": processed, "errors": errors}

    except Exception as exc:
        logger.exception("Daily cost aggregation failed")
        raise self.retry(exc=exc) from exc


@app.task(  # type: ignore[untyped-decorator]
    name="application.tasks.billing_tasks.detect_anomalies",
    bind=True,
    max_retries=2,
    default_retry_delay=60,
)
def detect_anomalies(self: Any) -> dict[str, Any]:
    """Run anomaly detection across all active tenants."""
    from domain.models.tenant import TenantStatus
    from infrastructure.container import get_container

    logger.info("Running anomaly detection sweep")

    try:
        container = get_container()
        tenants, _ = container.tenant_repo.list_tenants(0, 10000, TenantStatus.ACTIVE)
        total_anomalies = 0
        tenants_checked = 0

        for tenant in tenants:
            try:
                anomalies = container.billing_service.check_anomalies(tenant.id)
                total_anomalies += len(anomalies)
                tenants_checked += 1
            except Exception:
                logger.exception("Anomaly check failed for tenant %s", tenant.id)

        logger.info("Anomaly sweep: %d checked, %d anomalies", tenants_checked, total_anomalies)
        return {"tenants_checked": tenants_checked, "anomalies_found": total_anomalies}

    except Exception as exc:
        logger.exception("Anomaly detection sweep failed")
        raise self.retry(exc=exc) from exc


@app.task(  # type: ignore[untyped-decorator]
    name="application.tasks.billing_tasks.generate_monthly_invoices",
    bind=True,
    max_retries=3,
    default_retry_delay=300,
)
def generate_monthly_invoices(self: Any) -> dict[str, Any]:
    """Generate invoices for all active tenants for the previous month."""
    from domain.models.tenant import TenantStatus
    from infrastructure.container import get_container

    today = date.today()
    first_of_this_month = today.replace(day=1)
    last_of_prev_month = first_of_this_month - timedelta(days=1)
    first_of_prev_month = last_of_prev_month.replace(day=1)

    logger.info("Generating invoices for %s to %s", first_of_prev_month, last_of_prev_month)

    try:
        container = get_container()
        tenants, _ = container.tenant_repo.list_tenants(0, 10000, TenantStatus.ACTIVE)
        invoices_generated = 0
        errors: list[str] = []

        for tenant in tenants:
            try:
                container.billing_service.generate_invoice(
                    tenant.id, first_of_prev_month, last_of_prev_month
                )
                invoices_generated += 1
            except Exception as exc:
                errors.append(f"{tenant.id}: {exc}")

        logger.info("Invoices: %d generated, %d errors", invoices_generated, len(errors))
        return {
            "period_start": first_of_prev_month.isoformat(),
            "period_end": last_of_prev_month.isoformat(),
            "invoices_generated": invoices_generated,
            "errors": errors,
        }

    except Exception as exc:
        logger.exception("Monthly invoice generation failed")
        raise self.retry(exc=exc) from exc
