from __future__ import annotations


class DomainException(Exception):
    """Base class for all domain-layer exceptions.

    Carries HTTP-mapping metadata so the presentation layer can produce
    RFC 9457 Problem Details without knowing exception internals.
    """

    def __init__(
        self,
        detail: str = "",
        *,
        title: str = "Domain Error",
        status_code: int = 400,
        error_type: str = "about:blank",
    ) -> None:
        super().__init__(detail)
        self.detail = detail
        self.title = title
        self.status_code = status_code
        self.error_type = error_type


class TenantNotFoundError(DomainException):
    def __init__(self, tenant_id: str = "") -> None:
        self.tenant_id = tenant_id
        super().__init__(
            detail=f"Tenant not found: {tenant_id}",
            title="Tenant Not Found",
            status_code=404,
            error_type="https://api.eu-platform.example/problems/tenant-not-found",
        )


class InvalidStateTransitionError(DomainException):
    def __init__(self, current_state: str = "", new_state: str = "") -> None:
        self.current_state = current_state
        self.new_state = new_state
        super().__init__(
            detail=f"Invalid state transition from {current_state} to {new_state}",
            title="Invalid State Transition",
            status_code=409,
            error_type="https://api.eu-platform.example/problems/invalid-transition",
        )


class TenantAlreadyExistsError(DomainException):
    def __init__(self, identifier: str = "") -> None:
        self.identifier = identifier
        super().__init__(
            detail=f"Tenant already exists: {identifier}",
            title="Tenant Conflict",
            status_code=409,
            error_type="https://api.eu-platform.example/problems/tenant-conflict",
        )


class CrossTenantAccessError(DomainException):
    def __init__(self, source_tenant: str = "", target_tenant: str = "") -> None:
        self.source_tenant = source_tenant
        self.target_tenant = target_tenant
        super().__init__(
            detail=f"Cross-tenant access denied: {source_tenant} -> {target_tenant}",
            title="Cross-Tenant Access Denied",
            status_code=403,
            error_type="https://api.eu-platform.example/problems/cross-tenant-access",
        )


class SchemaCreationError(DomainException):
    def __init__(self, schema_name: str = "", reason: str = "") -> None:
        self.schema_name = schema_name
        self.reason = reason
        super().__init__(
            detail=f"Failed to create schema '{schema_name}': {reason}",
            title="Schema Creation Failed",
            status_code=500,
            error_type="https://api.eu-platform.example/problems/schema-creation",
        )


class TenantQuotaExceededError(DomainException):
    def __init__(self, tenant_id: str = "", resource: str = "", limit: str = "") -> None:
        self.tenant_id = tenant_id
        self.resource = resource
        self.limit = limit
        super().__init__(
            detail=f"Tenant {tenant_id} exceeded quota for {resource} (limit: {limit})",
            title="Quota Exceeded",
            status_code=429,
            error_type="https://api.eu-platform.example/problems/quota-exceeded",
        )
