"""Tenant schema tables — applied per-tenant schema.

Revision ID: 002
Revises: 001
Create Date: 2026-02-16

Run with: alembic -x tenant=<slug> upgrade head
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Users table — per-tenant
    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("role", sa.String(20), nullable=False, server_default="MEMBER"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_login", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_users_email", "users", ["email"])

    # Usage records — raw resource consumption data
    op.create_table(
        "usage_records",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("resource_type", sa.String(20), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("unit", sa.String(20), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_usage_records_resource_type", "usage_records", ["resource_type"])
    op.create_index("ix_usage_records_recorded_at", "usage_records", ["recorded_at"])

    # Cost records — calculated costs per resource per day
    op.create_table(
        "cost_records",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("date", sa.Date, nullable=False),
        sa.Column("resource_type", sa.String(20), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("unit_price", sa.Numeric(precision=10, scale=6), nullable=False),
        sa.Column("total_cost", sa.Numeric(precision=12, scale=4), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="EUR"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_cost_records_date", "cost_records", ["date"])
    op.create_index("ix_cost_records_resource_type", "cost_records", ["resource_type"])
    op.create_unique_constraint("uq_cost_records_date_resource", "cost_records", ["date", "resource_type"])

    # Invoices
    op.create_table(
        "invoices",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("period_start", sa.Date, nullable=False),
        sa.Column("period_end", sa.Date, nullable=False),
        sa.Column("line_items", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("total_amount", sa.Numeric(precision=12, scale=4), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="EUR"),
        sa.Column("status", sa.String(20), nullable=False, server_default="DRAFT"),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    # Cost anomalies
    op.create_table(
        "cost_anomalies",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("resource_type", sa.String(20), nullable=False),
        sa.Column("expected_value", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("actual_value", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("deviation_factor", sa.Numeric(precision=8, scale=4), nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("acknowledged", sa.Boolean, nullable=False, server_default=sa.text("false")),
    )

    # Data retention policy
    op.create_table(
        "retention_policy",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("transactional_data_days", sa.Integer, nullable=False, server_default="90"),
        sa.Column("log_data_days", sa.Integer, nullable=False, server_default="365"),
        sa.Column("user_activity_days", sa.Integer, nullable=False, server_default="180"),
        sa.Column("uploaded_files_days", sa.Integer, nullable=False, server_default="365"),
        sa.Column("grace_period_days", sa.Integer, nullable=False, server_default="30"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("retention_policy")
    op.drop_table("cost_anomalies")
    op.drop_table("invoices")
    op.drop_table("cost_records")
    op.drop_table("usage_records")
    op.drop_table("users")
