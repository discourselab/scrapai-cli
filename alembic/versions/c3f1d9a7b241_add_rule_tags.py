"""add_rule_tags

Revision ID: c3f1d9a7b241
Revises: 1beddbb53e84
Create Date: 2026-04-20 17:50:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c3f1d9a7b241'
down_revision: Union[str, Sequence[str], None] = '1beddbb53e84'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add tags JSON column to spider_rules.

    Lets rule JSON declare which HTML tags LinkExtractor inspects
    (default remains ('a', 'area') when null). Needed for sites whose
    pagination lives in <link rel="next"> rather than anchor tags.
    """
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [col['name'] for col in inspector.get_columns('spider_rules')]

    if 'tags' not in columns:
        op.add_column('spider_rules', sa.Column('tags', sa.JSON(), nullable=True))


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [col['name'] for col in inspector.get_columns('spider_rules')]

    if 'tags' in columns:
        op.drop_column('spider_rules', 'tags')
