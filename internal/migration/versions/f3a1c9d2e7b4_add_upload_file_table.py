"""add upload_file table

Revision ID: f3a1c9d2e7b4
Revises: d9bc8b8909ca
Create Date: 2026-10-13 10:20:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'f3a1c9d2e7b4'
down_revision = 'd9bc8b8909ca'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('upload_file',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('account_id', sa.UUID(), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('key', sa.String(length=255), nullable=False),
    sa.Column('size', sa.BigInteger(), nullable=False),
    sa.Column('extension', sa.String(length=255), nullable=False),
    sa.Column('mime_type', sa.String(length=255), nullable=False),
    sa.Column('hash', sa.String(length=255), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id', name='pk_upload_file_id')
    )
    with op.batch_alter_table('upload_file', schema=None) as batch_op:
        batch_op.create_index('idx_upload_file_account_id', ['account_id'], unique=False)


def downgrade():
    with op.batch_alter_table('upload_file', schema=None) as batch_op:
        batch_op.drop_index('idx_upload_file_account_id')

    op.drop_table('upload_file')
