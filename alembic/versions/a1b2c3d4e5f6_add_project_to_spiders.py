"""add_project_to_spiders

Revision ID: a1b2c3d4e5f6
Revises: 7a505deca329
Create Date: 2026-01-17

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '7a505deca329'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add project column to spiders table."""
    op.add_column('spiders', sa.Column('project', sa.String(length=255), nullable=True, server_default='default'))
    op.create_index('idx_spiders_project', 'spiders', ['project'])


def downgrade() -> None:
    """Remove project column from spiders table."""
    op.drop_index('idx_spiders_project', table_name='spiders')
    op.drop_column('spiders', 'project')
