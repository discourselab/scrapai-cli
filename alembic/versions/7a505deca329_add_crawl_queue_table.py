"""add_crawl_queue_table

Revision ID: 7a505deca329
Revises: 9303ace1c581
Create Date: 2025-12-15 00:19:28.021877

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7a505deca329'
down_revision: Union[str, Sequence[str], None] = '9303ace1c581'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'crawl_queue',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_name', sa.String(length=255), nullable=False, server_default='default'),
        sa.Column('website_url', sa.Text(), nullable=False),
        sa.Column('custom_instruction', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=False, server_default='pending'),
        sa.Column('priority', sa.Integer(), nullable=False, server_default='5'),
        sa.Column('processing_by', sa.String(length=255), nullable=True),
        sa.Column('locked_at', sa.TIMESTAMP(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('retry_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.TIMESTAMP(), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.TIMESTAMP(), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('completed_at', sa.TIMESTAMP(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )

    # Create indexes for performance
    op.create_index('idx_queue_project_status', 'crawl_queue', ['project_name', 'status'])
    op.create_index('idx_queue_priority', 'crawl_queue', ['priority', 'created_at'], postgresql_ops={'priority': 'DESC'})
    op.create_index('idx_queue_locked_at', 'crawl_queue', ['locked_at'], postgresql_where=sa.text("status = 'processing'"))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('idx_queue_locked_at', table_name='crawl_queue')
    op.drop_index('idx_queue_priority', table_name='crawl_queue')
    op.drop_index('idx_queue_project_status', table_name='crawl_queue')
    op.drop_table('crawl_queue')
