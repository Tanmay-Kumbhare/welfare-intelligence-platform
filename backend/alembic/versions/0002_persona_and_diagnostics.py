"""Add persona filtering and diagnostic remediation columns.

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-07
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision: str = "0002"
down_revision: str = "0001"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    # tbl_scheme_master: persona tag for filtering
    op.add_column(
        "tbl_scheme_master",
        sa.Column("target_persona", sa.String(50), nullable=True),
    )
    op.create_index("ix_scheme_target_persona", "tbl_scheme_master", ["target_persona"])

    # tbl_scheme_eligibility_rule: diagnostic stage and remedy
    op.add_column(
        "tbl_scheme_eligibility_rule",
        sa.Column("failure_stage_code", sa.String(50), nullable=True),
    )
    op.add_column(
        "tbl_scheme_eligibility_rule",
        sa.Column("remedy_template", sa.Text, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("tbl_scheme_eligibility_rule", "remedy_template")
    op.drop_column("tbl_scheme_eligibility_rule", "failure_stage_code")
    op.drop_index("ix_scheme_target_persona", table_name="tbl_scheme_master")
    op.drop_column("tbl_scheme_master", "target_persona")
