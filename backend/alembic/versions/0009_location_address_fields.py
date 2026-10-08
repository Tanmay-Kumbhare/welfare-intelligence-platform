"""add permanent and current address fields to location profile

Revision ID: 0009_location_address_fields
Revises: 0008_education_records
Create Date: 2026-10-08 19:00:00.000000

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0009_location_address_fields"
down_revision: str | None = "0008_education_records"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    op.add_column("tbl_location_profile", sa.Column("address_line_1", sa.String(length=255), nullable=True))
    op.add_column("tbl_location_profile", sa.Column("address_line_2", sa.String(length=255), nullable=True))
    op.add_column("tbl_location_profile", sa.Column("pincode", sa.String(length=10), nullable=True))
    op.add_column("tbl_location_profile", sa.Column("same_as_permanent", sa.Boolean(), nullable=False, server_default=sa.text("true")))
    op.add_column("tbl_location_profile", sa.Column("current_address", postgresql.JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("tbl_location_profile", "current_address")
    op.drop_column("tbl_location_profile", "same_as_permanent")
    op.drop_column("tbl_location_profile", "pincode")
    op.drop_column("tbl_location_profile", "address_line_2")
    op.drop_column("tbl_location_profile", "address_line_1")
