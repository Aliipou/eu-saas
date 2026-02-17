from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4


class ResourceType(enum.Enum):
    CPU = "CPU"
    MEMORY = "MEMORY"
    STORAGE = "STORAGE"
    NETWORK = "NETWORK"
    API_CALLS = "API_CALLS"


@dataclass
class UsageRecord:
    id: UUID = field(default_factory=uuid4)
    tenant_id: UUID = field(default_factory=uuid4)
    resource_type: ResourceType = ResourceType.CPU
    quantity: Decimal = Decimal("0")
    unit: str = ""
    recorded_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class CostRecord:
    id: UUID = field(default_factory=uuid4)
    tenant_id: UUID = field(default_factory=uuid4)
    date: date = field(default_factory=date.today)
    resource_type: ResourceType = ResourceType.CPU
    quantity: Decimal = Decimal("0")
    unit_price: Decimal = Decimal("0")
    total_cost: Decimal = Decimal("0")
    currency: str = "EUR"


@dataclass
class Invoice:
    id: UUID = field(default_factory=uuid4)
    tenant_id: UUID = field(default_factory=uuid4)
    period_start: date = field(default_factory=date.today)
    period_end: date = field(default_factory=date.today)
    line_items: list[dict[str, Any]] = field(default_factory=list)
    total_amount: Decimal = Decimal("0")
    currency: str = "EUR"
    status: str = "DRAFT"
    generated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class CostAnomaly:
    id: UUID = field(default_factory=uuid4)
    tenant_id: UUID = field(default_factory=uuid4)
    resource_type: ResourceType = ResourceType.CPU
    expected_value: Decimal = Decimal("0")
    actual_value: Decimal = Decimal("0")
    deviation_factor: Decimal = Decimal("0")
    detected_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    acknowledged: bool = False
