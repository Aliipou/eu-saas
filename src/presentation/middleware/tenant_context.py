"""
Tenant context middleware for the EU Multi-Tenant Cloud Platform.

Extracts and validates the current tenant from incoming requests via JWT
claims or the ``X-Tenant-ID`` header, then makes the resolved context
available through ``request.state`` and a FastAPI dependency.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException, Request, status
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse, Response

# ---------------------------------------------------------------------------
# Public endpoints that do NOT require a tenant context
# ---------------------------------------------------------------------------

PUBLIC_PATH_PREFIXES: tuple[str, ...] = (
    "/health",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/api/v1/auth/login",
    "/api/v1/auth/register",
    "/api/v1/auth/refresh",
)


# ---------------------------------------------------------------------------
# TenantContext value object
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TenantContext:
    """Immutable value object that holds the resolved tenant information for
    the current request.

    Attributes:
        tenant_id:   Unique tenant UUID.
        tenant_slug: URL-safe slug (e.g. ``acme-gmbh``).
        schema_name: Postgres schema used for this tenant's data isolation.
        tier:        Subscription tier (used for rate-limit / feature checks).
        status:      Current tenant lifecycle status.
    """

    tenant_id: uuid.UUID
    tenant_slug: str
    schema_name: str
    tier: str = "FREE"
    status: str = "ACTIVE"


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------


class TenantContextMiddleware(BaseHTTPMiddleware):
    """Starlette middleware that resolves the tenant for every non-public
    request and attaches a :class:`TenantContext` to ``request.state``.

    Resolution order:

    1. ``tenant_id`` claim inside a validated JWT (set by auth middleware).
    2. ``X-Tenant-ID`` request header (useful for service-to-service calls).

    If the tenant cannot be resolved, or the tenant is not ``ACTIVE``, a
    ``403`` / ``404`` JSON error is returned immediately.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Skip public / documentation routes
        if self._is_public(request.url.path):
            request.state.tenant_context = None
            return await call_next(request)

        tenant_id = self._extract_tenant_id(request)
        if tenant_id is None:
            return self._problem_response(
                status_code=status.HTTP_403_FORBIDDEN,
                title="Missing Tenant Context",
                detail=(
                    "A tenant identifier is required. Provide a valid JWT with a "
                    "'tenant_id' claim or set the X-Tenant-ID header."
                ),
            )

        # ------------------------------------------------------------------
        # Validate the tenant exists and is active.
        # In production this would hit a cache-backed TenantRepository; here
        # we provide a pluggable lookup via ``request.app.state``.
        # ------------------------------------------------------------------
        tenant_record = await self._resolve_tenant(request, tenant_id)

        if tenant_record is None:
            return self._problem_response(
                status_code=status.HTTP_404_NOT_FOUND,
                title="Tenant Not Found",
                detail=f"Tenant with id '{tenant_id}' does not exist.",
                instance=request.url.path,
            )

        if tenant_record.get("status") != "ACTIVE":
            return self._problem_response(
                status_code=status.HTTP_403_FORBIDDEN,
                title="Tenant Inactive",
                detail=(
                    f"Tenant '{tenant_id}' is currently "
                    f"'{tenant_record.get('status', 'UNKNOWN')}'. "
                    "Only ACTIVE tenants may access the API."
                ),
                instance=request.url.path,
            )

        request.state.tenant_context = TenantContext(
            tenant_id=uuid.UUID(str(tenant_id)),
            tenant_slug=tenant_record.get("slug", ""),
            schema_name=tenant_record.get("schema_name", ""),
            tier=tenant_record.get("tier", "FREE"),
            status=tenant_record.get("status", "ACTIVE"),
        )

        return await call_next(request)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _is_public(path: str) -> bool:
        return any(path.startswith(prefix) for prefix in PUBLIC_PATH_PREFIXES)

    @staticmethod
    def _extract_tenant_id(request: Request) -> str | None:
        """Return the tenant id string from JWT claims or header."""
        # 1. JWT claims (populated by an upstream auth middleware / dependency)
        jwt_claims: dict[str, Any] | None = getattr(request.state, "jwt_claims", None)
        if jwt_claims and "tenant_id" in jwt_claims:
            return str(jwt_claims["tenant_id"])

        # 2. Explicit header
        header_value = request.headers.get("X-Tenant-ID")
        if header_value:
            # Basic UUID format validation
            try:
                uuid.UUID(header_value)
                return header_value
            except ValueError:
                return None

        return None

    @staticmethod
    async def _resolve_tenant(request: Request, tenant_id: str) -> dict[str, Any] | None:
        """Look up the tenant record.

        If the application has a ``tenant_repository`` on ``app.state`` we
        delegate to it; otherwise we return a stub so the middleware is
        testable in isolation.
        """
        repo = getattr(request.app.state, "tenant_repository", None)
        if repo is not None:
            return await repo.get_by_id(tenant_id)  # type: ignore[no-any-return]

        # Fallback: accept any well-formed UUID and assume ACTIVE.  Remove
        # this branch once the real repository is wired up.
        try:
            uid = uuid.UUID(tenant_id)
        except ValueError:
            return None
        return {
            "id": str(uid),
            "slug": "default",
            "schema_name": f"tenant_{uid.hex[:12]}",
            "tier": "FREE",
            "status": "ACTIVE",
        }

    @staticmethod
    def _problem_response(
        status_code: int,
        title: str,
        detail: str,
        instance: str | None = None,
    ) -> JSONResponse:
        """Return an RFC 9457 Problem Details JSON response."""
        body: dict[str, Any] = {
            "type": "about:blank",
            "title": title,
            "status": status_code,
            "detail": detail,
        }
        if instance:
            body["instance"] = instance
        return JSONResponse(
            status_code=status_code,
            content=body,
            media_type="application/problem+json",
        )


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------


async def get_current_tenant(request: Request) -> TenantContext:
    """FastAPI dependency that returns the :class:`TenantContext` set by
    :class:`TenantContextMiddleware`.

    Raises:
        HTTPException(403): If no tenant context is available (should not
            happen for protected routes if the middleware is installed).
    """
    ctx: TenantContext | None = getattr(request.state, "tenant_context", None)
    if ctx is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant context is not available for this request.",
        )
    return ctx
