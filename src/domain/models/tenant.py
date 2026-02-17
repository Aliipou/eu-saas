from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4


class TenantStatus(enum.Enum):
    PENDING = "PENDING"
    PROVISIONING = "PROVISIONING"
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    DEPROVISIONING = "DEPROVISIONING"
    DELETED = "DELETED"


VALID_STATE_TRANSITIONS: dict[TenantStatus, list[TenantStatus]] = {
    TenantStatus.PENDING: [TenantStatus.PROVISIONING, TenantStatus.DELETED],
    TenantStatus.PROVISIONING: [TenantStatus.ACTIVE, TenantStatus.DELETED],
    TenantStatus.ACTIVE: [TenantStatus.SUSPENDED, TenantStatus.DEPROVISIONING],
    TenantStatus.SUSPENDED: [TenantStatus.ACTIVE, TenantStatus.DEPROVISIONING],
    TenantStatus.DEPROVISIONING: [TenantStatus.DELETED],
    TenantStatus.DELETED: [],
}


@dataclass
class TenantSettings:
    max_users: int = 50
    storage_limit_gb: int = 100
    api_rate_limit: int = 1000
    data_retention_days: int = 365
    cost_alert_threshold: float = 1000.0


@dataclass
class Tenant:
    id: UUID = field(default_factory=uuid4)
    name: str = ""
    slug: str = ""
    owner_email: str = ""
    status: TenantStatus = TenantStatus.PENDING
    schema_name: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    settings: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
