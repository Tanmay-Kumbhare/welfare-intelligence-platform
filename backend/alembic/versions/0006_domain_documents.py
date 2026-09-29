"""domain documents

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-29 14:50:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '0006'
down_revision = '0005'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('tbl_citizen_document',
    sa.Column('document_id', postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column('citizen_id', postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column('requirement_type', sa.String(length=100), nullable=False),
    sa.Column('original_filename', sa.String(length=255), nullable=False),
    sa.Column('content_type', sa.String(length=100), nullable=False),
    sa.Column('file_size', sa.Integer(), nullable=False),
    sa.Column('detected_type', sa.String(length=100), nullable=True),
    sa.Column('validation_status', sa.String(length=50), nullable=False),
    sa.Column('validation_message', sa.Text(), nullable=True),
    sa.Column('uploaded_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['citizen_id'], ['tbl_citizen_master.citizen_id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('document_id')
    )


def downgrade():
    op.drop_table('tbl_citizen_document')
