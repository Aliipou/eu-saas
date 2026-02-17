"""Billing and cost management API endpoints."""

from __future__ import annotations

import calendar
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status

from infrastructure.container import get_billing_service
from application.services.billing_service import BillingService

from ...middleware.tenant_context import TenantContext, get_current_tenant
from .schemas import (
    AnomalyListResponse,
    AnomalyResponse,
    CostBreakdown,
    CostLineItem,
    CostProjection,
    ErrorResponse,
    InvoiceListResponse,
    InvoiceResponse,
    PaginationMeta,
)

router = APIRouter(prefix="/tenants/{tenant_id}", tags=["Billing & Costs"])

TenantID = Annotated[uuid.UUID, Path(description="Tenant identifier.")]


@router.get(
    "/costs",
    response_model=CostBreakdown,
    summary="Get cost breakdown",
    responses={
        200: {"description": "Cost breakdown for the requested period."},
        400: {"description": "Invalid date range.", "model": ErrorResponse},
        404: {"description": "Tenant not found.", "model": ErrorResponse},
    },
)
async def get_cost_breakdown(
    tenant_id: TenantID,
    start_date: date = Query(..., description="Period start date (inclusive)."),
    end_date: date = Query(..., description="Period end date (inclusive)."),
    group_by: str | None = Query(None),
    service: BillingService = Depends(get_billing_service),
) -> CostBreakdown:
    if end_date < start_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="end_date must be >= start_date.",
        )
    breakdown = service.get_cost_breakdown(tenant_id, start_date, end_date)
    line_items = [
        CostLineItem(
            service=k,
            amount=v,
            currency="EUR",
            unit="unit",
            quantity=v,
        )
        for k, v in breakdown.by_resource.items()
    ]
    return CostBreakdown(
        tenant_id=tenant_id,
        period_start=start_date,
        period_end=end_date,
        total_amount=breakdown.total,
        currency="EUR",
        line_items=line_items,
    )


@router.get(
    "/costs/current",
    response_model=CostBreakdown,
    summary="Current billing period costs",
)
async def get_current_costs(
    tenant_id: TenantID,
    service: BillingService = Depends(get_billing_service),
) -> CostBreakdown:
    today = date.today()
    period_start = today.replace(day=1)
    breakdown = service.get_cost_breakdown(tenant_id, period_start, today)
    line_items = [
        CostLineItem(service=k, amount=v, currency="EUR", unit="unit", quantity=v)
        for k, v in breakdown.by_resource.items()
    ]
    return CostBreakdown(
        tenant_id=tenant_id,
        period_start=period_start,
        period_end=today,
        total_amount=breakdown.total,
        currency="EUR",
        line_items=line_items,
    )


@router.get(
    "/costs/projection",
    response_model=CostProjection,
    summary="Cost projection for current month",
)
async def get_cost_projection(
    tenant_id: TenantID,
    service: BillingService = Depends(get_billing_service),
) -> CostProjection:
    projection = service.project_monthly_cost(tenant_id)
    today = date.today()
    _, last_day = calendar.monthrange(today.year, today.month)
    return CostProjection(
        tenant_id=tenant_id,
        billing_period_start=today.replace(day=1),
        billing_period_end=today.replace(day=last_day),
        actual_to_date=projection.actual_cost,
        projected_total=projection.projected_cost,
        confidence_interval_low=projection.actual_cost,
        confidence_interval_high=projection.projected_cost,
        currency="EUR",
    )


@router.get("/invoices", response_model=InvoiceListResponse, summary="List invoices")
async def list_invoices(
    tenant_id: TenantID,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: str | None = Query(None, alias="status"),
) -> InvoiceListResponse:
    return InvoiceListResponse(
        items=[],
        pagination=PaginationMeta(page=page, page_size=page_size, total_items=0, total_pages=0),
    )


@router.get("/invoices/{invoice_id}", response_model=InvoiceResponse, summary="Get invoice detail")
async def get_invoice(
    tenant_id: TenantID,
    invoice_id: Annotated[uuid.UUID, Path(description="Invoice identifier.")],
) -> InvoiceResponse:
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Invoice '{invoice_id}' not found for tenant '{tenant_id}'.",
    )


@router.get("/anomalies", response_model=AnomalyListResponse, summary="List cost anomalies")
async def list_anomalies(
    tenant_id: TenantID,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    severity: str | None = Query(None),
    acknowledged: bool | None = Query(None),
) -> AnomalyListResponse:
    return AnomalyListResponse(
        items=[],
        pagination=PaginationMeta(page=page, page_size=page_size, total_items=0, total_pages=0),
    )
