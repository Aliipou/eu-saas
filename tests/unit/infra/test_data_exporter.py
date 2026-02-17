"""Tests for infrastructure.gdpr.data_exporter."""

from __future__ import annotations

import json
import os
import tarfile
from typing import Any

import pytest

from infrastructure.gdpr.data_exporter import DataExporter, ExportConfig

# ------------------------------------------------------------------
# Mock database
# ------------------------------------------------------------------


class MockTenantDatabase:
    """In-memory stub satisfying the TenantDatabase protocol."""

    def __init__(self, tables: dict[str, list[dict[str, Any]]]) -> None:
        self._tables = tables

    async def list_tables(self, schema_name: str) -> list[str]:
        return list(self._tables.keys())

    async def fetch_all_rows(
        self,
        schema_name: str,
        table_name: str,
    ) -> list[dict[str, Any]]:
        return self._tables.get(table_name, [])


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


@pytest.fixture
def mock_db() -> MockTenantDatabase:
    return MockTenantDatabase(
        {
            "users": [{"id": "1", "name": "Alice"}, {"id": "2", "name": "Bob"}],
            "orders": [{"id": "100", "total": "9.99"}],
        }
    )


@pytest.fixture
def export_dir(tmp_path) -> str:
    return str(tmp_path)


# ------------------------------------------------------------------
# Tests
# ------------------------------------------------------------------


@pytest.mark.asyncio
class TestExportTenantData:
    async def test_creates_tar_gz_file(
        self,
        mock_db: MockTenantDatabase,
        export_dir: str,
    ) -> None:
        config = ExportConfig(export_directory=export_dir, default_format="json")
        exporter = DataExporter(db=mock_db, config=config)
        path = await exporter.export_tenant_data("tenant-1", "schema_1")

        assert path.endswith(".tar.gz")
        assert os.path.isfile(path)

    async def test_archive_contains_table_files_and_manifest(
        self,
        mock_db: MockTenantDatabase,
        export_dir: str,
    ) -> None:
        config = ExportConfig(export_directory=export_dir, default_format="json")
        exporter = DataExporter(db=mock_db, config=config)
        path = await exporter.export_tenant_data("tenant-1", "schema_1")

        with tarfile.open(path, "r:gz") as tar:
            names = tar.getnames()
        assert "tenant-1/users.json" in names
        assert "tenant-1/orders.json" in names
        assert "tenant-1/manifest.json" in names

    async def test_json_format_produces_json_files(
        self,
        mock_db: MockTenantDatabase,
        export_dir: str,
    ) -> None:
        config = ExportConfig(export_directory=export_dir, default_format="json")
        exporter = DataExporter(db=mock_db, config=config)
        path = await exporter.export_tenant_data("tenant-1", "schema_1")

        with tarfile.open(path, "r:gz") as tar:
            names = tar.getnames()
        table_files = [n for n in names if n != "tenant-1/manifest.json"]
        assert all(n.endswith(".json") for n in table_files)

    async def test_csv_format_produces_csv_files(
        self,
        mock_db: MockTenantDatabase,
        export_dir: str,
    ) -> None:
        config = ExportConfig(export_directory=export_dir)
        exporter = DataExporter(db=mock_db, config=config)
        path = await exporter.export_tenant_data(
            "tenant-1",
            "schema_1",
            output_format="csv",
        )

        with tarfile.open(path, "r:gz") as tar:
            names = tar.getnames()
        table_files = [n for n in names if n != "tenant-1/manifest.json"]
        assert all(n.endswith(".csv") for n in table_files)

    async def test_manifest_content(
        self,
        mock_db: MockTenantDatabase,
        export_dir: str,
    ) -> None:
        config = ExportConfig(export_directory=export_dir, default_format="json")
        exporter = DataExporter(db=mock_db, config=config)
        path = await exporter.export_tenant_data("tenant-1", "schema_1")

        with tarfile.open(path, "r:gz") as tar:
            member = tar.getmember("tenant-1/manifest.json")
            f = tar.extractfile(member)
            assert f is not None
            manifest = json.load(f)

        assert manifest["tenant_id"] == "tenant-1"
        assert manifest["schema"] == "schema_1"
        assert set(manifest["tables"]) == {"users", "orders"}
