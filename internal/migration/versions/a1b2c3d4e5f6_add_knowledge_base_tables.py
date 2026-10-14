"""add knowledge base tables

Revision ID: a1b2c3d4e5f6
Revises: f3a1c9d2e7b4
Create Date: 2026-10-13 14:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = 'f3a1c9d2e7b4'
branch_labels = None
depends_on = None


def upgrade():
    # dataset
    op.create_table('dataset',
    sa.Column('id', UUID(), nullable=False),
    sa.Column('account_id', UUID(), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('icon', sa.String(length=255), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id', name='pk_dataset_id')
    )
    with op.batch_alter_table('dataset', schema=None) as batch_op:
        batch_op.create_index('idx_dataset_account_id', ['account_id'], unique=False)

    # dataset_query
    op.create_table('dataset_query',
    sa.Column('id', UUID(), nullable=False),
    sa.Column('dataset_id', UUID(), nullable=False),
    sa.Column('query', sa.Text(), nullable=False),
    sa.Column('source', sa.String(length=255), nullable=False),
    sa.Column('source_app_id', UUID(), nullable=True),
    sa.Column('created_by', UUID(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id', name='pk_dataset_query_id')
    )
    with op.batch_alter_table('dataset_query', schema=None) as batch_op:
        batch_op.create_index('idx_dataset_query_dataset_id', ['dataset_id'], unique=False)

    # process_rule
    op.create_table('process_rule',
    sa.Column('id', UUID(), nullable=False),
    sa.Column('account_id', UUID(), nullable=False),
    sa.Column('dataset_id', UUID(), nullable=False),
    sa.Column('mode', sa.String(length=255), nullable=False),
    sa.Column('rule', JSONB(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id', name='pk_process_rule_id')
    )
    with op.batch_alter_table('process_rule', schema=None) as batch_op:
        batch_op.create_index('idx_process_rule_dataset_id', ['dataset_id'], unique=False)

    # segment
    op.create_table('segment',
    sa.Column('id', UUID(), nullable=False),
    sa.Column('account_id', UUID(), nullable=False),
    sa.Column('dataset_id', UUID(), nullable=False),
    sa.Column('document_id', UUID(), nullable=False),
    sa.Column('node_id', sa.String(length=255), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('character_count', sa.Integer(), nullable=False),
    sa.Column('token_count', sa.Integer(), nullable=False),
    sa.Column('keywords', JSONB(), nullable=False),
    sa.Column('hash', sa.String(length=255), nullable=False),
    sa.Column('hit_count', sa.BigInteger(), nullable=False),
    sa.Column('enabled', sa.Boolean(), nullable=False),
    sa.Column('disabled_at', sa.DateTime(), nullable=True),
    sa.Column('processing_started_at', sa.DateTime(), nullable=True),
    sa.Column('indexing_completed_at', sa.DateTime(), nullable=True),
    sa.Column('completed_at', sa.DateTime(), nullable=True),
    sa.Column('stopped_at', sa.DateTime(), nullable=True),
    sa.Column('error', sa.Text(), nullable=False),
    sa.Column('status', sa.String(length=255), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id', name='pk_segment_id')
    )
    with op.batch_alter_table('segment', schema=None) as batch_op:
        batch_op.create_index('idx_segment_dataset_id', ['dataset_id'], unique=False)
        batch_op.create_index('idx_segment_document_id', ['document_id'], unique=False)

    # document
    op.create_table('document',
    sa.Column('id', UUID(), nullable=False),
    sa.Column('account_id', UUID(), nullable=False),
    sa.Column('dataset_id', UUID(), nullable=False),
    sa.Column('upload_file_id', UUID(), nullable=False),
    sa.Column('process_rule_id', UUID(), nullable=False),
    sa.Column('batch', sa.String(length=255), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.Column('character_count', sa.BigInteger(), nullable=False),
    sa.Column('token_count', sa.BigInteger(), nullable=False),
    sa.Column('processing_started_at', sa.DateTime(), nullable=True),
    sa.Column('parsing_completed_at', sa.DateTime(), nullable=True),
    sa.Column('splitting_completed_at', sa.DateTime(), nullable=True),
    sa.Column('indexing_completed_at', sa.DateTime(), nullable=True),
    sa.Column('completed_at', sa.DateTime(), nullable=True),
    sa.Column('stopped_at', sa.DateTime(), nullable=True),
    sa.Column('error', sa.Text(), nullable=False),
    sa.Column('enabled', sa.Boolean(), nullable=False),
    sa.Column('disabled_at', sa.DateTime(), nullable=True),
    sa.Column('status', sa.String(length=255), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id', name='pk_document_id')
    )
    with op.batch_alter_table('document', schema=None) as batch_op:
        batch_op.create_index('idx_document_dataset_id', ['dataset_id'], unique=False)
        batch_op.create_index('idx_document_upload_file_id', ['upload_file_id'], unique=False)

    # keyword_table
    op.create_table('keyword_table',
    sa.Column('id', UUID(), nullable=False),
    sa.Column('dataset_id', UUID(), nullable=False),
    sa.Column('keyword_table', JSONB(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id', name='pk_keyword_table_id')
    )
    with op.batch_alter_table('keyword_table', schema=None) as batch_op:
        batch_op.create_index('idx_keyword_table_dataset_id', ['dataset_id'], unique=False)

    # app_dataset_join
    op.create_table('app_dataset_join',
    sa.Column('id', UUID(), nullable=False),
    sa.Column('app_id', UUID(), nullable=False),
    sa.Column('dataset_id', UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id', name='pk_app_dataset_join_id')
    )
    with op.batch_alter_table('app_dataset_join', schema=None) as batch_op:
        batch_op.create_index('idx_app_dataset_join_app_id', ['app_id'], unique=False)
        batch_op.create_index('idx_app_dataset_join_dataset_id', ['dataset_id'], unique=False)


def downgrade():
    with op.batch_alter_table('app_dataset_join', schema=None) as batch_op:
        batch_op.drop_index('idx_app_dataset_join_dataset_id')
        batch_op.drop_index('idx_app_dataset_join_app_id')
    op.drop_table('app_dataset_join')

    with op.batch_alter_table('keyword_table', schema=None) as batch_op:
        batch_op.drop_index('idx_keyword_table_dataset_id')
    op.drop_table('keyword_table')

    with op.batch_alter_table('document', schema=None) as batch_op:
        batch_op.drop_index('idx_document_upload_file_id')
        batch_op.drop_index('idx_document_dataset_id')
    op.drop_table('document')

    with op.batch_alter_table('segment', schema=None) as batch_op:
        batch_op.drop_index('idx_segment_document_id')
        batch_op.drop_index('idx_segment_dataset_id')
    op.drop_table('segment')

    with op.batch_alter_table('process_rule', schema=None) as batch_op:
        batch_op.drop_index('idx_process_rule_dataset_id')
    op.drop_table('process_rule')

    with op.batch_alter_table('dataset_query', schema=None) as batch_op:
        batch_op.drop_index('idx_dataset_query_dataset_id')
    op.drop_table('dataset_query')

    with op.batch_alter_table('dataset', schema=None) as batch_op:
        batch_op.drop_index('idx_dataset_account_id')
    op.drop_table('dataset')
