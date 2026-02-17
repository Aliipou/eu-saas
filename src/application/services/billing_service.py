"""Billing application service.

Coordinates usage recording, daily cost aggregation, invoice generation,
and cost-anomaly detection.  Delegates pricing logic to the domain-layer
:class:`CostCalculator`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Protocol
from uuid import UUID, uuid4

from domain.models.audit import AuditAction, AuditEntry
from domain.models.billing import (
    CostAnomaly,
    CostRecord,
    Invoice,
    ResourceType,
    UsageRecord,
)

if TYPE_CHECKING:
    from domain.services.cost_calculator import CostCalculator

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Value objects returned by service methods
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CostBreakdown:
    """Aggregated cost view for a date range."""

    tenant_id: UUID
    start_date: date
    end_date: date
    by_resource: dict[str, Decimal] = field(default_factory=dict)
    total: Decimal = Decimal("0")
    currency: str = "EUR"


@dataclass(frozen=True)
class CostProjection:
    """Projected monthly cost based on current month's data."""

    tenant_id: UUID
    month: int
    year: int
    days_elapsed: int
    days_in_month: int
    actual_cost: Decimal = Decimal("0")
    projected_cost: Decimal = Decimal("0")
    currency: str = "EUR"


# ---------------------------------------------------------------------------
# Repository / infrastructure port interfaces
# ---------------------------------------------------------------------------


class UsageRepository(Protocol):
    """Port: persistence for usage records."""

    def save(self, record: UsageRecord) -> UsageRecord: ...

    def get_by_tenant_and_date(
        self,
        tenant_id: UUID,
        target_date: date,
    ) -> list[UsageRecord]: ...

    def get_by_tenant_and_range(
        self,
        tenant_id: UUID,
        start_date: date,
        end_date: date,
    ) -> list[UsageRecord]: ...


class CostRepository(Protocol):
    """Port: persistence for cost records."""

    def save(self, record: CostRecord) -> CostRecord: ...

    def save_many(self, records: list[CostRecord]) -> list[CostRecord]: ...

    def get_by_tenant_and_date(
        self,
        tenant_id: UUID,
        target_date: date,
    ) -> list[CostRecord]: ...

    def get_by_tenant_and_range(
        self,
        tenant_id: UUID,
        start_date: date,
        end_date: date,
    ) -> list[CostRecord]: ...


class InvoiceRepository(Protocol):
    """Port: persistence for invoices."""

    def save(self, invoice: Invoice) -> Invoice: ...

    def get_by_tenant_and_period(
        self,
        tenant_id: UUID,
        period_start: date,
        period_end: date,
    ) -> Invoice | None: ...


class AnomalyRepository(Protocol):
    """Port: persistence for cost anomalies."""

    def save(self, anomaly: CostAnomaly) -> CostAnomaly: ...

    def save_many(self, anomalies: list[CostAnomaly]) -> list[CostAnomaly]: ...

    def get_recent_by_tenant(
        self,
        tenant_id: UUID,
        days: int = 7,
    ) -> list[CostAnomaly]: ...


class AuditRepository(Protocol):
    """Port: tamper-evident audit entries."""

    def get_latest_entry(self, tenant_id: UUID) -> AuditEntry | None: ...

    def save(self, entry: AuditEntry) -> AuditEntry: ...


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class BillingService:
    """Orchestrates usage metering, cost calculation, and invoicing."""

    def __init__(
        self,
        usage_repo: UsageRepository,
        cost_repo: CostRepository,
        invoice_repo: InvoiceRepository,
        anomaly_repo: AnomalyRepository,
        audit_repo: AuditRepository,
        cost_calculator: CostCalculator,
    ) -> None:
        self._usage_repo = usage_repo
        self._cost_repo = cost_repo
        self._invoice_repo = invoice_repo
        self._anomaly_repo = anomaly_repo
        self._audit_repo = audit_repo
        self._calculator = cost_calculator

    # -- helpers ----------------------------------------------------------

    def _create_audit_entry(
        self,
        tenant_id: UUID,
        action: AuditAction,
        details: dict[str, Any] | None = None,
    ) -> AuditEntry:
        latest = self._audit_repo.get_latest_entry(tenant_id)
        previous_hash = latest.entry_hash if latest else ""
        entry = AuditEntry(
            id=uuid4(),
            tenant_id=tenant_id,
            action=action,
            actor_id=UUID(int=0),
            details=details or {},
            timestamp=datetime.now(UTC),
            previous_hash=previous_hash,
        )
        return self._audit_repo.save(entry)

    # -- public API -------------------------------------------------------

    def record_usage(
        self,
        tenant_id: UUID,
        resource_type: ResourceType,
        quantity: Decimal,
        unit: str,
    ) -> UsageRecord:
        """Persist a single usage metering event."""
        record = UsageRecord(
            id=uuid4(),
            tenant_id=tenant_id,
            resource_type=resource_type,
            quantity=quantity,
            unit=unit,
            recorded_at=datetime.now(UTC),
        )
        return self._usage_repo.save(record)

    def calculate_daily_costs(
        self,
        tenant_id: UUID,
        target_date: date,
    ) -> list[CostRecord]:
        """Aggregate usage for a given day and produce cost records.

        Groups usage by resource type, applies the pricing model via
        :class:`CostCalculator`, and persists the resulting cost records.
        """
        usage_records = self._usage_repo.get_by_tenant_and_date(tenant_id, target_date)

        # Aggregate quantities per resource type
        aggregated: dict[ResourceType, Decimal] = {}
        for rec in usage_records:
            aggregated[rec.resource_type] = (
                aggregated.get(rec.resource_type, Decimal("0")) + rec.quantity
            )

        cost_records: list[CostRecord] = []
        for resource_type, total_quantity in aggregated.items():
            unit_price = self._calculator.calculate_cost(resource_type, Decimal("1"))
            total_cost = self._calculator.calculate_cost(resource_type, total_quantity)
            cost_records.append(
                CostRecord(
                    id=uuid4(),
                    tenant_id=tenant_id,
                    date=target_date,
                    resource_type=resource_type,
                    quantity=total_quantity,
                    unit_price=unit_price,
                    total_cost=total_cost,
                    currency="EUR",
                )
            )

        if cost_records:
            cost_records = self._cost_repo.save_many(cost_records)

        return cost_records

    def get_cost_breakdown(
        self,
        tenant_id: UUID,
        start_date: date,
        end_date: date,
    ) -> CostBreakdown:
        """Return an aggregated cost breakdown for a date range."""
        records = self._cost_repo.get_by_tenant_and_range(tenant_id, start_date, end_date)

        by_resource: dict[str, Decimal] = {}
        total = Decimal("0")
        for rec in records:
            key = rec.resource_type.value
            by_resource[key] = by_resource.get(key, Decimal("0")) + rec.total_cost
            total += rec.total_cost

        return CostBreakdown(
            tenant_id=tenant_id,
            start_date=start_date,
            end_date=end_date,
            by_resource=by_resource,
            total=total,
        )

    def project_monthly_cost(self, tenant_id: UUID) -> CostProjection:
        """Project full-month costs from the current month's actuals."""
        import calendar

        today = date.today()
        month_start = today.replace(day=1)
        days_in_month = calendar.monthrange(today.year, today.month)[1]
        days_elapsed = today.day

        records = self._cost_repo.get_by_tenant_and_range(tenant_id, month_start, today)
        actual = sum((r.total_cost for r in records), Decimal("0"))

        projected = actual / days_elapsed * days_in_month if days_elapsed > 0 else Decimal("0")

        return CostProjection(
            tenant_id=tenant_id,
            month=today.month,
            year=today.year,
            days_elapsed=days_elapsed,
            days_in_month=days_in_month,
            actual_cost=actual.quantize(Decimal("0.01")),
            projected_cost=projected.quantize(Decimal("0.01")),
        )

    def generate_invoice(
        self,
        tenant_id: UUID,
        period_start: date,
        period_end: date,
    ) -> Invoice:
        """Generate an invoice for the given billing period."""
        records = self._cost_repo.get_by_tenant_and_range(tenant_id, period_start, period_end)

        line_items: list[dict[str, Any]] = []
        total_amount = Decimal("0")
        for rec in records:
            line_items.append(
                {
                    "resource_type": rec.resource_type.value,
                    "date": rec.date.isoformat(),
                    "quantity": str(rec.quantity),
                    "unit_price": str(rec.unit_price),
                    "total_cost": str(rec.total_cost),
                    "currency": rec.currency,
                }
            )
            total_amount += rec.total_cost

        invoice = Invoice(
            id=uuid4(),
            tenant_id=tenant_id,
            period_start=period_start,
            period_end=period_end,
            line_items=line_items,
            total_amount=total_amount.quantize(Decimal("0.01")),
            currency="EUR",
            status="DRAFT",
            generated_at=datetime.now(UTC),
        )
        invoice = self._invoice_repo.save(invoice)

        self._create_audit_entry(
            tenant_id=tenant_id,
            action=AuditAction.TENANT_UPDATED,
            details={
                "event": "invoice_generated",
                "invoice_id": str(invoice.id),
                "total_amount": str(invoice.total_amount),
                "period": f"{period_start.isoformat()} - {period_end.isoformat()}",
            },
        )
        logger.info("Invoice %s generated for tenant %s", invoice.id, tenant_id)
        return invoice

    def check_anomalies(self, tenant_id: UUID) -> list[CostAnomaly]:
        """Run anomaly detection across resource types using a 7-day rolling window.

        Returns any newly detected anomalies.
        """
        today = date.today()
        window_start = today - timedelta(days=7)

        cost_records = self._cost_repo.get_by_tenant_and_range(tenant_id, window_start, today)

        # Organise daily totals per resource type
        daily_totals: dict[ResourceType, dict[date, Decimal]] = {}
        for rec in cost_records:
            rt_map = daily_totals.setdefault(rec.resource_type, {})
            rt_map[rec.date] = rt_map.get(rec.date, Decimal("0")) + rec.total_cost

        new_anomalies: list[CostAnomaly] = []
        for resource_type, date_map in daily_totals.items():
            sorted_dates = sorted(date_map.keys())
            if len(sorted_dates) < 2:
                continue

            # Historical = all days except today; current = today
            historical_values = [float(date_map[d]) for d in sorted_dates if d != today]
            current_value = float(date_map.get(today, Decimal("0")))

            if not historical_values:
                continue

            anomaly = self._calculator.detect_anomaly(current_value, historical_values)
            if anomaly is not None:
                anomaly.tenant_id = tenant_id
                anomaly.resource_type = resource_type
                new_anomalies.append(anomaly)

        if new_anomalies:
            new_anomalies = self._anomaly_repo.save_many(new_anomalies)
            self._create_audit_entry(
                tenant_id=tenant_id,
                action=AuditAction.COST_ANOMALY_DETECTED,
                details={
                    "anomaly_count": len(new_anomalies),
                    "resource_types": [a.resource_type.value for a in new_anomalies],
                },
            )

        return new_anomalies
