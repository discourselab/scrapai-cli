"""add_callbacks_config

Revision ID: a7b3f9e12345
Revises: 4574452c6abe
Create Date: 2026-02-24 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a7b3f9e12345'
down_revision: Union[str, Sequence[str], None] = '4574452c6abe'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add callbacks_config column to spiders table."""
    op.add_column('spiders', sa.Column('callbacks_config', sa.JSON(), nullable=True))


def downgrade() -> None:
    """Remove callbacks_config column from spiders table."""
    op.drop_column('spiders', 'callbacks_config')
