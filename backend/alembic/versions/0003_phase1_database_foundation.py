"""Phase 1 database foundation: dynamic forms, submissions, profile facts,
domain profiles, scheme sources, ingestion runs, and assessment upgrades.

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-15

Safety:
- Entirely ADDITIVE: no existing tables or columns are dropped or altered
  destructively. Only new tables, new columns on existing tables, and new
  indexes are created.
- Fully reversible: downgrade() drops exactly what upgrade() created, in
  reverse dependency order. Existing V1 columns (including the legacy
  eligibility_result boolean) are untouched.
- Compatible with the 7 seeded schemes: tbl_scheme_master additions are all
  nullable; no seed data is modified.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str = "0002"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None

# Timestamp type used for all created_at / updated_at columns.
TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    # ==============================================================
    # PART A — DYNAMIC FORM FOUNDATION
    # ==============================================================

    op.create_table(
        "tbl_form_definition",
        sa.Column("form_id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("form_code", sa.String(100), nullable=False, index=True),
        sa.Column("form_name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("target_citizen_type", sa.String(20)),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("status", sa.String(20), server_default="DRAFT"),
        sa.Column("created_at", TS, nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", TS, nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("form_code", "version", name="uq_form_code_version"),
    )

    op.create_table(
        "tbl_form_section",
        sa.Column("section_id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("form_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tbl_form_definition.form_id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("section_code", sa.String(100), nullable=False),
        sa.Column("section_name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("display_order", sa.Integer, nullable=False, server_default="1"),
        sa.Column("status", sa.String(20), server_default="ACTIVE"),
        sa.Column("created_at", TS, nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", TS, nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("form_id", "section_code", name="uq_form_section_code"),
    )
    op.create_index("ix_form_section_form", "tbl_form_section", ["form_id"])

    op.create_table(
        "tbl_form_question",
        sa.Column("question_id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("section_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tbl_form_section.section_id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("question_code", sa.String(100), nullable=False),
        sa.Column("question_text", sa.String(500), nullable=False),
        # text|number|decimal|date|boolean|single_choice|multi_choice|dropdown|file|location
        sa.Column("question_type", sa.String(30), nullable=False),
        # STRING|INTEGER|DECIMAL|BOOLEAN|DATE|JSON
        sa.Column("data_type", sa.String(20), nullable=False, server_default="STRING"),
        sa.Column("required", sa.Boolean, server_default=sa.text("false")),
        sa.Column("display_order", sa.Integer, nullable=False, server_default="1"),
        sa.Column("profile_field", sa.String(100)),
        sa.Column("validation_rule", postgresql.JSONB),
        sa.Column("help_text", sa.Text),
        sa.Column("placeholder", sa.String(255)),
        sa.Column("status", sa.String(20), server_default="ACTIVE"),
        sa.Column("created_at", TS, nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", TS, nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_form_question_section", "tbl_form_question", ["section_id"])
    op.create_index("ix_form_question_code", "tbl_form_question", ["question_code"])

    op.create_table(
        "tbl_form_question_option",
        sa.Column("option_id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("question_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tbl_form_question.question_id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("option_code", sa.String(100), nullable=False),
        sa.Column("option_label", sa.String(255), nullable=False),
        sa.Column("display_order", sa.Integer, nullable=False, server_default="1"),
        sa.Column("status", sa.String(20), server_default="ACTIVE"),
        sa.UniqueConstraint("question_id", "option_code", name="uq_question_option_code"),
    )
    op.create_index("ix_form_option_question", "tbl_form_question_option", ["question_id"])

    op.create_table(
        "tbl_form_condition",
        sa.Column("condition_id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        # Question whose visibility/requirement is affected
        sa.Column("question_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tbl_form_question.question_id", ondelete="CASCADE"),
                  nullable=False),
        # Question whose answer drives the condition
        sa.Column("depends_on_question_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tbl_form_question.question_id", ondelete="CASCADE"),
                  nullable=False),
        # EQUALS|NOT_EQUALS|GREATER_THAN|LESS_THAN|GREATER_THAN_OR_EQUAL|
        # LESS_THAN_OR_EQUAL|IN|NOT_IN|IS_EMPTY|IS_NOT_EMPTY
        sa.Column("operator", sa.String(30), nullable=False),
        sa.Column("comparison_value", sa.String(255)),
        # SHOW|HIDE|REQUIRE
        sa.Column("action", sa.String(20), nullable=False, server_default="SHOW"),
        # Same group = AND; different groups = OR (simple grouping only).
        sa.Column("condition_group", sa.Integer, nullable=False, server_default="1"),
        sa.Column("created_at", TS, nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", TS, nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_form_condition_question", "tbl_form_condition", ["question_id"])
    op.create_index("ix_form_condition_depends_on", "tbl_form_condition", ["depends_on_question_id"])

    # ==============================================================
    # PART B — FORM SUBMISSIONS
    # ==============================================================

    op.create_table(
        "tbl_form_submission",
        sa.Column("submission_id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("citizen_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tbl_citizen_master.citizen_id", ondelete="CASCADE"),
                  nullable=False),
        # RESTRICT: never silently delete a submission's referenced form.
        sa.Column("form_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tbl_form_definition.form_id", ondelete="RESTRICT"),
                  nullable=False),
        # Snapshot of the form version this submission answered.
        sa.Column("form_version", sa.Integer, nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="DRAFT"),
        sa.Column("started_at", TS, nullable=False, server_default=sa.text("now()")),
        sa.Column("completed_at", TS),
        sa.Column("completion_percentage", sa.SmallInteger, nullable=False, server_default="0"),
        sa.Column("created_at", TS, nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", TS, nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "status IN ('DRAFT','IN_PROGRESS','COMPLETED','ABANDONED')",
            name="ck_form_submission_status",
        ),
    )
    op.create_index("ix_form_submission_citizen", "tbl_form_submission", ["citizen_id"])
    op.create_index("ix_form_submission_form", "tbl_form_submission", ["form_id"])

    op.create_table(
        "tbl_form_answer",
        sa.Column("answer_id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("submission_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tbl_form_submission.submission_id", ondelete="CASCADE"),
                  nullable=False),
        # RESTRICT: answers are historical evidence; questions are not deleted
        # while any answer references them.
        sa.Column("question_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tbl_form_question.question_id", ondelete="RESTRICT"),
                  nullable=False),
        # Typed value columns — exactly one populated per data_type.
        sa.Column("answer_text", sa.Text),
        sa.Column("answer_number", sa.Integer),
        sa.Column("answer_decimal", sa.Numeric(20, 4)),
        sa.Column("answer_boolean", sa.Boolean),
        sa.Column("answer_date", sa.Date),
        sa.Column("answer_json", postgresql.JSONB),
        # USER_INPUT|DOCUMENT|API|SYSTEM_DERIVED|ADMIN_VERIFIED
        sa.Column("source", sa.String(30), nullable=False, server_default="USER_INPUT"),
        sa.Column("confidence", sa.Numeric(4, 3)),
        sa.Column("created_at", TS, nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", TS, nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("submission_id", "question_id", name="uq_submission_question"),
    )
    op.create_index("ix_form_answer_submission", "tbl_form_answer", ["submission_id"])
    op.create_index("ix_form_answer_question", "tbl_form_answer", ["question_id"])

    # ==============================================================
    # PART C — PROFILE FACTS
    # ==============================================================

    op.create_table(
        "tbl_profile_fact",
        sa.Column("fact_id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("citizen_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tbl_citizen_master.citizen_id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("fact_code", sa.String(100), nullable=False),
        sa.Column("fact_value", sa.Text),
        # STRING|INTEGER|DECIMAL|BOOLEAN|DATE|JSON
        sa.Column("data_type", sa.String(20), nullable=False),
        # USER_INPUT|DOCUMENT|OCR|GOVERNMENT_API|EXTERNAL_VERIFICATION|
        # ADMIN_VERIFIED|SYSTEM_DERIVED
        sa.Column("source", sa.String(30), nullable=False, server_default="USER_INPUT"),
        sa.Column("confidence", sa.Numeric(4, 3)),
        sa.Column("verified", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("effective_from", sa.Date),
        sa.Column("effective_until", sa.Date),
        sa.Column("created_at", TS, nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", TS, nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "data_type IN ('STRING','INTEGER','DECIMAL','BOOLEAN','DATE','JSON')",
            name="ck_profile_fact_data_type",
        ),
    )
    op.create_index("ix_profile_fact_citizen", "tbl_profile_fact", ["citizen_id"])
    op.create_index("ix_profile_fact_code", "tbl_profile_fact", ["fact_code"])
    # One open fact per (citizen, code). Superseded facts are closed by
    # setting effective_until, which excludes them from this partial index.
    op.create_index(
        "uq_profile_fact_open",
        "tbl_profile_fact",
        ["citizen_id", "fact_code"],
        unique=True,
        postgresql_where=sa.text("effective_until IS NULL"),
    )

    op.create_table(
        "tbl_profile_fact_provenance",
        sa.Column("provenance_id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("fact_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tbl_profile_fact.fact_id", ondelete="CASCADE"),
                  nullable=False),
        # USER_INPUT|DOCUMENT|OCR|GOVERNMENT_API|EXTERNAL_VERIFICATION|
        # ADMIN_VERIFIED|SYSTEM_DERIVED
        sa.Column("source_type", sa.String(30), nullable=False),
        sa.Column("source_reference", sa.String(255)),
        sa.Column("source_text", sa.Text),
        # No FK on purpose: documents live in a future document store.
        sa.Column("document_id", postgresql.UUID(as_uuid=True)),
        # SET NULL: provenance must survive even if the answer is removed.
        sa.Column("form_answer_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tbl_form_answer.answer_id", ondelete="SET NULL")),
        # PENDING|VERIFIED|REJECTED
        sa.Column("verification_status", sa.String(20), server_default="PENDING"),
        sa.Column("verification_date", TS),
        sa.Column("created_at", TS, nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_fact_provenance_fact", "tbl_profile_fact_provenance", ["fact_id"])

    # ==============================================================
    # PART D — DOMAIN PROFILE TABLES
    # ==============================================================

    op.create_table(
        "tbl_education_profile",
        sa.Column("education_id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("citizen_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tbl_citizen_master.citizen_id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("education_level", sa.String(50)),
        sa.Column("institution_name", sa.String(255)),
        sa.Column("institution_type", sa.String(50)),
        sa.Column("course_name", sa.String(255)),
        sa.Column("course_type", sa.String(50)),
        sa.Column("year_of_study", sa.Integer),
        sa.Column("academic_year", sa.String(20)),
        sa.Column("marks_percentage", sa.Numeric(5, 2)),
        sa.Column("annual_fee", sa.Numeric(12, 2)),
        sa.Column("hostel_status", sa.String(20)),
        sa.Column("scholarship_currently_received", sa.Boolean),
        sa.Column("extension_metadata", postgresql.JSONB),
        sa.Column("created_at", TS, nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", TS, nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("citizen_id", name="uq_education_citizen"),
    )
    op.create_index("ix_education_citizen", "tbl_education_profile", ["citizen_id"])

    op.create_table(
        "tbl_employment_profile",
        sa.Column("employment_id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("citizen_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tbl_citizen_master.citizen_id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("employment_status", sa.String(30)),
        sa.Column("occupation", sa.String(100)),
        sa.Column("employment_type", sa.String(30)),
        sa.Column("employer_type", sa.String(30)),
        sa.Column("employer_name", sa.String(255)),
        sa.Column("monthly_income", sa.Numeric(12, 2)),
        sa.Column("annual_income", sa.Numeric(15, 2)),
        sa.Column("work_sector", sa.String(30)),
        sa.Column("self_employed", sa.Boolean),
        sa.Column("extension_metadata", postgresql.JSONB),
        sa.Column("created_at", TS, nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", TS, nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("citizen_id", name="uq_employment_citizen"),
    )
    op.create_index("ix_employment_citizen", "tbl_employment_profile", ["citizen_id"])

    op.create_table(
        "tbl_family_member",
        sa.Column("family_member_id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("citizen_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tbl_citizen_master.citizen_id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("relationship", sa.String(30), nullable=False),
        sa.Column("name", sa.String(255)),
        sa.Column("date_of_birth", sa.Date),
        sa.Column("gender", sa.String(20)),
        sa.Column("education_status", sa.String(50)),
        sa.Column("occupation", sa.String(100)),
        sa.Column("income", sa.Numeric(12, 2)),
        sa.Column("dependent_flag", sa.Boolean, server_default=sa.text("false")),
        sa.Column("disability_status", sa.String(30), server_default="NONE"),
        sa.Column("extension_metadata", postgresql.JSONB),
        sa.Column("created_at", TS, nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", TS, nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_family_member_citizen", "tbl_family_member", ["citizen_id"])

    op.create_table(
        "tbl_agriculture_profile",
        sa.Column("agriculture_id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("citizen_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tbl_citizen_master.citizen_id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("farmer_status", sa.String(30)),
        sa.Column("farmer_type", sa.String(30)),
        sa.Column("land_ownership_status", sa.String(30)),
        sa.Column("total_land_area", sa.Numeric(10, 2)),
        sa.Column("cultivated_land_area", sa.Numeric(10, 2)),
        sa.Column("irrigated_land_area", sa.Numeric(10, 2)),
        sa.Column("land_unit", sa.String(15), server_default="HECTARE"),
        sa.Column("crop_type", sa.String(100)),
        sa.Column("season", sa.String(20)),
        sa.Column("tenant_farmer", sa.Boolean),
        sa.Column("sharecropper", sa.Boolean),
        sa.Column("agricultural_income", sa.Numeric(15, 2)),
        sa.Column("extension_metadata", postgresql.JSONB),
        sa.Column("created_at", TS, nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", TS, nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("citizen_id", name="uq_agriculture_citizen"),
    )
    op.create_index("ix_agriculture_citizen", "tbl_agriculture_profile", ["citizen_id"])

    op.create_table(
        "tbl_disability_profile",
        sa.Column("disability_id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("citizen_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tbl_citizen_master.citizen_id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("disability_status", sa.String(20)),
        sa.Column("disability_type", sa.String(50)),
        sa.Column("disability_percentage", sa.Numeric(5, 2)),
        sa.Column("certificate_available", sa.Boolean),
        # Salted hash only — raw certificate numbers are never stored.
        sa.Column("certificate_number_hash", sa.String(128)),
        sa.Column("extension_metadata", postgresql.JSONB),
        sa.Column("created_at", TS, nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", TS, nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("citizen_id", name="uq_disability_citizen"),
    )
    op.create_index("ix_disability_citizen", "tbl_disability_profile", ["citizen_id"])

    op.create_table(
        "tbl_asset_profile",
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("citizen_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tbl_citizen_master.citizen_id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("asset_type", sa.String(50)),
        sa.Column("ownership_status", sa.String(30)),
        sa.Column("estimated_value", sa.Numeric(15, 2)),
        sa.Column("extension_metadata", postgresql.JSONB),
        sa.Column("created_at", TS, nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", TS, nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_asset_citizen", "tbl_asset_profile", ["citizen_id"])

    # ==============================================================
    # PART E — SCHEME SOURCE FOUNDATION
    # ==============================================================

    op.create_table(
        "tbl_scheme_source",
        sa.Column("source_id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("source_name", sa.String(255), nullable=False),
        sa.Column("source_type", sa.String(50), nullable=False),
        sa.Column("base_url", sa.String(500)),
        sa.Column("authority_name", sa.String(255)),
        sa.Column("status", sa.String(20), server_default="ACTIVE"),
        sa.Column("created_at", TS, nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", TS, nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "source_type IN ('GOVERNMENT_API','GOVERNMENT_WEBSITE','GOVERNMENT_PORTAL',"
            "'GOVERNMENT_PDF','OTHER_AUTHORIZED_SOURCE')",
            name="ck_scheme_source_type",
        ),
        sa.UniqueConstraint("source_name", name="uq_scheme_source_name"),
    )

    op.create_table(
        "tbl_scheme_source_document",
        sa.Column("source_document_id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        # Nullable + SET NULL: documents can be discovered before scheme
        # linkage, and must survive scheme deletion.
        sa.Column("scheme_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tbl_scheme_master.scheme_id", ondelete="SET NULL")),
        sa.Column("source_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tbl_scheme_source.source_id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("document_name", sa.String(255), nullable=False),
        sa.Column("document_url", sa.String(500), nullable=False),
        sa.Column("document_type", sa.String(50)),
        sa.Column("language", sa.String(10), server_default="en"),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("retrieved_at", TS),
        sa.Column("published_at", sa.Date),
        sa.Column("content_hash", sa.String(64)),
        sa.Column("processing_status", sa.String(20), server_default="PENDING"),
        sa.Column("created_at", TS, nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", TS, nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint(
            "source_id", "document_name", "version", name="uq_source_document_version"
        ),
    )
    op.create_index("ix_source_document_scheme", "tbl_scheme_source_document", ["scheme_id"])
    op.create_index("ix_source_document_source", "tbl_scheme_source_document", ["source_id"])

    op.create_table(
        "tbl_scheme_source_content",
        sa.Column("content_id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("source_document_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tbl_scheme_source_document.source_document_id",
                                ondelete="CASCADE"),
                  nullable=False),
        # RAW|NORMALIZED|EXTRACTED_TEXT — original raw content always preserved.
        sa.Column("content_type", sa.String(30), nullable=False),
        sa.Column("raw_content", sa.Text),
        sa.Column("normalized_content", sa.Text),
        sa.Column("language", sa.String(10), server_default="en"),
        sa.Column("processing_status", sa.String(20), server_default="PENDING"),
        sa.Column("extraction_version", sa.String(50)),
        sa.Column("retrieved_at", TS),
        sa.Column("created_at", TS, nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", TS, nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "content_type IN ('RAW','NORMALIZED','EXTRACTED_TEXT')",
            name="ck_scheme_content_type",
        ),
        sa.UniqueConstraint(
            "source_document_id", "content_type", "language",
            name="uq_source_content_variant",
        ),
    )
    op.create_index("ix_source_content_document", "tbl_scheme_source_content",
                    ["source_document_id"])

    op.create_table(
        "tbl_scheme_rule_provenance",
        sa.Column("rule_provenance_id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("rule_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tbl_scheme_eligibility_rule.rule_id", ondelete="CASCADE"),
                  nullable=False),
        # RESTRICT: never silently delete the document a rule was proven from.
        sa.Column("source_document_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tbl_scheme_source_document.source_document_id",
                                ondelete="RESTRICT"),
                  nullable=False),
        sa.Column("source_text", sa.Text),
        sa.Column("source_page", sa.Integer),
        sa.Column("source_section", sa.String(255)),
        sa.Column("source_reference", sa.String(255)),
        sa.Column("extraction_method", sa.String(50)),
        sa.Column("extraction_confidence", sa.Numeric(4, 3)),
        sa.Column("verification_status", sa.String(20), server_default="PENDING"),
        sa.Column("verified_at", TS),
        sa.Column("created_at", TS, nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_rule_provenance_rule", "tbl_scheme_rule_provenance", ["rule_id"])
    op.create_index("ix_rule_provenance_document", "tbl_scheme_rule_provenance",
                    ["source_document_id"])

    # ==============================================================
    # PART F — SCHEME INGESTION RUN
    # ==============================================================

    op.create_table(
        "tbl_scheme_ingestion_run",
        sa.Column("ingestion_run_id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("source_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tbl_scheme_source.source_id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("started_at", TS, nullable=False, server_default=sa.text("now()")),
        sa.Column("completed_at", TS),
        # RUNNING|COMPLETED|FAILED|CANCELLED
        sa.Column("status", sa.String(20), server_default="RUNNING"),
        sa.Column("records_discovered", sa.Integer, server_default="0"),
        sa.Column("records_created", sa.Integer, server_default="0"),
        sa.Column("records_updated", sa.Integer, server_default="0"),
        sa.Column("records_failed", sa.Integer, server_default="0"),
        sa.Column("error_summary", sa.Text),
        sa.Column("created_at", TS, nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_ingestion_run_source", "tbl_scheme_ingestion_run", ["source_id"])

    # ==============================================================
    # PART G — ELIGIBILITY ASSESSMENT (additive columns only)
    # ==============================================================

    op.add_column("tbl_eligibility_assessment",
                  sa.Column("eligibility_status", sa.String(30), nullable=True))
    op.add_column("tbl_eligibility_assessment",
                  sa.Column("missing_facts", postgresql.JSONB, nullable=True))
    op.add_column("tbl_eligibility_assessment",
                  sa.Column("missing_documents", postgresql.JSONB, nullable=True))
    op.add_column("tbl_eligibility_assessment",
                  sa.Column("confidence_score", sa.Numeric(4, 3), nullable=True))
    op.add_column("tbl_eligibility_assessment",
                  sa.Column("assessment_version", sa.String(50), nullable=True))
    op.add_column("tbl_eligibility_assessment",
                  sa.Column("created_at", TS, nullable=True,
                            server_default=sa.text("now()")))
    op.add_column("tbl_eligibility_assessment",
                  sa.Column("updated_at", TS, nullable=True,
                            server_default=sa.text("now()")))
    # NOTE: eligibility_result BOOLEAN is intentionally NOT removed.

    # ==============================================================
    # PART E (cont.) — tbl_scheme_master canonical source fields
    # (additive only; all nullable so the 7 seed schemes stay valid)
    # ==============================================================

    op.add_column("tbl_scheme_master",
                  sa.Column("official_scheme_identifier", sa.String(100), nullable=True))
    op.add_column("tbl_scheme_master",
                  sa.Column("source_type", sa.String(50), nullable=True))
    op.add_column("tbl_scheme_master",
                  sa.Column("source_name", sa.String(255), nullable=True))
    op.add_column("tbl_scheme_master",
                  sa.Column("source_url", sa.String(500), nullable=True))
    op.add_column("tbl_scheme_master",
                  sa.Column("application_window_type", sa.String(30), nullable=True))
    op.add_column("tbl_scheme_master",
                  sa.Column("end_date", sa.Date, nullable=True))
    op.add_column("tbl_scheme_master",
                  sa.Column("scheme_version", sa.Integer, nullable=True,
                            server_default="1"))
    op.add_column("tbl_scheme_master",
                  sa.Column("last_updated_at", TS, nullable=True))
    op.add_column("tbl_scheme_master",
                  sa.Column("last_verified_at_ts", TS, nullable=True))
    # NOTE: official_source_url, application_url and last_verified_at already
    # exist from V1 and are reused — no duplicates were created.


def downgrade() -> None:
    # Reverse order: columns first, then tables in reverse dependency order.

    # --- PART E scheme_master columns ---
    op.drop_column("tbl_scheme_master", "last_verified_at_ts")
    op.drop_column("tbl_scheme_master", "last_updated_at")
    op.drop_column("tbl_scheme_master", "scheme_version")
    op.drop_column("tbl_scheme_master", "end_date")
    op.drop_column("tbl_scheme_master", "application_window_type")
    op.drop_column("tbl_scheme_master", "source_url")
    op.drop_column("tbl_scheme_master", "source_name")
    op.drop_column("tbl_scheme_master", "source_type")
    op.drop_column("tbl_scheme_master", "official_scheme_identifier")

    # --- PART G assessment columns ---
    op.drop_column("tbl_eligibility_assessment", "updated_at")
    op.drop_column("tbl_eligibility_assessment", "created_at")
    op.drop_column("tbl_eligibility_assessment", "assessment_version")
    op.drop_column("tbl_eligibility_assessment", "confidence_score")
    op.drop_column("tbl_eligibility_assessment", "missing_documents")
    op.drop_column("tbl_eligibility_assessment", "missing_facts")
    op.drop_column("tbl_eligibility_assessment", "eligibility_status")

    # --- PART F ---
    op.drop_index("ix_ingestion_run_source", table_name="tbl_scheme_ingestion_run")
    op.drop_table("tbl_scheme_ingestion_run")

    # --- PART E provenance/documents/content/source ---
    op.drop_index("ix_rule_provenance_document", table_name="tbl_scheme_rule_provenance")
    op.drop_index("ix_rule_provenance_rule", table_name="tbl_scheme_rule_provenance")
    op.drop_table("tbl_scheme_rule_provenance")

    op.drop_index("ix_source_content_document", table_name="tbl_scheme_source_content")
    op.drop_table("tbl_scheme_source_content")

    op.drop_index("ix_source_document_source", table_name="tbl_scheme_source_document")
    op.drop_index("ix_source_document_scheme", table_name="tbl_scheme_source_document")
    op.drop_table("tbl_scheme_source_document")

    op.drop_table("tbl_scheme_source")

    # --- PART D ---
    op.drop_index("ix_asset_citizen", table_name="tbl_asset_profile")
    op.drop_table("tbl_asset_profile")

    op.drop_index("ix_disability_citizen", table_name="tbl_disability_profile")
    op.drop_table("tbl_disability_profile")

    op.drop_index("ix_agriculture_citizen", table_name="tbl_agriculture_profile")
    op.drop_table("tbl_agriculture_profile")

    op.drop_index("ix_family_member_citizen", table_name="tbl_family_member")
    op.drop_table("tbl_family_member")

    op.drop_index("ix_employment_citizen", table_name="tbl_employment_profile")
    op.drop_table("tbl_employment_profile")

    op.drop_index("ix_education_citizen", table_name="tbl_education_profile")
    op.drop_table("tbl_education_profile")

    # --- PART C ---
    op.drop_index("ix_fact_provenance_fact", table_name="tbl_profile_fact_provenance")
    op.drop_table("tbl_profile_fact_provenance")

    op.drop_index("uq_profile_fact_open", table_name="tbl_profile_fact")
    op.drop_index("ix_profile_fact_code", table_name="tbl_profile_fact")
    op.drop_index("ix_profile_fact_citizen", table_name="tbl_profile_fact")
    op.drop_table("tbl_profile_fact")

    # --- PART B ---
    op.drop_index("ix_form_answer_question", table_name="tbl_form_answer")
    op.drop_index("ix_form_answer_submission", table_name="tbl_form_answer")
    op.drop_table("tbl_form_answer")

    op.drop_index("ix_form_submission_form", table_name="tbl_form_submission")
    op.drop_index("ix_form_submission_citizen", table_name="tbl_form_submission")
    op.drop_table("tbl_form_submission")

    # --- PART A ---
    op.drop_index("ix_form_condition_depends_on", table_name="tbl_form_condition")
    op.drop_index("ix_form_condition_question", table_name="tbl_form_condition")
    op.drop_table("tbl_form_condition")

    op.drop_index("ix_form_option_question", table_name="tbl_form_question_option")
    op.drop_table("tbl_form_question_option")

    op.drop_index("ix_form_question_code", table_name="tbl_form_question")
    op.drop_index("ix_form_question_section", table_name="tbl_form_question")
    op.drop_table("tbl_form_question")

    op.drop_index("ix_form_section_form", table_name="tbl_form_section")
    op.drop_table("tbl_form_section")

    op.drop_table("tbl_form_definition")
