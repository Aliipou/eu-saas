"""
SQLAlchemy 2.0+ ORM models for the EU-Grade Multi-Tenant Cloud Platform.

Schema layout
-------------
* **public** schema  -- shared across all tenants
    - ``tenants``   -- one row per onboarded tenant
    - ``audit_log`` -- append-only, tamper-evident audit trail
* **tenant_{slug}** schemas  -- one schema per tenant
    - ``users``
    - ``usage_records``
    - ``cost_records``
    - ``invoices``
"""

from __future__ import annotations

import enum
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
)


# ---------------------------------------------------------------------------
# Base class
# ---------------------------------------------------------------------------

class Base(DeclarativeBase):
    """Shared declarative base for every ORM model."""
    pass


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class TenantStatus(str, enum.Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    DEACTIVATED = "deactivated"
    PENDING = "pending"


class TenantTier(str, enum.Enum):
    FREE = "free"
    STARTER = "starter"
    PROFESSIONAL = "professional"
    ENTERPRISE = "enterprise"


class UserRole(str, enum.Enum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"


class InvoiceStatus(str, enum.Enum):
    DRAFT = "draft"
    ISSUED = "issued"
    PAID = "paid"
    OVERDUE = "overdue"
    CANCELLED = "cancelled"


class AuditAction(str, enum.Enum):
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    LOGIN = "login"
    LOGOUT = "logout"
    EXPORT = "export"
    BILLING = "billing"
    SCHEMA_CHANGE = "schema_change"
    COMPLIANCE = "compliance"


# ---------------------------------------------------------------------------
# PUBLIC SCHEMA -- TenantModel
# ---------------------------------------------------------------------------

class TenantModel(Base):
    """Represents a tenant (organisation) registered on the platform.

    Lives in the ``public`` schema and is shared across all tenants.
    """

    __tablename__ = "tenants"
    __table_args__ = (
        UniqueConstraint("slug", name="uq_tenants_slug"),
        Index("ix_tenants_status", "status"),
        Index("ix_tenants_created_at", "created_at"),
        {"schema": "public"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[TenantStatus] = mapped_column(
        Enum(TenantStatus, name="tenant_status", schema="public"),
        nullable=False,
        default=TenantStatus.PENDING,
    )
    tier: Mapped[TenantTier] = mapped_column(
        Enum(TenantTier, name="tenant_tier", schema="public"),
        nullable=False,
        default=TenantTier.FREE,
    )
    domain: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    metadata_json: Mapped[Optional[dict]] = mapped_column(
        JSONB, nullable=True, default=None
    )
    data_residency_region: Mapped[str] = mapped_column(
        String(10), nullable=False, default="eu-west-1"
    )
    max_users: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    is_gdpr_compliant: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Back-references (only useful inside public-schema queries)
    audit_logs: Mapped[List["AuditLogModel"]] = relationship(
        back_populates="tenant", lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<Tenant(id={self.id!r}, slug={self.slug!r}, status={self.status!r})>"


# ---------------------------------------------------------------------------
# TENANT SCHEMA -- UserModel
# ---------------------------------------------------------------------------

class UserModel(Base):
    """A user belonging to a specific tenant.

    This table is created inside each ``tenant_{slug}`` schema.
    """

    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("email", name="uq_users_email"),
        Index("ix_users_email", "email"),
        Index("ix_users_role", "role"),
        Index("ix_users_is_active", "is_active"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    hashed_password: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role", create_constraint=False),
        nullable=False,
        default=UserRole.MEMBER,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    last_login_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships within the tenant schema
    usage_records: Mapped[List["UsageRecordModel"]] = relationship(
        back_populates="user", lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id!r}, email={self.email!r})>"


# ---------------------------------------------------------------------------
# TENANT SCHEMA -- UsageRecordModel
# ---------------------------------------------------------------------------

class UsageRecordModel(Base):
    """Tracks individual resource-usage events for billing purposes."""

    __tablename__ = "usage_records"
    __table_args__ = (
        Index("ix_usage_records_tenant_id", "tenant_id"),
        Index("ix_usage_records_user_id", "user_id"),
        Index("ix_usage_records_recorded_at", "recorded_at"),
        Index(
            "ix_usage_records_tenant_period",
            "tenant_id",
            "recorded_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    resource_type: Mapped[str] = mapped_column(String(100), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), nullable=False
    )
    unit: Mapped[str] = mapped_column(String(50), nullable=False)
    metadata_json: Mapped[Optional[dict]] = mapped_column(
        JSONB, nullable=True
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    user: Mapped[Optional["UserModel"]] = relationship(
        back_populates="usage_records"
    )

    def __repr__(self) -> str:
        return (
            f"<UsageRecord(id={self.id!r}, resource={self.resource_type!r}, "
            f"qty={self.quantity!r})>"
        )


# ---------------------------------------------------------------------------
# TENANT SCHEMA -- CostRecordModel
# ---------------------------------------------------------------------------

class CostRecordModel(Base):
    """Aggregated cost line-items derived from usage records."""

    __tablename__ = "cost_records"
    __table_args__ = (
        Index("ix_cost_records_tenant_id", "tenant_id"),
        Index("ix_cost_records_period", "period_start", "period_end"),
        Index(
            "ix_cost_records_tenant_period",
            "tenant_id",
            "period_start",
            "period_end",
        ),
        CheckConstraint(
            "amount >= 0", name="ck_cost_records_amount_non_negative"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    resource_type: Mapped[str] = mapped_column(String(100), nullable=False)
    amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False
    )
    currency: Mapped[str] = mapped_column(
        String(3), nullable=False, default="EUR"
    )
    period_start: Mapped[date] = mapped_column(nullable=False)
    period_end: Mapped[date] = mapped_column(nullable=False)
    invoice_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("invoices.id", ondelete="SET NULL"),
        nullable=True,
    )
    metadata_json: Mapped[Optional[dict]] = mapped_column(
        JSONB, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    invoice: Mapped[Optional["InvoiceModel"]] = relationship(
        back_populates="cost_records"
    )

    def __repr__(self) -> str:
        return (
            f"<CostRecord(id={self.id!r}, type={self.resource_type!r}, "
            f"amount={self.amount!r} {self.currency})>"
        )


# ---------------------------------------------------------------------------
# TENANT SCHEMA -- InvoiceModel
# ---------------------------------------------------------------------------

class InvoiceModel(Base):
    """Monthly invoice issued to a tenant."""

    __tablename__ = "invoices"
    __table_args__ = (
        UniqueConstraint(
            "invoice_number", name="uq_invoices_invoice_number"
        ),
        Index("ix_invoices_tenant_id", "tenant_id"),
        Index("ix_invoices_status", "status"),
        Index("ix_invoices_issued_at", "issued_at"),
        CheckConstraint(
            "total_amount >= 0",
            name="ck_invoices_total_amount_non_negative",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    invoice_number: Mapped[str] = mapped_column(
        String(50), nullable=False
    )
    status: Mapped[InvoiceStatus] = mapped_column(
        Enum(InvoiceStatus, name="invoice_status", create_constraint=False),
        nullable=False,
        default=InvoiceStatus.DRAFT,
    )
    total_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0.0000")
    )
    currency: Mapped[str] = mapped_column(
        String(3), nullable=False, default="EUR"
    )
    period_start: Mapped[date] = mapped_column(nullable=False)
    period_end: Mapped[date] = mapped_column(nullable=False)
    issued_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    paid_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    metadata_json: Mapped[Optional[dict]] = mapped_column(
        JSONB, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    cost_records: Mapped[List["CostRecordModel"]] = relationship(
        back_populates="invoice", lazy="selectin"
    )

    def __repr__(self) -> str:
        return (
            f"<Invoice(id={self.id!r}, number={self.invoice_number!r}, "
            f"status={self.status!r})>"
        )


# ---------------------------------------------------------------------------
# PUBLIC SCHEMA -- AuditLogModel  (shared, append-only)
# ---------------------------------------------------------------------------

class AuditLogModel(Base):
    """Append-only, tamper-evident audit log stored in the public schema.

    Each entry contains a SHA-256 ``chain_hash`` that incorporates the
    hash of the previous entry, forming a hash-chain for integrity
    verification.
    """

    __tablename__ = "audit_log"
    __table_args__ = (
        Index("ix_audit_log_tenant_id", "tenant_id"),
        Index("ix_audit_log_action", "action"),
        Index("ix_audit_log_timestamp", "timestamp"),
        Index(
            "ix_audit_log_tenant_timestamp",
            "tenant_id",
            "timestamp",
        ),
        Index("ix_audit_log_actor_id", "actor_id"),
        {"schema": "public"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("public.tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    actor_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    action: Mapped[AuditAction] = mapped_column(
        Enum(AuditAction, name="audit_action", schema="public"),
        nullable=False,
    )
    resource_type: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_id: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True
    )
    details: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(
        String(45), nullable=True
    )
    chain_hash: Mapped[str] = mapped_column(
        String(64), nullable=False
    )
    previous_hash: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    tenant: Mapped["TenantModel"] = relationship(
        back_populates="audit_logs"
    )

    def __repr__(self) -> str:
        return (
            f"<AuditLog(id={self.id!r}, action={self.action!r}, "
            f"tenant_id={self.tenant_id!r})>"
        )
