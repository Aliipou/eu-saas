"""
Right-to-Erasure (GDPR Article 17) handler.

Implements the complete lifecycle for permanently removing a tenant and all
associated data from the platform. Every step is logged and the overall
operation is designed to be idempotent and retryable.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Protocol

# ======================================================================
# Step tracking
# ======================================================================


class ErasureStep(str, Enum):
    FREEZE_TENANT = "freeze_tenant"
    EXPORT_FINAL_ARCHIVE = "export_final_archive"
    CASCADE_DELETE_DATA = "cascade_delete_data"
    DROP_SCHEMA = "drop_schema"
    ROTATE_ENCRYPTION_KEY = "rotate_encryption_key"
    PURGE_CACHES = "purge_caches"
    WRITE_AUDIT_RECORD = "write_audit_record"


@dataclass
class StepResult:
    step: ErasureStep
    success: bool
    detail: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class ErasureResult:
    """Final outcome of a full erasure run."""

    tenant_id: str
    success: bool
    steps: list[StepResult] = field(default_factory=list)
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None
    archive_path: str | None = None


# ======================================================================
# Backend protocol
# ======================================================================


class ErasureBackend(Protocol):
    """
    Abstract backend that the handler delegates actual work to.

    Each method corresponds to one erasure step. Implementations should
    raise on failure so the handler can record the error and decide whether
    to continue or abort.
    """

    async def freeze_tenant(self, tenant_id: str) -> None:
        """Disable all access for the tenant."""
        ...

    async def export_final_archive(self, tenant_id: str) -> str:
        """Create a final data export and return the archive path."""
        ...

    async def cascade_delete_data(self, tenant_id: str) -> None:
        """Delete all tenant rows across every table."""
        ...

    async def drop_schema(self, tenant_id: str) -> None:
        """Drop the tenant's dedicated database schema."""
        ...

    async def rotate_encryption_key(self, tenant_id: str) -> None:
        """Rotate or destroy encryption keys associated with the tenant."""
        ...

    async def purge_caches(self, tenant_id: str) -> None:
        """Evict all cached data belonging to the tenant."""
        ...

    async def write_audit_record(self, tenant_id: str, result: ErasureResult) -> None:
        """Persist a tamper-evident audit log entry for the erasure."""
        ...


# ======================================================================
# Erasure handler
# ======================================================================

logger = logging.getLogger(__name__)


class ErasureHandler:
    """
    Orchestrates the right-to-erasure workflow.

    The ``execute`` method runs every step in order. Each step is individually
    wrapped so that:

    * A failure in one step does **not** prevent the handler from attempting
      remaining steps (best-effort).
    * The entire ``execute`` call can be retried safely because each step
      implementation is expected to be idempotent.
    """

    # Ordered pipeline of steps.
    _PIPELINE: list[ErasureStep] = [
        ErasureStep.FREEZE_TENANT,
        ErasureStep.EXPORT_FINAL_ARCHIVE,
        ErasureStep.CASCADE_DELETE_DATA,
        ErasureStep.DROP_SCHEMA,
        ErasureStep.ROTATE_ENCRYPTION_KEY,
        ErasureStep.PURGE_CACHES,
        ErasureStep.WRITE_AUDIT_RECORD,
    ]

    def __init__(self, backend: ErasureBackend) -> None:
        self._backend = backend

    async def execute(self, tenant_id: str) -> ErasureResult:
        """
        Run the full erasure pipeline for *tenant_id*.

        Returns an ``ErasureResult`` summarising each step.
        """

        result = ErasureResult(tenant_id=tenant_id, success=True)
        logger.info("Starting erasure for tenant %s", tenant_id)

        for step in self._PIPELINE:
            step_result = await self._run_step(step, tenant_id, result)
            result.steps.append(step_result)
            if not step_result.success:
                result.success = False
                logger.error(
                    "Erasure step %s failed for tenant %s: %s",
                    step.value,
                    tenant_id,
                    step_result.detail,
                )

        result.completed_at = datetime.now(UTC)
        logger.info(
            "Erasure for tenant %s completed. success=%s",
            tenant_id,
            result.success,
        )
        return result

    # ------------------------------------------------------------------
    # Individual step runners
    # ------------------------------------------------------------------

    async def _run_step(
        self,
        step: ErasureStep,
        tenant_id: str,
        result: ErasureResult,
    ) -> StepResult:
        """Execute a single step, catching and recording any errors."""

        try:
            await self._dispatch(step, tenant_id, result)
            return StepResult(step=step, success=True)
        except Exception as exc:
            return StepResult(step=step, success=False, detail=str(exc))

    async def _dispatch(
        self,
        step: ErasureStep,
        tenant_id: str,
        result: ErasureResult,
    ) -> None:
        """Route *step* to the appropriate backend method."""

        if step == ErasureStep.FREEZE_TENANT:
            await self._backend.freeze_tenant(tenant_id)

        elif step == ErasureStep.EXPORT_FINAL_ARCHIVE:
            archive_path = await self._backend.export_final_archive(tenant_id)
            result.archive_path = archive_path

        elif step == ErasureStep.CASCADE_DELETE_DATA:
            await self._backend.cascade_delete_data(tenant_id)

        elif step == ErasureStep.DROP_SCHEMA:
            await self._backend.drop_schema(tenant_id)

        elif step == ErasureStep.ROTATE_ENCRYPTION_KEY:
            await self._backend.rotate_encryption_key(tenant_id)

        elif step == ErasureStep.PURGE_CACHES:
            await self._backend.purge_caches(tenant_id)

        elif step == ErasureStep.WRITE_AUDIT_RECORD:
            await self._backend.write_audit_record(tenant_id, result)

    # ------------------------------------------------------------------
    # Convenience: individual steps (for retry or partial re-runs)
    # ------------------------------------------------------------------

    async def freeze_tenant(self, tenant_id: str) -> StepResult:
        return await self._run_step(
            ErasureStep.FREEZE_TENANT, tenant_id, ErasureResult(tenant_id=tenant_id, success=True)
        )

    async def export_final_archive(self, tenant_id: str) -> StepResult:
        return await self._run_step(
            ErasureStep.EXPORT_FINAL_ARCHIVE,
            tenant_id,
            ErasureResult(tenant_id=tenant_id, success=True),
        )

    async def cascade_delete_data(self, tenant_id: str) -> StepResult:
        return await self._run_step(
            ErasureStep.CASCADE_DELETE_DATA,
            tenant_id,
            ErasureResult(tenant_id=tenant_id, success=True),
        )

    async def drop_schema(self, tenant_id: str) -> StepResult:
        return await self._run_step(
            ErasureStep.DROP_SCHEMA, tenant_id, ErasureResult(tenant_id=tenant_id, success=True)
        )

    async def rotate_encryption_key(self, tenant_id: str) -> StepResult:
        return await self._run_step(
            ErasureStep.ROTATE_ENCRYPTION_KEY,
            tenant_id,
            ErasureResult(tenant_id=tenant_id, success=True),
        )

    async def purge_caches(self, tenant_id: str) -> StepResult:
        return await self._run_step(
            ErasureStep.PURGE_CACHES, tenant_id, ErasureResult(tenant_id=tenant_id, success=True)
        )

    async def write_audit_record(self, tenant_id: str) -> StepResult:
        return await self._run_step(
            ErasureStep.WRITE_AUDIT_RECORD,
            tenant_id,
            ErasureResult(tenant_id=tenant_id, success=True),
        )
