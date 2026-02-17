"""Initial public schema — tenant registry and audit log.

Revision ID: 001
Revises: None
Create Date: 2026-02-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Tenant registry — lives in public schema
    op.create_table(
        "tenants",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(63), nullable=False, unique=True),
        sa.Column("owner_email", sa.String(255), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="PENDING"),
        sa.Column("schema_name", sa.String(63), nullable=False, unique=True),
        sa.Column("settings", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("metadata_", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        schema="public",
    )
    op.create_index("ix_tenants_slug", "tenants", ["slug"], schema="public")
    op.create_index("ix_tenants_status", "tenants", ["status"], schema="public")
    op.create_index("ix_tenants_owner_email", "tenants", ["owner_email"], schema="public")

    # Audit log — shared across all tenants, append-only
    op.create_table(
        "audit_log",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("actor_id", UUID(as_uuid=True), nullable=True),
        sa.Column("details", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column(
            "timestamp", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("previous_hash", sa.String(64), nullable=True),
        sa.Column("entry_hash", sa.String(64), nullable=False),
        schema="public",
    )
    op.create_index("ix_audit_log_tenant_id", "audit_log", ["tenant_id"], schema="public")
    op.create_index("ix_audit_log_action", "audit_log", ["action"], schema="public")
    op.create_index("ix_audit_log_timestamp", "audit_log", ["timestamp"], schema="public")


def downgrade() -> None:
    op.drop_table("audit_log", schema="public")
    op.drop_table("tenants", schema="public")
