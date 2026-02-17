"""
Role-Based Access Control (RBAC) for the multi-tenant platform.

Defines a permission model where each ``TenantRole`` is mapped to a set of
``Permission`` values. FastAPI dependencies ``require_permission`` and
``require_role`` enforce access at the endpoint level.
"""

from __future__ import annotations

from enum import Enum, IntEnum
from typing import TYPE_CHECKING, Any

from fastapi import HTTPException, Request, status

if TYPE_CHECKING:
    from collections.abc import Callable

# ======================================================================
# Permissions
# ======================================================================


class Permission(str, Enum):
    """Fine-grained permissions used throughout the platform."""

    TENANT_READ = "tenant:read"
    TENANT_WRITE = "tenant:write"
    TENANT_ADMIN = "tenant:admin"

    USER_READ = "user:read"
    USER_WRITE = "user:write"

    BILLING_READ = "billing:read"
    BILLING_WRITE = "billing:write"

    GDPR_READ = "gdpr:read"
    GDPR_WRITE = "gdpr:write"

    AUDIT_READ = "audit:read"


# ======================================================================
# Roles  (ordered from least to most privileged)
# ======================================================================


class TenantRole(IntEnum):
    """
    Tenant-scoped roles ordered by privilege level.

    The integer value enables simple ``>=`` comparisons when enforcing a
    minimum role requirement.
    """

    VIEWER = 10
    MEMBER = 20
    ADMIN = 30
    OWNER = 40


# ======================================================================
# Role -> Permissions mapping
# ======================================================================

_ALL_PERMISSIONS: set[Permission] = set(Permission)

ROLE_PERMISSIONS: dict[TenantRole, set[Permission]] = {
    TenantRole.OWNER: _ALL_PERMISSIONS,
    TenantRole.ADMIN: _ALL_PERMISSIONS - {Permission.TENANT_ADMIN},
    TenantRole.MEMBER: {
        Permission.TENANT_READ,
        Permission.USER_READ,
        Permission.USER_WRITE,
        Permission.BILLING_READ,
        Permission.GDPR_READ,
        Permission.AUDIT_READ,
    },
    TenantRole.VIEWER: {
        Permission.TENANT_READ,
        Permission.USER_READ,
        Permission.BILLING_READ,
        Permission.GDPR_READ,
        Permission.AUDIT_READ,
    },
}


# ======================================================================
# Helper to extract the current user from the request
# ======================================================================


def _get_current_user(request: Request) -> dict[str, Any]:
    """
    Retrieve the authenticated user payload attached to the request.

    Middleware or an earlier dependency should populate ``request.state.user``
    with a dict containing at least ``role`` (str matching a TenantRole name).
    """
    user: dict[str, Any] | None = getattr(request.state, "user", None)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )
    return user


def _resolve_role(role_value: str) -> TenantRole:
    """Convert a role string (e.g. ``'ADMIN'``) to a ``TenantRole``."""
    try:
        return TenantRole[role_value.upper()]
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Unknown role: {role_value}",
        ) from exc


# ======================================================================
# FastAPI dependencies
# ======================================================================


def require_permission(permission: Permission) -> Callable[..., Any]:
    """
    Return a FastAPI dependency that verifies the current user holds
    the requested *permission* based on their tenant role.

    Usage::

        @router.get("/billing", dependencies=[Depends(require_permission(Permission.BILLING_READ))])
        async def get_billing(): ...
    """

    async def _check(request: Request) -> None:
        user = _get_current_user(request)
        role = _resolve_role(user["role"])
        allowed = ROLE_PERMISSIONS.get(role, set())
        if permission not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied. Required: {permission.value}",
            )

    return _check


def require_role(min_role: TenantRole) -> Callable[..., Any]:
    """
    Return a FastAPI dependency that enforces a minimum role level.

    Usage::

        @router.delete("/tenant", dependencies=[Depends(require_role(TenantRole.OWNER))])
        async def delete_tenant(): ...
    """

    async def _check(request: Request) -> None:
        user = _get_current_user(request)
        role = _resolve_role(user["role"])
        if role < min_role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient role. Required: {min_role.name}, current: {role.name}",
            )

    return _check
