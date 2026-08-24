"""Initial schema — all 10 V1 tables.

Revision ID: 0001
Revises: (none)
Create Date: 2026-08-24
"""

from __future__ import annotations

import uuid
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: str | None = None
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # tbl_citizen_master
    # ------------------------------------------------------------------
    op.create_table(
        "tbl_citizen_master",
        sa.Column("citizen_id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("date_of_birth", sa.Date, nullable=False),
        sa.Column("gender", sa.String(20)),
        sa.Column("mobile_number", sa.String(15)),
        sa.Column("email_id", sa.String(255)),
        sa.Column("citizen_type", sa.String(20), nullable=False),
        sa.Column("registration_date", sa.Date, server_default=sa.text("CURRENT_DATE")),
        sa.Column("verification_status", sa.String(20), server_default="PENDING"),
    )

    # ------------------------------------------------------------------
    # tbl_demographic_profile
    # ------------------------------------------------------------------
    op.create_table(
        "tbl_demographic_profile",
        sa.Column("profile_id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("citizen_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tbl_citizen_master.citizen_id", ondelete="CASCADE"),
                  nullable=False, unique=True),
        sa.Column("education_level", sa.String(50)),
        sa.Column("occupation", sa.String(100)),
        sa.Column("family_size", sa.Integer),
        sa.Column("marital_status", sa.String(30)),
        sa.Column("social_category", sa.String(10)),
        sa.Column("disability_status", sa.String(30), server_default="NONE"),
        sa.Column("type_specific_metadata", postgresql.JSONB),
    )

    # ------------------------------------------------------------------
    # tbl_financial_profile
    # ------------------------------------------------------------------
    op.create_table(
        "tbl_financial_profile",
        sa.Column("financial_id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("citizen_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tbl_citizen_master.citizen_id", ondelete="CASCADE"),
                  nullable=False, unique=True),
        sa.Column("annual_income", sa.Numeric(15, 2)),
        sa.Column("employment_status", sa.String(30)),
        sa.Column("income_source", sa.String(100)),
        sa.Column("poverty_category", sa.String(10)),
        sa.Column("land_holding_size", sa.Numeric(8, 2)),
        sa.Column("is_bpl_card_holder", sa.Boolean, server_default="false"),
        sa.Column("is_income_tax_payer", sa.Boolean, server_default="false"),
    )

    # ------------------------------------------------------------------
    # tbl_location_profile
    # ------------------------------------------------------------------
    op.create_table(
        "tbl_location_profile",
        sa.Column("location_id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("citizen_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tbl_citizen_master.citizen_id", ondelete="CASCADE"),
                  nullable=False, unique=True),
        sa.Column("state", sa.String(100)),
        sa.Column("district", sa.String(100)),
        sa.Column("village_city", sa.String(150)),
        sa.Column("area_type", sa.String(15)),
    )

    # ------------------------------------------------------------------
    # tbl_scheme_master
    # ------------------------------------------------------------------
    op.create_table(
        "tbl_scheme_master",
        sa.Column("scheme_id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("scheme_name", sa.String(255), nullable=False),
        sa.Column("department_name", sa.String(255)),
        sa.Column("scheme_category", sa.String(50)),
        sa.Column("description", sa.Text),
        sa.Column("benefit_description", sa.Text),
        sa.Column("start_date", sa.Date),
        sa.Column("status", sa.String(20), server_default="ACTIVE"),
        sa.Column("official_source_url", sa.String(500)),
        sa.Column("application_url", sa.String(500)),
        sa.Column("last_verified_at", sa.Date),
        sa.Column("group_combining_operator", sa.String(5), server_default="AND"),
    )

    # ------------------------------------------------------------------
    # tbl_scheme_rule_group
    # ------------------------------------------------------------------
    op.create_table(
        "tbl_scheme_rule_group",
        sa.Column("group_id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("scheme_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tbl_scheme_master.scheme_id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("group_name", sa.String(100), nullable=False),
        sa.Column("intra_group_operator", sa.String(5), nullable=False),
        sa.Column("group_priority", sa.Integer, server_default="1"),
    )

    # ------------------------------------------------------------------
    # tbl_scheme_eligibility_rule
    # ------------------------------------------------------------------
    op.create_table(
        "tbl_scheme_eligibility_rule",
        sa.Column("rule_id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("scheme_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tbl_scheme_master.scheme_id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("group_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tbl_scheme_rule_group.group_id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("parameter_name", sa.String(100), nullable=False),
        sa.Column("operator", sa.String(5), nullable=False),
        sa.Column("required_value", sa.String(255), nullable=False),
        sa.Column("rule_description", sa.Text),
        sa.Column("rule_priority", sa.Integer, server_default="1"),
    )

    # ------------------------------------------------------------------
    # tbl_scheme_document_master
    # ------------------------------------------------------------------
    op.create_table(
        "tbl_scheme_document_master",
        sa.Column("document_id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("scheme_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tbl_scheme_master.scheme_id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("document_type", sa.String(100), nullable=False),
        sa.Column("mandatory_flag", sa.Boolean, server_default="true"),
        sa.Column("description", sa.Text),
    )

    # ------------------------------------------------------------------
    # tbl_eligibility_assessment
    # ------------------------------------------------------------------
    op.create_table(
        "tbl_eligibility_assessment",
        sa.Column("assessment_id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("citizen_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tbl_citizen_master.citizen_id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("scheme_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tbl_scheme_master.scheme_id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("eligibility_result", sa.Boolean, nullable=False),
        sa.Column("reason", sa.Text),
        sa.Column("evaluation_details", postgresql.JSONB),
        sa.Column("assessment_date", sa.Date, server_default=sa.text("CURRENT_DATE")),
        sa.UniqueConstraint("citizen_id", "scheme_id", name="uq_citizen_scheme_assessment"),
    )

    # ------------------------------------------------------------------
    # Indexes
    # ------------------------------------------------------------------
    op.create_index("ix_citizen_type", "tbl_citizen_master", ["citizen_type"])
    op.create_index("ix_scheme_category", "tbl_scheme_master", ["scheme_category"])
    op.create_index("ix_scheme_status", "tbl_scheme_master", ["status"])
    op.create_index("ix_assessment_citizen", "tbl_eligibility_assessment", ["citizen_id"])
    op.create_index("ix_rule_scheme", "tbl_scheme_eligibility_rule", ["scheme_id"])
    op.create_index("ix_rule_group", "tbl_scheme_eligibility_rule", ["group_id"])


def downgrade() -> None:
    op.drop_table("tbl_eligibility_assessment")
    op.drop_table("tbl_scheme_document_master")
    op.drop_table("tbl_scheme_eligibility_rule")
    op.drop_table("tbl_scheme_rule_group")
    op.drop_table("tbl_scheme_master")
    op.drop_table("tbl_location_profile")
    op.drop_table("tbl_financial_profile")
    op.drop_table("tbl_demographic_profile")
    op.drop_table("tbl_citizen_master")
