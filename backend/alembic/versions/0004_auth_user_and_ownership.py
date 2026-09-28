"""
Auth tables: user account, role membership, and a link from citizen -> owning user.

This is the foundation for replacing the "localStorage citizen_id" model with
server-verified authentication. A user is the authentication identity; a citizen
is the welfare profile. For now they are linked 1:1 via owning_user_id.
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_auth_user_and_ownership"
down_revision: str | None = "0003"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # User account
    # ------------------------------------------------------------------
    op.create_table(
        "tbl_user_account",
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column(
            "provider",
            sa.String(30),
            nullable=False,
            server_default=sa.text("'EMAIL_PASSWORD'"),
        ),
        sa.Column(
            "email_verified",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("email", name="uq_user_account_email"),
    )

    op.create_index("ix_user_account_email", "tbl_user_account", ["email"], unique=True)

    # ------------------------------------------------------------------
    # User role membership
    # ------------------------------------------------------------------
    op.create_table(
        "tbl_user_role",
        sa.Column(
            "user_role_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "tbl_user_account.user_id", ondelete="CASCADE"
            ),
            nullable=False,
        ),
        sa.Column("role", sa.String(30), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("user_id", "role", name="uq_user_role_membership"),
    )

    op.create_index("ix_user_role_user", "tbl_user_role", ["user_id"])

    # ------------------------------------------------------------------
    # Ownership link on citizen master
    # ------------------------------------------------------------------
    op.add_column(
        "tbl_citizen_master",
        sa.Column(
            "owning_user_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_citizen_owning_user", "tbl_citizen_master", ["owning_user_id"]
    )

    # ------------------------------------------------------------------
    # Token/session store for the current token-based session approach
    # ------------------------------------------------------------------
    op.create_table(
        "tbl_user_session",
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "tbl_user_account.user_id", ondelete="CASCADE"
            ),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(255), nullable=False),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "last_used_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.create_index("ix_user_session_user", "tbl_user_session", ["user_id"])
    op.create_index("ix_user_session_token", "tbl_user_session", ["token_hash"])


def downgrade() -> None:
    op.drop_index("ix_user_session_token", table_name="tbl_user_session")
    op.drop_index("ix_user_session_user", table_name="tbl_user_session")
    op.drop_table("tbl_user_session")

    op.drop_index("ix_citizen_owning_user", table_name="tbl_citizen_master")
    op.drop_column("tbl_citizen_master", "owning_user_id")

    op.drop_index("ix_user_role_user", table_name="tbl_user_role")
    op.drop_table("tbl_user_role")

    op.drop_index("uq_user_account_email", table_name="tbl_user_account")
    op.drop_table("tbl_user_account")
