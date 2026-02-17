"""Tests for infrastructure.cost.pricing_engine."""

from __future__ import annotations

import pytest

from infrastructure.cost.pricing_engine import (
    DEFAULT_PRICING,
    LineItem,
    PeriodCost,
    PricingEngine,
    ProjectedCost,
    ResourceType,
    UsageRecord,
)


@pytest.fixture
def engine() -> PricingEngine:
    return PricingEngine()


class TestCalculateLineItem:
    def test_returns_correct_line_item(self, engine: PricingEngine) -> None:
        item = engine.calculate_line_item(ResourceType.CPU, quantity=100.0)
        assert isinstance(item, LineItem)
        assert item.resource_type == ResourceType.CPU
        assert item.quantity == 100.0
        assert item.unit_price == DEFAULT_PRICING[ResourceType.CPU]
        expected_total = round(100.0 * DEFAULT_PRICING[ResourceType.CPU], 6)
        assert item.total == expected_total

    def test_custom_price_override(self, engine: PricingEngine) -> None:
        item = engine.calculate_line_item(
            ResourceType.STORAGE,
            quantity=50.0,
            custom_price=0.05,
        )
        assert item.unit_price == 0.05
        assert item.total == round(50.0 * 0.05, 6)


class TestCalculatePeriodCost:
    def test_aggregates_multiple_records(self, engine: PricingEngine) -> None:
        records = [
            UsageRecord(resource_type=ResourceType.CPU, quantity=10.0),
            UsageRecord(resource_type=ResourceType.MEMORY, quantity=20.0),
        ]
        period = engine.calculate_period_cost(records)
        assert isinstance(period, PeriodCost)
        assert len(period.line_items) == 2
        expected = round(
            10.0 * DEFAULT_PRICING[ResourceType.CPU] + 20.0 * DEFAULT_PRICING[ResourceType.MEMORY],
            6,
        )
        assert period.total == expected
        assert period.currency == "EUR"


class TestProjectMonthlyCost:
    def test_extrapolates_correctly(self, engine: PricingEngine) -> None:
        records = [UsageRecord(resource_type=ResourceType.CPU, quantity=100.0)]
        projection = engine.project_monthly_cost(records, days_elapsed=10, days_in_month=30)
        assert isinstance(projection, ProjectedCost)
        assert projection.projected_total == pytest.approx(
            projection.current_total * 3.0,
            rel=1e-6,
        )
        assert projection.days_elapsed == 10
        assert projection.days_in_month == 30

    def test_raises_for_zero_days_elapsed(self, engine: PricingEngine) -> None:
        records = [UsageRecord(resource_type=ResourceType.CPU, quantity=1.0)]
        with pytest.raises(ValueError, match="days_elapsed must be positive"):
            engine.project_monthly_cost(records, days_elapsed=0, days_in_month=30)

    def test_raises_for_negative_days_elapsed(self, engine: PricingEngine) -> None:
        records = [UsageRecord(resource_type=ResourceType.CPU, quantity=1.0)]
        with pytest.raises(ValueError, match="days_elapsed must be positive"):
            engine.project_monthly_cost(records, days_elapsed=-5, days_in_month=30)
