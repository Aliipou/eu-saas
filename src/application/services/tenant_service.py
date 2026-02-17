"""Application service that orchestrates tenant lifecycle operations.

``TenantService`` sits between the presentation layer and the domain /
infrastructure layers.  It coordinates repository calls, domain-service
validations, schema management, and audit logging without leaking
infrastructure details upward.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Optional, Protocol
from uuid import UUID, uuid4

from domain.exceptions import (
    InvalidStateTransitionError,
    TenantAlreadyExistsError,
    TenantNotFoundError,
)
from domain.models.audit import AuditAction, AuditEntry
from domain.models.tenant import Tenant, TenantSettings, TenantStatus
from domain.services.tenant_lifecycle import TenantLifecycleService

from application.schemas.pagination import PaginatedResponse, PaginationParams

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Repository / infrastructure port interfaces (dependency-inversion)
# ---------------------------------------------------------------------------

class TenantRepository(Protocol):
    """Port: persistence operations for :class:`Tenant` aggregates."""

    def get_by_id(self, tenant_id: UUID) -> Optional[Tenant]: ...

    def get_by_slug(self, slug: str) -> Optional[Tenant]: ...

    def list_tenants(
        self,
        offset: int,
        limit: int,
        status_filter: Optional[TenantStatus] = None,
    ) -> tuple[list[Tenant], int]: ...

    def save(self, tenant: Tenant) -> Tenant: ...

    def update(self, tenant: Tenant) -> Tenant: ...


class AuditRepository(Protocol):
    """Port: persistence for tamper-evident audit entries."""

    def get_latest_entry(self, tenant_id: UUID) -> Optional[AuditEntry]: ...

    def save(self, entry: AuditEntry) -> AuditEntry: ...


class TenantSchemaManager(Protocol):
    """Port: PostgreSQL schema lifecycle management."""

    def create_schema(self, schema_name: str) -> None: ...

    def run_migrations(self, schema_name: str) -> None: ...

    def drop_schema(self, schema_name: str) -> None: ...


class EventPublisher(Protocol):
    """Port: domain-event publishing."""

    def publish(self, event: Any) -> None: ...


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class TenantService:
    """Orchestrates all tenant CRUD and lifecycle operations."""

    def __init__(
        self,
        tenant_repo: TenantRepository,
        audit_repo: AuditRepository,
        schema_manager: TenantSchemaManager,
        lifecycle_service: TenantLifecycleService,
        event_publisher: EventPublisher,
    ) -> None:
        self._tenant_repo = tenant_repo
        self._audit_repo = audit_repo
        self._schema_manager = schema_manager
        self._lifecycle = lifecycle_service
        self._event_publisher = event_publisher

    # -- helpers ----------------------------------------------------------

    def _create_audit_entry(
        self,
        tenant_id: UUID,
        action: AuditAction,
        actor_id: Optional[UUID] = None,
        details: Optional[dict[str, Any]] = None,
    ) -> AuditEntry:
        """Build a chained audit entry and persist it."""
        latest = self._audit_repo.get_latest_entry(tenant_id)
        previous_hash = latest.entry_hash if latest else ""

        entry = AuditEntry(
            id=uuid4(),
            tenant_id=tenant_id,
            action=action,
            actor_id=actor_id or UUID(int=0),
            details=details or {},
            timestamp=datetime.now(timezone.utc),
            previous_hash=previous_hash,
        )
        return self._audit_repo.save(entry)

    def _transition(self, tenant: Tenant, new_status: TenantStatus) -> Tenant:
        """Validate and apply a state transition."""
        if not self._lifecycle.validate_transition(tenant.status, new_status):
            raise InvalidStateTransitionError(
                current_state=tenant.status.value,
                new_state=new_status.value,
            )
        tenant.status = new_status
        tenant.updated_at = datetime.now(timezone.utc)
        return self._tenant_repo.update(tenant)

    # -- public API -------------------------------------------------------

    def create_tenant(
        self,
        name: str,
        slug: str,
        owner_email: str,
        settings: Optional[dict[str, Any]] = None,
    ) -> Tenant:
        """Provision a new tenant end-to-end.

        The tenant moves through PENDING -> PROVISIONING -> ACTIVE,
        creating a dedicated PostgreSQL schema along the way.
        """
        # 1. Validate slug uniqueness
        if self._tenant_repo.get_by_slug(slug) is not None:
            raise TenantAlreadyExistsError(identifier=slug)

        schema_name = f"tenant_{slug.replace('-', '_')}"

        # 2. Create tenant record in PENDING state
        tenant = Tenant(
            id=uuid4(),
            name=name,
            slug=slug,
            owner_email=owner_email,
            status=TenantStatus.PENDING,
            schema_name=schema_name,
            settings=settings or {},
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        tenant = self._tenant_repo.save(tenant)
        logger.info("Tenant %s created in PENDING state", tenant.id)

        try:
            # 3. Transition to PROVISIONING
            tenant = self._transition(tenant, TenantStatus.PROVISIONING)

            # 4. Create PostgreSQL schema
            self._schema_manager.create_schema(schema_name)

            # 5. Run initial migrations
            self._schema_manager.run_migrations(schema_name)

            # 6. Transition to ACTIVE
            tenant = self._transition(tenant, TenantStatus.ACTIVE)

        except Exception:
            logger.exception(
                "Provisioning failed for tenant %s – rolling back to DELETED",
                tenant.id,
            )
            # Best-effort transition to DELETED on failure
            try:
                tenant.status = TenantStatus.PROVISIONING  # reset for valid path
                self._transition(tenant, TenantStatus.DELETED)
            except Exception:
                logger.exception("Failed to mark tenant %s as DELETED", tenant.id)
            raise

        # 7. Audit
        self._create_audit_entry(
            tenant_id=tenant.id,
            action=AuditAction.TENANT_CREATED,
            details={"slug": slug, "owner_email": owner_email},
        )

        return tenant

    def get_tenant(self, tenant_id: UUID) -> Tenant:
        """Retrieve a single tenant by ID."""
        tenant = self._tenant_repo.get_by_id(tenant_id)
        if tenant is None:
            raise TenantNotFoundError(tenant_id=str(tenant_id))
        return tenant

    def list_tenants(
        self,
        page: int = 1,
        size: int = 20,
        status_filter: Optional[TenantStatus] = None,
    ) -> PaginatedResponse[Tenant]:
        """Return a paginated list of tenants, optionally filtered by status."""
        params = PaginationParams(page=page, size=size)
        items, total = self._tenant_repo.list_tenants(
            offset=params.offset,
            limit=params.size,
            status_filter=status_filter,
        )
        return PaginatedResponse[Tenant](
            items=items,
            total=total,
            page=params.page,
            size=params.size,
        )

    def update_tenant(
        self,
        tenant_id: UUID,
        updates: dict[str, Any],
    ) -> Tenant:
        """Apply partial updates to an existing tenant."""
        tenant = self.get_tenant(tenant_id)

        allowed_fields = {"name", "settings", "metadata"}
        for key, value in updates.items():
            if key in allowed_fields:
                setattr(tenant, key, value)

        tenant.updated_at = datetime.now(timezone.utc)
        tenant = self._tenant_repo.update(tenant)

        self._create_audit_entry(
            tenant_id=tenant.id,
            action=AuditAction.TENANT_UPDATED,
            details={"updated_fields": list(updates.keys())},
        )
        return tenant

    def suspend_tenant(self, tenant_id: UUID) -> Tenant:
        """Suspend an active tenant (ACTIVE -> SUSPENDED)."""
        tenant = self.get_tenant(tenant_id)
        tenant = self._transition(tenant, TenantStatus.SUSPENDED)

        self._create_audit_entry(
            tenant_id=tenant.id,
            action=AuditAction.TENANT_UPDATED,
            details={"action": "suspend", "new_status": TenantStatus.SUSPENDED.value},
        )
        return tenant

    def activate_tenant(self, tenant_id: UUID) -> Tenant:
        """Reactivate a suspended tenant (SUSPENDED -> ACTIVE)."""
        tenant = self.get_tenant(tenant_id)
        tenant = self._transition(tenant, TenantStatus.ACTIVE)

        self._create_audit_entry(
            tenant_id=tenant.id,
            action=AuditAction.TENANT_UPDATED,
            details={"action": "activate", "new_status": TenantStatus.ACTIVE.value},
        )
        return tenant

    def deprovision_tenant(self, tenant_id: UUID) -> Tenant:
        """Begin asynchronous deprovisioning of a tenant.

        Transitions to DEPROVISIONING and enqueues the background
        cleanup task.  The caller receives the tenant in its new state
        immediately.
        """
        tenant = self.get_tenant(tenant_id)
        tenant = self._transition(tenant, TenantStatus.DEPROVISIONING)

        self._create_audit_entry(
            tenant_id=tenant.id,
            action=AuditAction.TENANT_DELETED,
            details={"action": "deprovision_started"},
        )

        # Import here to avoid circular dependency with task module
        from application.tasks.tenant_tasks import deprovision_tenant_async

        deprovision_tenant_async.delay(str(tenant_id))

        return tenant
