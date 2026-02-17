from __future__ import annotations

import enum
import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4


class AuditAction(enum.Enum):
    TENANT_CREATED = "TENANT_CREATED"
    TENANT_UPDATED = "TENANT_UPDATED"
    TENANT_DELETED = "TENANT_DELETED"
    USER_LOGIN = "USER_LOGIN"
    DATA_ACCESSED = "DATA_ACCESSED"
    DATA_EXPORTED = "DATA_EXPORTED"
    DATA_ERASED = "DATA_ERASED"
    SCHEMA_MIGRATED = "SCHEMA_MIGRATED"
    COST_ANOMALY_DETECTED = "COST_ANOMALY_DETECTED"
    RETENTION_EXECUTED = "RETENTION_EXECUTED"


def _compute_entry_hash(
    previous_hash: str,
    action: AuditAction,
    tenant_id: UUID,
    timestamp: datetime,
) -> str:
    payload = f"{previous_hash}{action.value}{tenant_id!s}{timestamp.isoformat()}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass
class AuditEntry:
    id: UUID = field(default_factory=uuid4)
    tenant_id: UUID = field(default_factory=uuid4)
    action: AuditAction = AuditAction.TENANT_CREATED
    actor_id: UUID = field(default_factory=uuid4)
    details: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    previous_hash: str = ""
    entry_hash: str = field(default="", init=False)

    def __post_init__(self) -> None:
        self.entry_hash = _compute_entry_hash(
            self.previous_hash,
            self.action,
            self.tenant_id,
            self.timestamp,
        )
