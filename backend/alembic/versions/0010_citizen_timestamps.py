"""add timestamps and profile_version to citizen master

Revision ID: 0010_citizen_timestamps
Revises: 0009_location_address_fields
Create Date: 2026-10-08 19:30:00.000000

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0010_citizen_timestamps"
down_revision: str | None = "0009_location_address_fields"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    op.add_column(
        "tbl_citizen_master",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.add_column(
        "tbl_citizen_master",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.add_column(
        "tbl_citizen_master",
        sa.Column(
            "profile_version",
            sa.Integer(),
            server_default="1",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("tbl_citizen_master", "profile_version")
    op.drop_column("tbl_citizen_master", "updated_at")
    op.drop_column("tbl_citizen_master", "created_at")
