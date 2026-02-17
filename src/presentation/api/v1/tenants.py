"""Tenant management API endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status

from infrastructure.container import get_tenant_service
from application.services.tenant_service import TenantService
from domain.models.tenant import TenantStatus as DomainTenantStatus

from ...middleware.tenant_context import TenantContext, get_current_tenant
from .schemas import (
    ErrorResponse,
    PaginationMeta,
    TenantCreate,
    TenantListResponse,
    TenantResponse,
    TenantUpdate,
)

router = APIRouter(prefix="/tenants", tags=["Tenants"])

TenantID = Annotated[uuid.UUID, Path(description="Unique tenant identifier.")]


def _tenant_to_response(tenant: object) -> TenantResponse:
    """Map a domain Tenant to the API response schema."""
    return TenantResponse(
        id=tenant.id,
        name=tenant.name,
        slug=tenant.slug,
        status=tenant.status.value,
        tier="FREE",
        schema_name=tenant.schema_name,
        data_residency_region=tenant.metadata.get("data_residency_region", "eu-central-1"),
        admin_email=tenant.owner_email,
        metadata=tenant.metadata,
        created_at=tenant.created_at,
        updated_at=tenant.updated_at,
    )


@router.post(
    "",
    response_model=TenantResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new tenant",
    responses={
        201: {"description": "Tenant created and schema provisioned."},
        409: {"description": "Slug already taken.", "model": ErrorResponse},
        422: {"description": "Validation error.", "model": ErrorResponse},
    },
)
async def create_tenant(
    body: TenantCreate,
    service: TenantService = Depends(get_tenant_service),
) -> TenantResponse:
    tenant = service.create_tenant(
        name=body.name,
        slug=body.slug,
        owner_email=body.admin_email,
        settings={"tier": body.tier.value, "data_residency_region": body.data_residency_region},
    )
    return _tenant_to_response(tenant)


@router.get(
    "",
    response_model=TenantListResponse,
    summary="List all tenants (admin only)",
    responses={
        200: {"description": "Paginated tenant list."},
        403: {"description": "Insufficient permissions.", "model": ErrorResponse},
    },
)
async def list_tenants(
    page: int = Query(1, ge=1, description="Page number."),
    page_size: int = Query(20, ge=1, le=100, description="Items per page."),
    status_filter: str | None = Query(None, alias="status", description="Filter by tenant status."),
    service: TenantService = Depends(get_tenant_service),
) -> TenantListResponse:
    domain_status = None
    if status_filter:
        try:
            domain_status = DomainTenantStatus(status_filter)
        except ValueError:
            pass

    result = service.list_tenants(page=page, size=page_size, status_filter=domain_status)
    items = [_tenant_to_response(t) for t in result.items]

    return TenantListResponse(
        items=items,
        pagination=PaginationMeta(
            page=result.page,
            page_size=result.size,
            total_items=result.total,
            total_pages=result.pages,
        ),
    )


@router.get(
    "/{tenant_id}",
    response_model=TenantResponse,
    summary="Get tenant details",
    responses={
        200: {"description": "Tenant details."},
        404: {"description": "Tenant not found.", "model": ErrorResponse},
    },
)
async def get_tenant(
    tenant_id: TenantID,
    service: TenantService = Depends(get_tenant_service),
) -> TenantResponse:
    tenant = service.get_tenant(tenant_id)
    return _tenant_to_response(tenant)


@router.patch(
    "/{tenant_id}",
    response_model=TenantResponse,
    summary="Update tenant settings",
    responses={
        200: {"description": "Tenant updated."},
        404: {"description": "Tenant not found.", "model": ErrorResponse},
        422: {"description": "Validation error.", "model": ErrorResponse},
    },
)
async def update_tenant(
    tenant_id: TenantID,
    body: TenantUpdate,
    service: TenantService = Depends(get_tenant_service),
) -> TenantResponse:
    updates = body.model_dump(exclude_none=True)
    tenant = service.update_tenant(tenant_id, updates)
    return _tenant_to_response(tenant)


@router.post(
    "/{tenant_id}/suspend",
    response_model=TenantResponse,
    summary="Suspend tenant",
    responses={
        200: {"description": "Tenant suspended."},
        404: {"description": "Tenant not found.", "model": ErrorResponse},
        409: {"description": "Tenant already suspended.", "model": ErrorResponse},
    },
)
async def suspend_tenant(
    tenant_id: TenantID,
    service: TenantService = Depends(get_tenant_service),
) -> TenantResponse:
    tenant = service.suspend_tenant(tenant_id)
    return _tenant_to_response(tenant)


@router.post(
    "/{tenant_id}/activate",
    response_model=TenantResponse,
    summary="Reactivate tenant",
    responses={
        200: {"description": "Tenant reactivated."},
        404: {"description": "Tenant not found.", "model": ErrorResponse},
        409: {"description": "Tenant not in a suspendable state.", "model": ErrorResponse},
    },
)
async def activate_tenant(
    tenant_id: TenantID,
    service: TenantService = Depends(get_tenant_service),
) -> TenantResponse:
    tenant = service.activate_tenant(tenant_id)
    return _tenant_to_response(tenant)


@router.delete(
    "/{tenant_id}",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Initiate tenant deprovisioning",
    responses={
        202: {"description": "Deprovisioning initiated."},
        404: {"description": "Tenant not found.", "model": ErrorResponse},
    },
)
async def delete_tenant(
    tenant_id: TenantID,
    service: TenantService = Depends(get_tenant_service),
) -> dict:
    tenant = service.deprovision_tenant(tenant_id)
    return {
        "status": tenant.status.value,
        "tenant_id": str(tenant.id),
        "message": "Tenant deprovisioning has been initiated.",
    }
