"""add_source_url_to_spiders

Revision ID: d3b4f3f9e3a0
Revises: a1b2c3d4e5f6
Create Date: 2026-02-14 21:29:45.868146

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd3b4f3f9e3a0'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('spiders', sa.Column('source_url', sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('spiders', 'source_url')
