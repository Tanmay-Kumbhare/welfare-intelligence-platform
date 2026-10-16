"""
Phase 3B source/resource foundation: tbl_scheme_source_resource, tbl_scheme_ingestion_item,
and additive fetch-evidence columns.

Additive, backward-compatible migration implementing the frozen design in
SOURCE_RESOURCE_SCHEMA_DESIGN.md (Task 1D design + Task 1E freeze validation):

  - NEW tbl_scheme_source_resource  — stable logical resource identity per source
  - NEW tbl_scheme_ingestion_item   — per-resource attempt tracking within a run
  - tbl_scheme_source + 4 nullable columns (canonical_base_url, precedence_rank,
    fetch_policy, org_type)
  - tbl_scheme_source_document + resource_id FK + 5 nullable fetch-evidence columns

No existing column is modified, no data is backfilled, all new columns are nullable
so existing rows keep working unchanged. Fully reversible.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011_source_resource_foundation"
down_revision: str | None = "0010_citizen_timestamps"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None

TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    # ==============================================================
    # 1. NEW TABLE — tbl_scheme_source_resource
    #    Stable logical identity of a discoverable endpoint/document
    #    belonging to a source. Snapshots (documents) reference it.
    # ==============================================================
    op.create_table(
        "tbl_scheme_source_resource",
        sa.Column(
            "resource_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "source_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "tbl_scheme_source.source_id",
                ondelete="CASCADE",
                name="fk_source_resource_source",
            ),
            nullable=False,
        ),
        sa.Column("resource_name", sa.String(500), nullable=False),
        sa.Column("resource_url", sa.String(1000), nullable=False),
        # CATALOGUE_PAGE|SCHEME_PAGE|PDF|APPLICATION_PORTAL|API_ENDPOINT|DOCUMENT_ARCHIVE|OTHER
        sa.Column("resource_type", sa.String(50), nullable=False),
        sa.Column("language", sa.String(20), server_default="en"),
        # ACTIVE|INACTIVE|RETIRED
        sa.Column("status", sa.String(20), server_default="ACTIVE"),
        sa.Column("fetch_method", sa.String(50), server_default="HTTP_GET"),
        sa.Column("is_application_portal", sa.Boolean, server_default=sa.text("false")),
        sa.Column("discovered_at", TS),
        sa.Column("last_checked_at", TS),
        sa.Column("notes", sa.Text),
        sa.Column("created_at", TS, nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", TS, nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "resource_type IN ('CATALOGUE_PAGE','SCHEME_PAGE','PDF',"
            "'APPLICATION_PORTAL','API_ENDPOINT','DOCUMENT_ARCHIVE','OTHER')",
            name="ck_source_resource_type",
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE','INACTIVE','RETIRED')",
            name="ck_source_resource_status",
        ),
        # Resource identity: one logical URL per source. URL normalization
        # (lowercasing host, trailing-slash collapse, session-token stripping)
        # is applied by convention in the CRUD layer per the frozen design.
        sa.UniqueConstraint("source_id", "resource_url", name="uq_source_resource_url"),
    )
    op.create_index(
        "ix_source_resource_source", "tbl_scheme_source_resource", ["source_id"]
    )
    op.create_index(
        "ix_source_resource_status", "tbl_scheme_source_resource", ["status"]
    )

    # ==============================================================
    # 2. NEW TABLE — tbl_scheme_ingestion_item
    #    Per-resource attempt tracking within one ingestion run.
    # ==============================================================
    op.create_table(
        "tbl_scheme_ingestion_item",
        sa.Column(
            "item_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "ingestion_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "tbl_scheme_ingestion_run.ingestion_run_id",
                ondelete="CASCADE",
                name="fk_ingestion_item_run",
            ),
            nullable=False,
        ),
        # SET NULL: losing the link must never destroy run/snapshot history.
        sa.Column(
            "resource_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "tbl_scheme_source_resource.resource_id",
                ondelete="SET NULL",
                name="fk_ingestion_item_resource",
            ),
        ),
        sa.Column(
            "source_document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "tbl_scheme_source_document.source_document_id",
                ondelete="SET NULL",
                name="fk_ingestion_item_document",
            ),
        ),
        # PENDING|RUNNING|SUCCEEDED|FAILED|SKIPPED
        sa.Column("status", sa.String(20), server_default="PENDING"),
        sa.Column("http_status", sa.Integer),
        sa.Column("error_detail", sa.Text),
        sa.Column("started_at", TS),
        sa.Column("completed_at", TS),
        sa.Column("created_at", TS, nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "status IN ('PENDING','RUNNING','SUCCEEDED','FAILED','SKIPPED')",
            name="ck_ingestion_item_status",
        ),
    )
    op.create_index(
        "ix_ingestion_item_run", "tbl_scheme_ingestion_item", ["ingestion_run_id"]
    )

    # ==============================================================
    # 3. tbl_scheme_source — 4 nullable registry columns (no backfill)
    # ==============================================================
    op.add_column(
        "tbl_scheme_source",
        sa.Column("canonical_base_url", sa.String(500), nullable=True),
    )
    op.add_column(
        "tbl_scheme_source",
        sa.Column("precedence_rank", sa.Integer, nullable=True),
    )
    op.add_column(
        "tbl_scheme_source",
        sa.Column("fetch_policy", sa.String(50), nullable=True),
    )
    op.add_column(
        "tbl_scheme_source",
        sa.Column("org_type", sa.String(50), nullable=True),
    )
    # DEPARTMENT|COMMISSIONERATE|DIRECTORATE|BOARD|CORPORATION|MISSION|COMMISSION|PLATFORM
    op.create_check_constraint(
        "ck_scheme_source_org_type",
        "tbl_scheme_source",
        "org_type IS NULL OR org_type IN "
        "('DEPARTMENT','COMMISSIONERATE','DIRECTORATE','BOARD',"
        "'CORPORATION','MISSION','COMMISSION','PLATFORM')",
    )

    # ==============================================================
    # 4. tbl_scheme_source_document — resource link + fetch evidence
    #    (all nullable; existing rows keep resource_id = NULL)
    # ==============================================================
    op.add_column(
        "tbl_scheme_source_document",
        sa.Column(
            "resource_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "tbl_scheme_source_resource.resource_id",
                ondelete="SET NULL",
                name="fk_source_document_resource",
            ),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_source_document_resource", "tbl_scheme_source_document", ["resource_id"]
    )
    op.add_column(
        "tbl_scheme_source_document",
        sa.Column("http_status", sa.Integer, nullable=True),
    )
    op.add_column(
        "tbl_scheme_source_document",
        sa.Column("final_url", sa.String(1000), nullable=True),
    )
    op.add_column(
        "tbl_scheme_source_document",
        sa.Column("content_type", sa.String(200), nullable=True),
    )
    op.add_column(
        "tbl_scheme_source_document",
        sa.Column("content_length", sa.BigInteger, nullable=True),
    )
    op.add_column(
        "tbl_scheme_source_document",
        sa.Column("error_detail", sa.Text, nullable=True),
    )


def downgrade() -> None:
    # Reverse order: FKs/indexes first, then columns, then tables.
    op.drop_index(
        "ix_source_document_resource", table_name="tbl_scheme_source_document"
    )
    op.drop_column("tbl_scheme_source_document", "error_detail")
    op.drop_column("tbl_scheme_source_document", "content_length")
    op.drop_column("tbl_scheme_source_document", "content_type")
    op.drop_column("tbl_scheme_source_document", "final_url")
    op.drop_column("tbl_scheme_source_document", "http_status")
    op.drop_column("tbl_scheme_source_document", "resource_id")

    op.drop_constraint(
        "ck_scheme_source_org_type", "tbl_scheme_source", type_="check"
    )
    op.drop_column("tbl_scheme_source", "org_type")
    op.drop_column("tbl_scheme_source", "fetch_policy")
    op.drop_column("tbl_scheme_source", "precedence_rank")
    op.drop_column("tbl_scheme_source", "canonical_base_url")

    op.drop_index("ix_ingestion_item_run", table_name="tbl_scheme_ingestion_item")
    op.drop_table("tbl_scheme_ingestion_item")

    op.drop_index("ix_source_resource_status", table_name="tbl_scheme_source_resource")
    op.drop_index("ix_source_resource_source", table_name="tbl_scheme_source_resource")
    op.drop_table("tbl_scheme_source_resource")
