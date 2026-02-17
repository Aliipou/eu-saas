"""GDPR compliance API endpoints."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status

from infrastructure.container import get_gdpr_service

from .schemas import (
    AuditAction,
    AuditLogResponse,
    GDPRErasureRequest,
    GDPRErasureResponse,
    GDPRExportRequest,
    GDPRExportState,
    GDPRExportStatus,
    PaginationMeta,
    RetentionPolicyRequest,
    RetentionPolicyResponse,
)

if TYPE_CHECKING:
    from application.services.gdpr_service import GDPRService

router = APIRouter(prefix="/tenants/{tenant_id}", tags=["GDPR & Compliance"])

TenantID = Annotated[uuid.UUID, Path(description="Tenant identifier.")]
JobID = Annotated[uuid.UUID, Path(description="Export job identifier.")]


@router.post(
    "/gdpr/export",
    response_model=GDPRExportStatus,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Request a GDPR data export",
)
async def request_data_export(
    tenant_id: TenantID,
    body: GDPRExportRequest,
    service: GDPRService = Depends(get_gdpr_service),
) -> GDPRExportStatus:
    job_id = service.export_tenant_data(tenant_id)
    now = datetime.now(UTC)
    return GDPRExportStatus(
        job_id=uuid.UUID(job_id) if len(job_id) == 32 else uuid.uuid4(),
        tenant_id=tenant_id,
        status=GDPRExportState.PENDING,
        requested_at=now,
    )


@router.get("/gdpr/export/{job_id}", response_model=GDPRExportStatus, summary="Check export status")
async def get_export_status(
    tenant_id: TenantID,
    job_id: JobID,
    service: GDPRService = Depends(get_gdpr_service),
) -> GDPRExportStatus:
    try:
        service.get_export_status(str(job_id))
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Export job '{job_id}' not found for tenant '{tenant_id}'.",
        ) from exc
    return GDPRExportStatus(
        job_id=job_id,
        tenant_id=tenant_id,
        status=GDPRExportState.PENDING,
        requested_at=datetime.now(UTC),
    )


@router.post(
    "/gdpr/erase",
    response_model=GDPRErasureResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Initiate right-to-erasure",
)
async def request_erasure(
    tenant_id: TenantID,
    body: GDPRErasureRequest,
) -> GDPRErasureResponse:
    job_id = uuid.uuid4()
    return GDPRErasureResponse(
        job_id=job_id,
        tenant_id=tenant_id,
        data_subject_id=body.data_subject_id,
        status="ACCEPTED",
    )


@router.get(
    "/gdpr/retention", response_model=RetentionPolicyResponse, summary="Get retention policy"
)
async def get_retention_policy(
    tenant_id: TenantID,
    service: GDPRService = Depends(get_gdpr_service),
) -> RetentionPolicyResponse:
    policy = service.get_retention_policy(tenant_id)
    return RetentionPolicyResponse(
        tenant_id=tenant_id,
        default_retention_days=policy.retention_days,
        audit_log_retention_days=730,
        backup_retention_days=90,
        pii_retention_days=180,
        updated_at=policy.updated_at,
        updated_by=uuid.UUID(int=0),
    )


@router.put(
    "/gdpr/retention", response_model=RetentionPolicyResponse, summary="Update retention policy"
)
async def update_retention_policy(
    tenant_id: TenantID,
    body: RetentionPolicyRequest,
) -> RetentionPolicyResponse:
    now = datetime.now(UTC)
    return RetentionPolicyResponse(
        tenant_id=tenant_id,
        default_retention_days=body.default_retention_days,
        audit_log_retention_days=body.audit_log_retention_days,
        backup_retention_days=body.backup_retention_days,
        pii_retention_days=body.pii_retention_days,
        updated_at=now,
        updated_by=uuid.UUID(int=0),
    )


@router.get("/audit-log", response_model=AuditLogResponse, summary="Get audit trail")
async def get_audit_log(
    tenant_id: TenantID,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    action: AuditAction | None = Query(None),
    resource_type: str | None = Query(None),
    user_id: uuid.UUID | None = Query(None),
    start_date: datetime | None = Query(None),
    end_date: datetime | None = Query(None),
) -> AuditLogResponse:
    return AuditLogResponse(
        items=[],
        pagination=PaginationMeta(page=page, page_size=page_size, total_items=0, total_pages=0),
    )
