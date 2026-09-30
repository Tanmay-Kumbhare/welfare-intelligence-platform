"""
OAuth providers and account linking: nullable password_hash, google_id, digilocker_id, full_name.

Additive migration enabling Google OAuth and DigiLocker authentication alongside
existing email/password accounts, unified under tbl_user_account.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0005_oauth_and_linking"
down_revision: str | None = "0004_auth_user_and_ownership"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    # 1. Allow password_hash to be nullable for OAuth-only users
    op.alter_column(
        "tbl_user_account",
        "password_hash",
        existing_type=sa.String(255),
        nullable=True,
    )

    # 2. Add google_id with unique index
    op.add_column(
        "tbl_user_account",
        sa.Column("google_id", sa.String(255), nullable=True),
    )
    op.create_index(
        "ix_user_account_google_id",
        "tbl_user_account",
        ["google_id"],
        unique=True,
    )

    # 3. Add digilocker_id with unique index
    op.add_column(
        "tbl_user_account",
        sa.Column("digilocker_id", sa.String(255), nullable=True),
    )
    op.create_index(
        "ix_user_account_digilocker_id",
        "tbl_user_account",
        ["digilocker_id"],
        unique=True,
    )

    # 4. Add full_name on UserAccount
    op.add_column(
        "tbl_user_account",
        sa.Column("full_name", sa.String(255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("tbl_user_account", "full_name")

    op.drop_index("ix_user_account_digilocker_id", table_name="tbl_user_account")
    op.drop_column("tbl_user_account", "digilocker_id")

    op.drop_index("ix_user_account_google_id", table_name="tbl_user_account")
    op.drop_column("tbl_user_account", "google_id")

    op.alter_column(
        "tbl_user_account",
        "password_hash",
        existing_type=sa.String(255),
        nullable=False,
    )
