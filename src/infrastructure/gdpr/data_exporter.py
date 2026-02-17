"""
GDPR data portability: export all tenant data to a portable archive.

Implements Article 20 (Right to data portability) by dumping every table in
the tenant's database schema to JSON or CSV and packaging the result into a
compressed ``.tar.gz`` archive.
"""

from __future__ import annotations

import csv
import io
import json
import os
import tarfile
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Protocol, Sequence


# ======================================================================
# Database abstraction
# ======================================================================

class TenantDatabase(Protocol):
    """
    Protocol that any database adapter must satisfy so the exporter
    remains decoupled from a specific ORM or driver.
    """

    async def list_tables(self, schema_name: str) -> list[str]:
        """Return all table names in the given schema."""
        ...

    async def fetch_all_rows(
        self, schema_name: str, table_name: str
    ) -> list[dict[str, Any]]:
        """Return every row in *table_name* as a list of dicts."""
        ...


# ======================================================================
# Data exporter
# ======================================================================

@dataclass
class ExportConfig:
    """Configuration knobs for the exporter."""

    export_directory: str = tempfile.gettempdir()
    default_format: str = "json"  # "json" or "csv"


class DataExporter:
    """
    Exports all data belonging to a tenant schema into a compressed archive.

    Usage::

        exporter = DataExporter(db=my_db_adapter)
        archive_path = await exporter.export_tenant_data("tenant_abc", "tenant_abc")
    """

    def __init__(
        self,
        db: TenantDatabase,
        config: Optional[ExportConfig] = None,
    ) -> None:
        self._db = db
        self._config = config or ExportConfig()

    async def export_tenant_data(
        self,
        tenant_id: str,
        schema_name: str,
        output_format: Optional[str] = None,
    ) -> str:
        """
        Export all tables in *schema_name* and return the path to the
        ``.tar.gz`` archive.

        Parameters
        ----------
        tenant_id:
            Logical tenant identifier (used in the archive filename).
        schema_name:
            Database schema that holds the tenant's tables.
        output_format:
            ``"json"`` (default) or ``"csv"``.

        Returns
        -------
        str
            Absolute path to the generated archive file.
        """

        fmt = (output_format or self._config.default_format).lower()
        if fmt not in ("json", "csv"):
            raise ValueError(f"Unsupported output format: {fmt}")

        tables = await self._db.list_tables(schema_name)

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        archive_name = f"export_{tenant_id}_{timestamp}.tar.gz"
        archive_path = os.path.join(self._config.export_directory, archive_name)

        with tarfile.open(archive_path, "w:gz") as tar:
            for table in tables:
                rows = await self._db.fetch_all_rows(schema_name, table)
                if fmt == "json":
                    content = self._rows_to_json(rows)
                    filename = f"{table}.json"
                else:
                    content = self._rows_to_csv(rows)
                    filename = f"{table}.csv"

                encoded = content.encode("utf-8")
                info = tarfile.TarInfo(name=f"{tenant_id}/{filename}")
                info.size = len(encoded)
                info.mtime = int(datetime.now(timezone.utc).timestamp())
                tar.addfile(info, io.BytesIO(encoded))

            # Include a manifest file.
            manifest = json.dumps(
                {
                    "tenant_id": tenant_id,
                    "schema": schema_name,
                    "format": fmt,
                    "tables": tables,
                    "exported_at": timestamp,
                },
                indent=2,
            ).encode("utf-8")
            manifest_info = tarfile.TarInfo(name=f"{tenant_id}/manifest.json")
            manifest_info.size = len(manifest)
            manifest_info.mtime = int(datetime.now(timezone.utc).timestamp())
            tar.addfile(manifest_info, io.BytesIO(manifest))

        return archive_path

    # ------------------------------------------------------------------
    # Serialisation helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _rows_to_json(rows: list[dict[str, Any]]) -> str:
        return json.dumps(rows, indent=2, default=str)

    @staticmethod
    def _rows_to_csv(rows: list[dict[str, Any]]) -> str:
        if not rows:
            return ""
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
        return output.getvalue()
