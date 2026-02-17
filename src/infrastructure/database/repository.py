"""
Repository pattern implementations for the EU-Grade Multi-Tenant Cloud Platform.

Each repository encapsulates data-access logic for a specific aggregate
root and operates through an injected :class:`AsyncSession`.  Tenant-
schema routing is handled by the caller (typically via
``get_async_tenant_session``); the repositories themselves are schema-
agnostic.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy import and_, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from .models import (
    AuditAction,
    AuditLogModel,
    CostRecordModel,
    InvoiceModel,
    InvoiceStatus,
    TenantModel,
    TenantStatus,
    TenantTier,
    UsageRecordModel,
    UserModel,
    UserRole,
)


# =========================================================================
# TenantRepository -- operates on the PUBLIC schema
# =========================================================================

class TenantRepository:
    """CRUD operations for :class:`TenantModel` (``public.tenants``).

    Parameters
    ----------
    session:
        An :class:`AsyncSession` whose ``search_path`` includes
        ``public``.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        name: str,
        slug: str,
        tier: TenantTier = TenantTier.FREE,
        domain: Optional[str] = None,
        data_residency_region: str = "eu-west-1",
        max_users: int = 50,
        metadata_json: Optional[dict] = None,
    ) -> TenantModel:
        tenant = TenantModel(
            name=name,
            slug=slug,
            tier=tier,
            domain=domain,
            data_residency_region=data_residency_region,
            max_users=max_users,
            metadata_json=metadata_json,
            status=TenantStatus.PENDING,
        )
        self._session.add(tenant)
        await self._session.flush()
        await self._session.refresh(tenant)
        return tenant

    async def get_by_id(self, tenant_id: uuid.UUID) -> Optional[TenantModel]:
        stmt = select(TenantModel).where(TenantModel.id == tenant_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_slug(self, slug: str) -> Optional[TenantModel]:
        stmt = select(TenantModel).where(TenantModel.slug == slug)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_all(
        self,
        *,
        status: Optional[TenantStatus] = None,
        offset: int = 0,
        limit: int = 100,
    ) -> Sequence[TenantModel]:
        stmt = select(TenantModel).offset(offset).limit(limit)
        if status is not None:
            stmt = stmt.where(TenantModel.status == status)
        stmt = stmt.order_by(TenantModel.created_at.desc())
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def update(
        self,
        tenant_id: uuid.UUID,
        **fields: Any,
    ) -> Optional[TenantModel]:
        allowed = {
            "name", "slug", "status", "tier", "domain",
            "data_residency_region", "max_users", "is_gdpr_compliant",
            "metadata_json",
        }
        update_data = {k: v for k, v in fields.items() if k in allowed}
        if not update_data:
            return await self.get_by_id(tenant_id)

        stmt = (
            update(TenantModel)
            .where(TenantModel.id == tenant_id)
            .values(**update_data)
            .returning(TenantModel)
        )
        result = await self._session.execute(stmt)
        await self._session.flush()
        return result.scalar_one_or_none()

    async def delete(self, tenant_id: uuid.UUID) -> bool:
        stmt = delete(TenantModel).where(TenantModel.id == tenant_id)
        result = await self._session.execute(stmt)
        await self._session.flush()
        return result.rowcount > 0


# =========================================================================
# UserRepository -- operates on a TENANT schema
# =========================================================================

class UserRepository:
    """CRUD operations for :class:`UserModel` (``tenant_{slug}.users``).

    Parameters
    ----------
    session:
        An :class:`AsyncSession` whose ``search_path`` is set to the
        target tenant schema.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        tenant_id: uuid.UUID,
        email: str,
        display_name: str,
        hashed_password: str,
        role: UserRole = UserRole.MEMBER,
    ) -> UserModel:
        user = UserModel(
            tenant_id=tenant_id,
            email=email,
            display_name=display_name,
            hashed_password=hashed_password,
            role=role,
        )
        self._session.add(user)
        await self._session.flush()
        await self._session.refresh(user)
        return user

    async def get_by_id(self, user_id: uuid.UUID) -> Optional[UserModel]:
        stmt = select(UserModel).where(UserModel.id == user_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> Optional[UserModel]:
        stmt = select(UserModel).where(UserModel.email == email)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_tenant(
        self,
        tenant_id: uuid.UUID,
        *,
        offset: int = 0,
        limit: int = 100,
        is_active: Optional[bool] = None,
    ) -> Sequence[UserModel]:
        stmt = (
            select(UserModel)
            .where(UserModel.tenant_id == tenant_id)
            .offset(offset)
            .limit(limit)
        )
        if is_active is not None:
            stmt = stmt.where(UserModel.is_active == is_active)
        stmt = stmt.order_by(UserModel.created_at.desc())
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def update(
        self,
        user_id: uuid.UUID,
        **fields: Any,
    ) -> Optional[UserModel]:
        allowed = {
            "email", "display_name", "hashed_password", "role",
            "is_active", "last_login_at",
        }
        update_data = {k: v for k, v in fields.items() if k in allowed}
        if not update_data:
            return await self.get_by_id(user_id)

        stmt = (
            update(UserModel)
            .where(UserModel.id == user_id)
            .values(**update_data)
            .returning(UserModel)
        )
        result = await self._session.execute(stmt)
        await self._session.flush()
        return result.scalar_one_or_none()

    async def delete(self, user_id: uuid.UUID) -> bool:
        stmt = delete(UserModel).where(UserModel.id == user_id)
        result = await self._session.execute(stmt)
        await self._session.flush()
        return result.rowcount > 0


# =========================================================================
# BillingRepository -- operates on a TENANT schema
# =========================================================================

class BillingRepository:
    """CRUD for usage records, cost records, and invoices.

    Parameters
    ----------
    session:
        An :class:`AsyncSession` whose ``search_path`` is set to the
        target tenant schema.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ---- Usage Records ------------------------------------------------

    async def record_usage(
        self,
        *,
        tenant_id: uuid.UUID,
        resource_type: str,
        quantity: Decimal,
        unit: str,
        user_id: Optional[uuid.UUID] = None,
        metadata_json: Optional[dict] = None,
    ) -> UsageRecordModel:
        record = UsageRecordModel(
            tenant_id=tenant_id,
            user_id=user_id,
            resource_type=resource_type,
            quantity=quantity,
            unit=unit,
            metadata_json=metadata_json,
        )
        self._session.add(record)
        await self._session.flush()
        await self._session.refresh(record)
        return record

    async def get_usage_by_tenant(
        self,
        tenant_id: uuid.UUID,
        *,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        resource_type: Optional[str] = None,
        offset: int = 0,
        limit: int = 500,
    ) -> Sequence[UsageRecordModel]:
        stmt = (
            select(UsageRecordModel)
            .where(UsageRecordModel.tenant_id == tenant_id)
        )
        if start is not None:
            stmt = stmt.where(UsageRecordModel.recorded_at >= start)
        if end is not None:
            stmt = stmt.where(UsageRecordModel.recorded_at <= end)
        if resource_type is not None:
            stmt = stmt.where(UsageRecordModel.resource_type == resource_type)
        stmt = stmt.order_by(UsageRecordModel.recorded_at.desc())
        stmt = stmt.offset(offset).limit(limit)
        result = await self._session.execute(stmt)
        return result.scalars().all()

    # ---- Cost Records -------------------------------------------------

    async def create_cost_record(
        self,
        *,
        tenant_id: uuid.UUID,
        resource_type: str,
        amount: Decimal,
        currency: str = "EUR",
        period_start: date,
        period_end: date,
        invoice_id: Optional[uuid.UUID] = None,
        metadata_json: Optional[dict] = None,
    ) -> CostRecordModel:
        record = CostRecordModel(
            tenant_id=tenant_id,
            resource_type=resource_type,
            amount=amount,
            currency=currency,
            period_start=period_start,
            period_end=period_end,
            invoice_id=invoice_id,
            metadata_json=metadata_json,
        )
        self._session.add(record)
        await self._session.flush()
        await self._session.refresh(record)
        return record

    async def get_cost_records(
        self,
        tenant_id: uuid.UUID,
        *,
        period_start: Optional[date] = None,
        period_end: Optional[date] = None,
        offset: int = 0,
        limit: int = 500,
    ) -> Sequence[CostRecordModel]:
        stmt = (
            select(CostRecordModel)
            .where(CostRecordModel.tenant_id == tenant_id)
        )
        if period_start is not None:
            stmt = stmt.where(CostRecordModel.period_start >= period_start)
        if period_end is not None:
            stmt = stmt.where(CostRecordModel.period_end <= period_end)
        stmt = stmt.order_by(CostRecordModel.created_at.desc())
        stmt = stmt.offset(offset).limit(limit)
        result = await self._session.execute(stmt)
        return result.scalars().all()

    # ---- Invoices -----------------------------------------------------

    async def create_invoice(
        self,
        *,
        tenant_id: uuid.UUID,
        invoice_number: str,
        total_amount: Decimal,
        currency: str = "EUR",
        period_start: date,
        period_end: date,
        status: InvoiceStatus = InvoiceStatus.DRAFT,
        metadata_json: Optional[dict] = None,
    ) -> InvoiceModel:
        invoice = InvoiceModel(
            tenant_id=tenant_id,
            invoice_number=invoice_number,
            total_amount=total_amount,
            currency=currency,
            period_start=period_start,
            period_end=period_end,
            status=status,
            metadata_json=metadata_json,
        )
        self._session.add(invoice)
        await self._session.flush()
        await self._session.refresh(invoice)
        return invoice

    async def get_invoices(
        self,
        tenant_id: uuid.UUID,
        *,
        status: Optional[InvoiceStatus] = None,
        offset: int = 0,
        limit: int = 100,
    ) -> Sequence[InvoiceModel]:
        stmt = (
            select(InvoiceModel)
            .where(InvoiceModel.tenant_id == tenant_id)
        )
        if status is not None:
            stmt = stmt.where(InvoiceModel.status == status)
        stmt = stmt.order_by(InvoiceModel.created_at.desc())
        stmt = stmt.offset(offset).limit(limit)
        result = await self._session.execute(stmt)
        return result.scalars().all()


# =========================================================================
# AuditRepository -- operates on the PUBLIC schema (append-only)
# =========================================================================

class AuditRepository:
    """Append-only audit log with hash-chain integrity.

    The audit log lives in ``public.audit_log`` and is shared across
    tenants but partitioned logically by ``tenant_id``.

    Parameters
    ----------
    session:
        An :class:`AsyncSession` whose ``search_path`` includes
        ``public``.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @staticmethod
    def _compute_hash(
        *,
        tenant_id: uuid.UUID,
        actor_id: Optional[uuid.UUID],
        action: str,
        resource_type: str,
        resource_id: Optional[str],
        details: Optional[dict],
        timestamp: datetime,
        previous_hash: Optional[str],
    ) -> str:
        """Compute a SHA-256 hash for chain integrity."""
        payload = json.dumps(
            {
                "tenant_id": str(tenant_id),
                "actor_id": str(actor_id) if actor_id else None,
                "action": action,
                "resource_type": resource_type,
                "resource_id": resource_id,
                "details": details,
                "timestamp": timestamp.isoformat(),
                "previous_hash": previous_hash,
            },
            sort_keys=True,
            default=str,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    async def _get_latest_hash(self, tenant_id: uuid.UUID) -> Optional[str]:
        """Retrieve the ``chain_hash`` of the most recent audit entry
        for the given tenant."""
        stmt = (
            select(AuditLogModel.chain_hash)
            .where(AuditLogModel.tenant_id == tenant_id)
            .order_by(AuditLogModel.timestamp.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        return row

    async def append_entry(
        self,
        *,
        tenant_id: uuid.UUID,
        action: AuditAction,
        resource_type: str,
        actor_id: Optional[uuid.UUID] = None,
        resource_id: Optional[str] = None,
        details: Optional[dict] = None,
        ip_address: Optional[str] = None,
    ) -> AuditLogModel:
        """Append a new entry to the audit log, maintaining the hash chain.

        Parameters
        ----------
        tenant_id:
            The tenant this event belongs to.
        action:
            The type of auditable action.
        resource_type:
            E.g. ``"user"``, ``"invoice"``, ``"tenant"``.
        actor_id:
            The user who performed the action (if applicable).
        resource_id:
            Identifier of the affected resource.
        details:
            Arbitrary JSON payload with additional context.
        ip_address:
            IP address of the caller.

        Returns
        -------
        AuditLogModel
        """
        previous_hash = await self._get_latest_hash(tenant_id)
        now = datetime.utcnow()

        chain_hash = self._compute_hash(
            tenant_id=tenant_id,
            actor_id=actor_id,
            action=action.value,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details,
            timestamp=now,
            previous_hash=previous_hash,
        )

        entry = AuditLogModel(
            tenant_id=tenant_id,
            actor_id=actor_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details,
            ip_address=ip_address,
            chain_hash=chain_hash,
            previous_hash=previous_hash,
            timestamp=now,
        )
        self._session.add(entry)
        await self._session.flush()
        await self._session.refresh(entry)
        return entry

    async def get_entries_by_tenant(
        self,
        tenant_id: uuid.UUID,
        *,
        action: Optional[AuditAction] = None,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        offset: int = 0,
        limit: int = 200,
    ) -> Sequence[AuditLogModel]:
        """Retrieve audit entries for a tenant, optionally filtered."""
        stmt = (
            select(AuditLogModel)
            .where(AuditLogModel.tenant_id == tenant_id)
        )
        if action is not None:
            stmt = stmt.where(AuditLogModel.action == action)
        if start is not None:
            stmt = stmt.where(AuditLogModel.timestamp >= start)
        if end is not None:
            stmt = stmt.where(AuditLogModel.timestamp <= end)
        stmt = stmt.order_by(AuditLogModel.timestamp.asc())
        stmt = stmt.offset(offset).limit(limit)
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def verify_chain_integrity(
        self,
        tenant_id: uuid.UUID,
    ) -> Dict[str, Any]:
        """Verify the hash-chain integrity of all audit entries for a
        tenant.

        Returns
        -------
        dict
            ``{"valid": bool, "total_entries": int, "broken_at_index": int | None,
              "broken_entry_id": str | None}``
        """
        stmt = (
            select(AuditLogModel)
            .where(AuditLogModel.tenant_id == tenant_id)
            .order_by(AuditLogModel.timestamp.asc())
        )
        result = await self._session.execute(stmt)
        entries = result.scalars().all()

        if not entries:
            return {
                "valid": True,
                "total_entries": 0,
                "broken_at_index": None,
                "broken_entry_id": None,
            }

        previous_hash: Optional[str] = None

        for idx, entry in enumerate(entries):
            # Verify the previous_hash pointer
            if entry.previous_hash != previous_hash:
                return {
                    "valid": False,
                    "total_entries": len(entries),
                    "broken_at_index": idx,
                    "broken_entry_id": str(entry.id),
                }

            # Recompute and verify chain_hash
            expected_hash = self._compute_hash(
                tenant_id=entry.tenant_id,
                actor_id=entry.actor_id,
                action=entry.action.value if isinstance(entry.action, AuditAction) else entry.action,
                resource_type=entry.resource_type,
                resource_id=entry.resource_id,
                details=entry.details,
                timestamp=entry.timestamp,
                previous_hash=entry.previous_hash,
            )
            if entry.chain_hash != expected_hash:
                return {
                    "valid": False,
                    "total_entries": len(entries),
                    "broken_at_index": idx,
                    "broken_entry_id": str(entry.id),
                }

            previous_hash = entry.chain_hash

        return {
            "valid": True,
            "total_entries": len(entries),
            "broken_at_index": None,
            "broken_entry_id": None,
        }
