"""Integration tests for TenantSchemaManager — requires PostgreSQL.

These tests use testcontainers to spin up a real PostgreSQL instance
and exercise the schema lifecycle (create, exists, list, drop, size).
"""

from __future__ import annotations

import pytest

from infrastructure.database.tenant_schema_manager import TenantSchemaManager, _sanitise_slug


@pytest.mark.integration
class TestSanitiseSlug:
    """Unit-level checks for the slug sanitiser (no DB needed)."""

    def test_valid_slug(self):
        assert _sanitise_slug("acme-corp") == "acme_corp"

    def test_slug_with_underscores(self):
        assert _sanitise_slug("my_tenant") == "my_tenant"

    def test_invalid_slug_uppercase(self):
        with pytest.raises(ValueError):
            _sanitise_slug("INVALID")

    def test_invalid_slug_spaces(self):
        with pytest.raises(ValueError):
            _sanitise_slug("bad slug")

    def test_invalid_slug_starts_with_hyphen(self):
        with pytest.raises(ValueError):
            _sanitise_slug("-bad")


@pytest.mark.integration
class TestTenantSchemaManager:
    """Full integration tests requiring a live PostgreSQL database."""

    def test_create_schema(self, sync_engine):
        mgr = TenantSchemaManager(sync_engine)
        schema = mgr.create_schema("int-test-create")
        assert schema == "tenant_int_test_create"
        assert mgr.schema_exists("int-test-create")
        # cleanup
        mgr.drop_schema("int-test-create")

    def test_create_duplicate_raises(self, sync_engine):
        mgr = TenantSchemaManager(sync_engine)
        mgr.create_schema("int-test-dup")
        with pytest.raises(RuntimeError, match="already exists"):
            mgr.create_schema("int-test-dup")
        mgr.drop_schema("int-test-dup")

    def test_drop_schema(self, sync_engine):
        mgr = TenantSchemaManager(sync_engine)
        mgr.create_schema("int-test-drop")
        mgr.drop_schema("int-test-drop")
        assert not mgr.schema_exists("int-test-drop")

    def test_drop_nonexistent_raises(self, sync_engine):
        mgr = TenantSchemaManager(sync_engine)
        with pytest.raises(RuntimeError, match="does not exist"):
            mgr.drop_schema("nonexistent-schema")

    def test_list_schemas(self, sync_engine):
        mgr = TenantSchemaManager(sync_engine)
        mgr.create_schema("int-test-list-a")
        mgr.create_schema("int-test-list-b")
        schemas = mgr.list_schemas()
        assert "tenant_int_test_list_a" in schemas
        assert "tenant_int_test_list_b" in schemas
        mgr.drop_schema("int-test-list-a")
        mgr.drop_schema("int-test-list-b")

    def test_schema_exists_false(self, sync_engine):
        mgr = TenantSchemaManager(sync_engine)
        assert not mgr.schema_exists("does-not-exist")

    def test_get_schema_size(self, sync_engine):
        mgr = TenantSchemaManager(sync_engine)
        mgr.create_schema("int-test-size")
        size = mgr.get_schema_size("int-test-size")
        assert isinstance(size, int)
        assert size >= 0
        mgr.drop_schema("int-test-size")

    def test_get_schema_size_nonexistent_raises(self, sync_engine):
        mgr = TenantSchemaManager(sync_engine)
        with pytest.raises(RuntimeError, match="does not exist"):
            mgr.get_schema_size("nonexistent-size")
