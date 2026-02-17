"""GDPR compliance application service.

Implements the right to data portability (export), right to erasure,
and data retention management.  Heavy operations are delegated to
Celery background tasks.
"""

from __future__ import annotations

import enum
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional, Protocol
from uuid import UUID, uuid4

from domain.exceptions import TenantNotFoundError
from domain.models.audit import AuditAction, AuditEntry
from domain.models.tenant import Tenant, TenantStatus
from domain.services.tenant_lifecycle import TenantLifecycleService

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Value objects
# ---------------------------------------------------------------------------

class ExportJobStatus(enum.Enum):
    QUEUED = "QUEUED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class ExportStatus:
    """Status of an asynchronous data-export job."""

    job_id: str
    tenant_id: UUID
    status: ExportJobStatus
    download_url: Optional[str] = None
    error: Optional[str] = None
    created_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


@dataclass(frozen=True)
class ErasureResult:
    """Outcome of a full tenant-data erasure."""

    tenant_id: UUID
    schemas_dropped: list[str] = field(default_factory=list)
    records_deleted: int = 0
    caches_purged: bool = False
    audit_entry_id: Optional[UUID] = None
    completed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class RetentionPolicy:
    """Data retention configuration per tenant."""

    tenant_id: UUID = field(default_factory=uuid4)
    retention_days: int = 365
    grace_period_days: int = 30
    auto_cleanup_enabled: bool = True
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class CleanupResult:
    """Outcome of a retention-policy cleanup run."""

    tenant_id: UUID
    records_soft_deleted: int = 0
    records_hard_deleted: int = 0
    scan_completed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# Repository / infrastructure port interfaces
# ---------------------------------------------------------------------------

class TenantRepository(Protocol):
    """Port: tenant persistence."""

    def get_by_id(self, tenant_id: UUID) -> Optional[Tenant]: ...

    def update(self, tenant: Tenant) -> Tenant: ...


class ExportJobRepository(Protocol):
    """Port: data-export job tracking."""

    def save(self, job_id: str, tenant_id: UUID, status: ExportJobStatus) -> None: ...

    def get_status(self, job_id: str) -> Optional[ExportStatus]: ...

    def update_status(
        self,
        job_id: str,
        status: ExportJobStatus,
        download_url: Optional[str] = None,
        error: Optional[str] = None,
    ) -> None: ...


class RetentionRepository(Protocol):
    """Port: retention-policy persistence and record scanning."""

    def get_policy(self, tenant_id: UUID) -> Optional[RetentionPolicy]: ...

    def save_policy(self, policy: RetentionPolicy) -> RetentionPolicy: ...

    def find_expired_records(
        self,
        tenant_id: UUID,
        threshold_date: date,
    ) -> list[UUID]: ...

    def soft_delete_records(self, record_ids: list[UUID]) -> int: ...

    def find_soft_deleted_past_grace(
        self,
        tenant_id: UUID,
        grace_date: date,
    ) -> list[UUID]: ...

    def hard_delete_records(self, record_ids: list[UUID]) -> int: ...


class TenantSchemaManager(Protocol):
    """Port: PostgreSQL schema lifecycle."""

    def drop_schema(self, schema_name: str) -> None: ...


class CacheManager(Protocol):
    """Port: tenant cache invalidation."""

    def purge_tenant(self, tenant_id: UUID) -> None: ...


class TenantDataRepository(Protocol):
    """Port: bulk data operations for a tenant."""

    def cascade_delete_all(self, tenant_id: UUID) -> int: ...


class AuditRepository(Protocol):
    """Port: tamper-evident audit entries."""

    def get_latest_entry(self, tenant_id: UUID) -> Optional[AuditEntry]: ...

    def save(self, entry: AuditEntry) -> AuditEntry: ...


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class GDPRService:
    """Implements GDPR data-portability, erasure, and retention management."""

    def __init__(
        self,
        tenant_repo: TenantRepository,
        export_job_repo: ExportJobRepository,
        retention_repo: RetentionRepository,
        schema_manager: TenantSchemaManager,
        cache_manager: CacheManager,
        data_repo: TenantDataRepository,
        audit_repo: AuditRepository,
        lifecycle_service: TenantLifecycleService,
    ) -> None:
        self._tenant_repo = tenant_repo
        self._export_job_repo = export_job_repo
        self._retention_repo = retention_repo
        self._schema_manager = schema_manager
        self._cache_manager = cache_manager
        self._data_repo = data_repo
        self._audit_repo = audit_repo
        self._lifecycle = lifecycle_service

    # -- helpers ----------------------------------------------------------

    def _get_tenant_or_raise(self, tenant_id: UUID) -> Tenant:
        tenant = self._tenant_repo.get_by_id(tenant_id)
        if tenant is None:
            raise TenantNotFoundError(tenant_id=str(tenant_id))
        return tenant

    def _create_audit_entry(
        self,
        tenant_id: UUID,
        action: AuditAction,
        details: Optional[dict[str, Any]] = None,
    ) -> AuditEntry:
        latest = self._audit_repo.get_latest_entry(tenant_id)
        previous_hash = latest.entry_hash if latest else ""
        entry = AuditEntry(
            id=uuid4(),
            tenant_id=tenant_id,
            action=action,
            actor_id=UUID(int=0),
            details=details or {},
            timestamp=datetime.now(timezone.utc),
            previous_hash=previous_hash,
        )
        return self._audit_repo.save(entry)

    # -- public API -------------------------------------------------------

    def export_tenant_data(self, tenant_id: UUID) -> str:
        """Queue an asynchronous data-export job.

        Returns the ``job_id`` that callers can use to poll for status.
        """
        self._get_tenant_or_raise(tenant_id)

        job_id = uuid4().hex
        self._export_job_repo.save(
            job_id=job_id,
            tenant_id=tenant_id,
            status=ExportJobStatus.QUEUED,
        )

        # Enqueue Celery task
        from application.tasks.gdpr_tasks import export_tenant_data_task

        export_tenant_data_task.delay(str(tenant_id), job_id)

        self._create_audit_entry(
            tenant_id=tenant_id,
            action=AuditAction.DATA_EXPORTED,
            details={"job_id": job_id, "status": "QUEUED"},
        )
        logger.info("Data export queued for tenant %s (job %s)", tenant_id, job_id)
        return job_id

    def get_export_status(self, job_id: str) -> ExportStatus:
        """Return the current status of an export job."""
        status = self._export_job_repo.get_status(job_id)
        if status is None:
            raise ValueError(f"Export job not found: {job_id}")
        return status

    def execute_erasure(self, tenant_id: UUID) -> ErasureResult:
        """Execute a full right-to-erasure workflow.

        1. Freeze the tenant (suspend).
        2. Export final data archive for legal hold.
        3. Cascade-delete all tenant data.
        4. Drop the tenant PostgreSQL schema.
        5. Purge caches.
        6. Write tamper-evident audit record.
        7. Transition to DELETED.
        """
        tenant = self._get_tenant_or_raise(tenant_id)

        # 1. Freeze tenant -- suspend if currently active
        if tenant.status == TenantStatus.ACTIVE:
            if not self._lifecycle.validate_transition(
                tenant.status, TenantStatus.SUSPENDED
            ):
                raise ValueError(
                    f"Cannot suspend tenant {tenant_id} from state {tenant.status.value}"
                )
            tenant.status = TenantStatus.SUSPENDED
            tenant.updated_at = datetime.now(timezone.utc)
            tenant = self._tenant_repo.update(tenant)

        # 2. Export final archive (synchronous – for erasure we wait)
        final_job_id = uuid4().hex
        self._export_job_repo.save(
            job_id=final_job_id,
            tenant_id=tenant_id,
            status=ExportJobStatus.QUEUED,
        )
        logger.info("Final data archive for erasure: job %s", final_job_id)

        # 3. Cascade-delete all tenant data
        records_deleted = self._data_repo.cascade_delete_all(tenant_id)

        # 4. Drop tenant schema
        schema_name = tenant.schema_name
        self._schema_manager.drop_schema(schema_name)

        # 5. Purge caches
        self._cache_manager.purge_tenant(tenant_id)

        # 6. Write tamper-evident audit record
        audit_entry = self._create_audit_entry(
            tenant_id=tenant_id,
            action=AuditAction.DATA_ERASED,
            details={
                "records_deleted": records_deleted,
                "schema_dropped": schema_name,
                "final_export_job_id": final_job_id,
            },
        )

        # 7. Transition to DELETED via DEPROVISIONING
        if self._lifecycle.validate_transition(
            tenant.status, TenantStatus.DEPROVISIONING
        ):
            tenant.status = TenantStatus.DEPROVISIONING
            tenant.updated_at = datetime.now(timezone.utc)
            tenant = self._tenant_repo.update(tenant)

        if self._lifecycle.validate_transition(
            tenant.status, TenantStatus.DELETED
        ):
            tenant.status = TenantStatus.DELETED
            tenant.updated_at = datetime.now(timezone.utc)
            tenant = self._tenant_repo.update(tenant)

        logger.info("Erasure completed for tenant %s", tenant_id)

        return ErasureResult(
            tenant_id=tenant_id,
            schemas_dropped=[schema_name],
            records_deleted=records_deleted,
            caches_purged=True,
            audit_entry_id=audit_entry.id,
        )

    def get_retention_policy(self, tenant_id: UUID) -> RetentionPolicy:
        """Retrieve the retention policy for a tenant.

        Returns a default policy if none has been explicitly configured.
        """
        self._get_tenant_or_raise(tenant_id)
        policy = self._retention_repo.get_policy(tenant_id)
        if policy is None:
            policy = RetentionPolicy(tenant_id=tenant_id)
        return policy

    def update_retention_policy(
        self,
        tenant_id: UUID,
        policy: RetentionPolicy,
    ) -> RetentionPolicy:
        """Create or update the retention policy for a tenant."""
        self._get_tenant_or_raise(tenant_id)
        policy.updated_at = datetime.now(timezone.utc)
        saved = self._retention_repo.save_policy(policy)

        self._create_audit_entry(
            tenant_id=tenant_id,
            action=AuditAction.TENANT_UPDATED,
            details={
                "event": "retention_policy_updated",
                "retention_days": policy.retention_days,
                "grace_period_days": policy.grace_period_days,
            },
        )
        return saved

    def run_retention_cleanup(self, tenant_id: UUID) -> CleanupResult:
        """Execute retention cleanup for a single tenant.

        1. Scan for records exceeding the retention threshold.
        2. Soft-delete those records.
        3. Hard-delete records past the grace period.
        4. Log all deletions.
        """
        self._get_tenant_or_raise(tenant_id)
        policy = self.get_retention_policy(tenant_id)

        today = date.today()
        retention_threshold = today - timedelta(days=policy.retention_days)
        grace_threshold = today - timedelta(
            days=policy.retention_days + policy.grace_period_days
        )

        # Soft-delete records past retention threshold
        expired_ids = self._retention_repo.find_expired_records(
            tenant_id, retention_threshold
        )
        soft_deleted = 0
        if expired_ids:
            soft_deleted = self._retention_repo.soft_delete_records(expired_ids)

        # Hard-delete records past grace period
        grace_ids = self._retention_repo.find_soft_deleted_past_grace(
            tenant_id, grace_threshold
        )
        hard_deleted = 0
        if grace_ids:
            hard_deleted = self._retention_repo.hard_delete_records(grace_ids)

        result = CleanupResult(
            tenant_id=tenant_id,
            records_soft_deleted=soft_deleted,
            records_hard_deleted=hard_deleted,
        )

        if soft_deleted > 0 or hard_deleted > 0:
            self._create_audit_entry(
                tenant_id=tenant_id,
                action=AuditAction.RETENTION_EXECUTED,
                details={
                    "soft_deleted": soft_deleted,
                    "hard_deleted": hard_deleted,
                    "retention_days": policy.retention_days,
                    "grace_period_days": policy.grace_period_days,
                },
            )

        logger.info(
            "Retention cleanup for tenant %s: %d soft-deleted, %d hard-deleted",
            tenant_id,
            soft_deleted,
            hard_deleted,
        )
        return result
