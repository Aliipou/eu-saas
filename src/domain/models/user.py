from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4


class TenantRole(enum.Enum):
    OWNER = "OWNER"
    ADMIN = "ADMIN"
    MEMBER = "MEMBER"
    VIEWER = "VIEWER"


@dataclass
class User:
    id: UUID = field(default_factory=uuid4)
    tenant_id: UUID = field(default_factory=uuid4)
    email: str = ""
    hashed_password: str = ""
    full_name: str = ""
    role: TenantRole = TenantRole.MEMBER
    is_active: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_login: datetime | None = None
