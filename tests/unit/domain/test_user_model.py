"""Tests for src/domain/models/user.py"""

from uuid import UUID

from domain.models.user import TenantRole, User


class TestTenantRole:
    def test_enum_values(self):
        assert TenantRole.OWNER.value == "OWNER"
        assert TenantRole.ADMIN.value == "ADMIN"
        assert TenantRole.MEMBER.value == "MEMBER"
        assert TenantRole.VIEWER.value == "VIEWER"

    def test_enum_has_four_values(self):
        assert len(list(TenantRole)) == 4


class TestUser:
    def test_defaults(self):
        user = User()
        assert isinstance(user.id, UUID)
        assert isinstance(user.tenant_id, UUID)
        assert user.email == ""
        assert user.hashed_password == ""
        assert user.full_name == ""
        assert user.role == TenantRole.MEMBER
        assert user.is_active is True
        assert user.last_login is None

    def test_custom_role(self):
        user = User(role=TenantRole.OWNER, email="admin@example.com")
        assert user.role == TenantRole.OWNER
        assert user.email == "admin@example.com"

    def test_unique_ids(self):
        u1 = User()
        u2 = User()
        assert u1.id != u2.id
