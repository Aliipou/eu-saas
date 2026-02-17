from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID, uuid4

from domain.models.billing import ResourceType


@dataclass
class TenantEvent:
    tenant_id: UUID = field(default_factory=uuid4)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    event_type: str = ""


@dataclass
class TenantCreated(TenantEvent):
    event_type: str = "TenantCreated"


@dataclass
class TenantProvisioned(TenantEvent):
    event_type: str = "TenantProvisioned"


@dataclass
class TenantActivated(TenantEvent):
    event_type: str = "TenantActivated"


@dataclass
class TenantSuspended(TenantEvent):
    event_type: str = "TenantSuspended"


@dataclass
class TenantDeprovisioning(TenantEvent):
    event_type: str = "TenantDeprovisioning"


@dataclass
class TenantDeleted(TenantEvent):
    event_type: str = "TenantDeleted"


@dataclass
class CostAnomalyDetected(TenantEvent):
    event_type: str = "CostAnomalyDetected"
    resource_type: ResourceType = ResourceType.CPU
    deviation: float = 0.0
