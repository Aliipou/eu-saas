"""Tests for src/domain/services/tenant_lifecycle.py"""

import pytest

from domain.models.tenant import TenantStatus
from domain.services.tenant_lifecycle import TenantLifecycleService


@pytest.fixture
def service():
    return TenantLifecycleService()


class TestValidateTransition:
    @pytest.mark.parametrize(
        "current, new",
        [
            (TenantStatus.PENDING, TenantStatus.PROVISIONING),
            (TenantStatus.PENDING, TenantStatus.DELETED),
            (TenantStatus.PROVISIONING, TenantStatus.ACTIVE),
            (TenantStatus.PROVISIONING, TenantStatus.DELETED),
            (TenantStatus.ACTIVE, TenantStatus.SUSPENDED),
            (TenantStatus.ACTIVE, TenantStatus.DEPROVISIONING),
            (TenantStatus.SUSPENDED, TenantStatus.ACTIVE),
            (TenantStatus.SUSPENDED, TenantStatus.DEPROVISIONING),
            (TenantStatus.DEPROVISIONING, TenantStatus.DELETED),
        ],
    )
    def test_valid_transitions(self, service, current, new):
        assert service.validate_transition(current, new) is True

    @pytest.mark.parametrize(
        "current, new",
        [
            (TenantStatus.ACTIVE, TenantStatus.PENDING),
            (TenantStatus.DELETED, TenantStatus.ACTIVE),
            (TenantStatus.DELETED, TenantStatus.PENDING),
            (TenantStatus.PENDING, TenantStatus.ACTIVE),
            (TenantStatus.PROVISIONING, TenantStatus.SUSPENDED),
            (TenantStatus.DEPROVISIONING, TenantStatus.ACTIVE),
        ],
    )
    def test_invalid_transitions(self, service, current, new):
        assert service.validate_transition(current, new) is False


class TestGetTransitionActions:
    def test_pending_to_provisioning(self, service):
        actions = service.get_transition_actions(TenantStatus.PENDING, TenantStatus.PROVISIONING)
        assert actions == [
            "create_schema",
            "initialize_default_settings",
            "send_provisioning_notification",
        ]

    def test_provisioning_to_active(self, service):
        actions = service.get_transition_actions(TenantStatus.PROVISIONING, TenantStatus.ACTIVE)
        assert actions == [
            "activate_schema",
            "enable_api_access",
            "send_welcome_notification",
        ]

    def test_active_to_suspended(self, service):
        actions = service.get_transition_actions(TenantStatus.ACTIVE, TenantStatus.SUSPENDED)
        assert actions == [
            "disable_api_access",
            "send_suspension_notification",
        ]

    def test_active_to_deprovisioning(self, service):
        actions = service.get_transition_actions(TenantStatus.ACTIVE, TenantStatus.DEPROVISIONING)
        assert actions == [
            "disable_api_access",
            "schedule_data_export",
            "send_deprovisioning_notification",
        ]

    def test_suspended_to_active(self, service):
        actions = service.get_transition_actions(TenantStatus.SUSPENDED, TenantStatus.ACTIVE)
        assert actions == [
            "enable_api_access",
            "send_reactivation_notification",
        ]

    def test_deprovisioning_to_deleted(self, service):
        actions = service.get_transition_actions(TenantStatus.DEPROVISIONING, TenantStatus.DELETED)
        assert actions == [
            "delete_schema",
            "purge_tenant_data",
            "send_deletion_confirmation",
        ]

    def test_pending_to_deleted(self, service):
        actions = service.get_transition_actions(TenantStatus.PENDING, TenantStatus.DELETED)
        assert actions == ["send_cancellation_notification"]

    def test_invalid_transition_returns_empty_list(self, service):
        actions = service.get_transition_actions(TenantStatus.DELETED, TenantStatus.ACTIVE)
        assert actions == []
