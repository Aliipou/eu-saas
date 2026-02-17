"""Tests for src/domain/exceptions/tenant_exceptions.py"""

import pytest

from domain.exceptions.tenant_exceptions import (
    CrossTenantAccessError,
    DomainError,
    InvalidStateTransitionError,
    SchemaCreationError,
    TenantAlreadyExistsError,
    TenantNotFoundError,
    TenantQuotaExceededError,
)


class TestDomainError:
    def test_default_attributes(self):
        exc = DomainError("something went wrong")
        assert exc.detail == "something went wrong"
        assert exc.title == "Domain Error"
        assert exc.status_code == 400
        assert exc.error_type == "about:blank"

    def test_custom_attributes(self):
        exc = DomainError(
            "custom",
            title="Custom",
            status_code=422,
            error_type="urn:custom",
        )
        assert exc.title == "Custom"
        assert exc.status_code == 422
        assert exc.error_type == "urn:custom"

    def test_is_exception(self):
        assert issubclass(DomainError, Exception)


class TestTenantNotFoundError:
    def test_attributes(self):
        exc = TenantNotFoundError("abc-123")
        assert exc.tenant_id == "abc-123"
        assert exc.status_code == 404
        assert exc.title == "Tenant Not Found"
        assert "abc-123" in exc.detail

    def test_inherits_domain_exception(self):
        assert issubclass(TenantNotFoundError, DomainError)


class TestInvalidStateTransitionError:
    def test_attributes(self):
        exc = InvalidStateTransitionError("ACTIVE", "PENDING")
        assert exc.current_state == "ACTIVE"
        assert exc.new_state == "PENDING"
        assert exc.status_code == 409
        assert exc.title == "Invalid State Transition"
        assert "ACTIVE" in exc.detail
        assert "PENDING" in exc.detail

    def test_inherits_domain_exception(self):
        assert issubclass(InvalidStateTransitionError, DomainError)


class TestTenantAlreadyExistsError:
    def test_attributes(self):
        exc = TenantAlreadyExistsError("my-tenant")
        assert exc.identifier == "my-tenant"
        assert exc.status_code == 409
        assert exc.title == "Tenant Conflict"
        assert "my-tenant" in exc.detail

    def test_inherits_domain_exception(self):
        assert issubclass(TenantAlreadyExistsError, DomainError)


class TestCrossTenantAccessError:
    def test_attributes(self):
        exc = CrossTenantAccessError("tenant-a", "tenant-b")
        assert exc.source_tenant == "tenant-a"
        assert exc.target_tenant == "tenant-b"
        assert exc.status_code == 403
        assert exc.title == "Cross-Tenant Access Denied"
        assert "tenant-a" in exc.detail
        assert "tenant-b" in exc.detail

    def test_inherits_domain_exception(self):
        assert issubclass(CrossTenantAccessError, DomainError)


class TestSchemaCreationError:
    def test_attributes(self):
        exc = SchemaCreationError("tenant_xyz", "connection refused")
        assert exc.schema_name == "tenant_xyz"
        assert exc.reason == "connection refused"
        assert exc.status_code == 500
        assert exc.title == "Schema Creation Failed"
        assert "tenant_xyz" in exc.detail
        assert "connection refused" in exc.detail

    def test_inherits_domain_exception(self):
        assert issubclass(SchemaCreationError, DomainError)


class TestTenantQuotaExceededError:
    def test_attributes(self):
        exc = TenantQuotaExceededError("t-1", "API_CALLS", "1000")
        assert exc.tenant_id == "t-1"
        assert exc.resource == "API_CALLS"
        assert exc.limit == "1000"
        assert exc.status_code == 429
        assert exc.title == "Quota Exceeded"
        assert "t-1" in exc.detail
        assert "API_CALLS" in exc.detail

    def test_inherits_domain_exception(self):
        assert issubclass(TenantQuotaExceededError, DomainError)


class TestStatusCodes:
    """Cross-check all status codes in one place."""

    @pytest.mark.parametrize(
        "exc_class, args, expected_code",
        [
            (TenantNotFoundError, ("x",), 404),
            (InvalidStateTransitionError, ("A", "B"), 409),
            (TenantAlreadyExistsError, ("x",), 409),
            (CrossTenantAccessError, ("a", "b"), 403),
            (SchemaCreationError, ("s", "r"), 500),
            (TenantQuotaExceededError, ("t", "r", "l"), 429),
        ],
    )
    def test_status_code(self, exc_class, args, expected_code):
        exc = exc_class(*args)
        assert exc.status_code == expected_code
