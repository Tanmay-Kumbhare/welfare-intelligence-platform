"""education records table

Revision ID: 0008_education_records
Revises: 0007_oauth_and_linking
Create Date: 2026-10-08 18:15:00.000000

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0008_education_records"
down_revision: str | None = "0007_oauth_and_linking"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    op.create_table(
        "tbl_education_record",
        sa.Column("record_id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "citizen_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tbl_citizen_master.citizen_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("level", sa.String(length=50), nullable=False),
        sa.Column("details", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("passing_year", sa.Integer(), nullable=True),
        sa.Column("percentage", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_education_record_citizen_id", "tbl_education_record", ["citizen_id"])
    op.create_index("ix_education_record_level", "tbl_education_record", ["level"])


def downgrade() -> None:
    op.drop_index("ix_education_record_level", table_name="tbl_education_record")
    op.drop_index("ix_education_record_citizen_id", table_name="tbl_education_record")
    op.drop_table("tbl_education_record")
