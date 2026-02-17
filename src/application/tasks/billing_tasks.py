"""Background Celery tasks for billing operations.

Scheduled tasks handle daily cost aggregation, anomaly detection, and
monthly invoice generation across all tenants.
"""

from __future__ import annotations

import calendar
import logging
from datetime import date, timedelta

from application.tasks.celery_app import app

logger = logging.getLogger(__name__)


@app.task(
    name="application.tasks.billing_tasks.aggregate_daily_costs",
    bind=True,
    max_retries=3,
    default_retry_delay=120,
)
def aggregate_daily_costs(self) -> dict:
    """Calculate and store cost records for all active tenants.

    Intended to run daily (e.g. via Celery Beat at 01:00 UTC).
    Processes yesterday's usage data so that the full day is captured.
    """
    target_date = date.today() - timedelta(days=1)
    logger.info("Aggregating daily costs for %s", target_date.isoformat())

    processed: int = 0
    errors: list[str] = []

    try:
        raise NotImplementedError(
            "Wire up DI container to resolve BillingService and tenant listing. "
            "This placeholder documents the expected aggregation flow."
        )
    except NotImplementedError:
        logger.info(
            "aggregate_daily_costs: "
            "1) list all ACTIVE tenants, "
            "2) for each tenant call billing_service.calculate_daily_costs(%s), "
            "3) collect results",
            target_date.isoformat(),
        )
        return {
            "date": target_date.isoformat(),
            "tenants_processed": processed,
            "errors": errors,
        }
    except Exception as exc:
        logger.exception("Daily cost aggregation failed")
        raise self.retry(exc=exc)


@app.task(
    name="application.tasks.billing_tasks.detect_anomalies",
    bind=True,
    max_retries=2,
    default_retry_delay=60,
)
def detect_anomalies(self) -> dict:
    """Run anomaly detection across all active tenants.

    Intended to run every 15 minutes via Celery Beat.  For each tenant,
    invokes ``BillingService.check_anomalies`` which examines a 7-day
    rolling cost window.
    """
    logger.info("Running anomaly detection sweep")

    total_anomalies: int = 0
    tenants_checked: int = 0

    try:
        raise NotImplementedError(
            "Wire up DI container to resolve BillingService and tenant listing. "
            "This placeholder documents the expected anomaly-detection flow."
        )
    except NotImplementedError:
        logger.info(
            "detect_anomalies: "
            "1) list all ACTIVE tenants, "
            "2) for each tenant call billing_service.check_anomalies(), "
            "3) aggregate results"
        )
        return {
            "tenants_checked": tenants_checked,
            "anomalies_found": total_anomalies,
        }
    except Exception as exc:
        logger.exception("Anomaly detection sweep failed")
        raise self.retry(exc=exc)


@app.task(
    name="application.tasks.billing_tasks.generate_monthly_invoices",
    bind=True,
    max_retries=3,
    default_retry_delay=300,
)
def generate_monthly_invoices(self) -> dict:
    """Generate invoices for all active tenants for the previous month.

    Intended to run on the 1st of each month via Celery Beat.
    """
    today = date.today()
    # Previous month boundaries
    first_of_this_month = today.replace(day=1)
    last_of_prev_month = first_of_this_month - timedelta(days=1)
    first_of_prev_month = last_of_prev_month.replace(day=1)

    logger.info(
        "Generating monthly invoices for period %s to %s",
        first_of_prev_month.isoformat(),
        last_of_prev_month.isoformat(),
    )

    invoices_generated: int = 0
    errors: list[str] = []

    try:
        raise NotImplementedError(
            "Wire up DI container to resolve BillingService and tenant listing. "
            "This placeholder documents the expected invoice generation flow."
        )
    except NotImplementedError:
        logger.info(
            "generate_monthly_invoices: "
            "1) list all ACTIVE tenants, "
            "2) for each tenant call billing_service.generate_invoice(%s, %s), "
            "3) collect results",
            first_of_prev_month.isoformat(),
            last_of_prev_month.isoformat(),
        )
        return {
            "period_start": first_of_prev_month.isoformat(),
            "period_end": last_of_prev_month.isoformat(),
            "invoices_generated": invoices_generated,
            "errors": errors,
        }
    except Exception as exc:
        logger.exception("Monthly invoice generation failed")
        raise self.retry(exc=exc)
