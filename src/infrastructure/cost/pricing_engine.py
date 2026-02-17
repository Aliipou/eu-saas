"""
Pricing engine for tenant resource consumption.

Applies configurable per-unit rates to usage quantities and produces
line items, period totals, and monthly projections. All monetary values
are in EUR.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

# ======================================================================
# Resource types
# ======================================================================


class ResourceType(str, Enum):
    CPU = "cpu"  # unit: vCPU-hour
    MEMORY = "memory"  # unit: GB-hour
    STORAGE = "storage"  # unit: GB-day
    NETWORK = "network"  # unit: GB
    API_CALLS = "api_calls"  # unit: call


# ======================================================================
# Default pricing (EUR per unit)
# ======================================================================

DEFAULT_PRICING: dict[ResourceType, float] = {
    ResourceType.CPU: 0.02,  # EUR per vCPU-hour
    ResourceType.MEMORY: 0.005,  # EUR per GB-hour
    ResourceType.STORAGE: 0.01,  # EUR per GB-day
    ResourceType.NETWORK: 0.001,  # EUR per GB
    ResourceType.API_CALLS: 0.0001,  # EUR per call
}


# ======================================================================
# Result data structures
# ======================================================================


@dataclass(frozen=True)
class LineItem:
    """A single billable line on an invoice."""

    resource_type: ResourceType
    quantity: float
    unit_price: float
    total: float


@dataclass(frozen=True)
class UsageRecord:
    """Raw usage entry fed into the pricing engine."""

    resource_type: ResourceType
    quantity: float


@dataclass(frozen=True)
class PeriodCost:
    """Aggregated cost for a billing period."""

    line_items: list[LineItem]
    total: float
    currency: str = "EUR"


@dataclass(frozen=True)
class ProjectedCost:
    """Extrapolated monthly cost based on partial-period usage."""

    current_total: float
    projected_total: float
    days_elapsed: int
    days_in_month: int
    currency: str = "EUR"


# ======================================================================
# Pricing engine
# ======================================================================


class PricingEngine:
    """
    Stateless calculator that turns usage records into costs.

    Accepts optional custom pricing overrides; falls back to
    ``DEFAULT_PRICING`` for any resource type not explicitly overridden.
    """

    def __init__(
        self,
        pricing: dict[ResourceType, float] | None = None,
    ) -> None:
        self._pricing: dict[ResourceType, float] = {**DEFAULT_PRICING}
        if pricing:
            self._pricing.update(pricing)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def calculate_line_item(
        self,
        resource_type: ResourceType,
        quantity: float,
        custom_price: float | None = None,
    ) -> LineItem:
        """
        Calculate cost for a single resource type and quantity.

        Parameters
        ----------
        resource_type:
            The kind of resource consumed.
        quantity:
            Amount consumed in the resource's native unit.
        custom_price:
            Optional per-unit price override for this line item only.
        """

        unit_price = custom_price if custom_price is not None else self._pricing[resource_type]
        total = round(quantity * unit_price, 6)

        return LineItem(
            resource_type=resource_type,
            quantity=quantity,
            unit_price=unit_price,
            total=total,
        )

    def calculate_period_cost(
        self,
        usage_records: Sequence[UsageRecord],
        pricing: dict[ResourceType, float] | None = None,
    ) -> PeriodCost:
        """
        Aggregate multiple usage records into a single ``PeriodCost``.

        Parameters
        ----------
        usage_records:
            One or more raw usage entries for the billing period.
        pricing:
            Optional pricing overrides applied for this calculation only.
        """

        effective_pricing = {**self._pricing}
        if pricing:
            effective_pricing.update(pricing)

        line_items: list[LineItem] = []
        for record in usage_records:
            unit_price = effective_pricing.get(record.resource_type, 0.0)
            item = LineItem(
                resource_type=record.resource_type,
                quantity=record.quantity,
                unit_price=unit_price,
                total=round(record.quantity * unit_price, 6),
            )
            line_items.append(item)

        total = round(sum(item.total for item in line_items), 6)
        return PeriodCost(line_items=line_items, total=total)

    def project_monthly_cost(
        self,
        current_usage: Sequence[UsageRecord],
        days_elapsed: int,
        days_in_month: int,
    ) -> ProjectedCost:
        """
        Extrapolate the current partial-month usage to a full-month estimate.

        Uses simple linear projection: ``projected = current * (days_in_month / days_elapsed)``.
        """

        if days_elapsed <= 0:
            raise ValueError("days_elapsed must be positive")
        if days_in_month <= 0:
            raise ValueError("days_in_month must be positive")

        period = self.calculate_period_cost(current_usage)
        factor = days_in_month / days_elapsed
        projected = round(period.total * factor, 6)

        return ProjectedCost(
            current_total=period.total,
            projected_total=projected,
            days_elapsed=days_elapsed,
            days_in_month=days_in_month,
        )
