"""scope_unique_constraints_to_project_and_spider

Revision ID: 1beddbb53e84
Revises: a7b3f9e12345
Create Date: 2026-04-19 21:40:20.645759

Replaces global UNIQUE on spiders.name and scraped_items.url with
project- and spider-scoped compound UNIQUE constraints so that:
- the same spider name can exist in different projects
- the same URL can be scraped by different spiders / projects
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "1beddbb53e84"
down_revision: Union[str, Sequence[str], None] = "a7b3f9e12345"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _index_exists(table: str, name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(ix["name"] == name for ix in inspector.get_indexes(table))


def _constraint_exists(table: str, name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(uc["name"] == name for uc in inspector.get_unique_constraints(table))


def upgrade() -> None:
    with op.batch_alter_table("spiders") as batch_op:
        if _index_exists("spiders", "ix_spiders_name"):
            batch_op.drop_index("ix_spiders_name")
        batch_op.create_index("ix_spiders_name", ["name"], unique=False)
        if not _constraint_exists("spiders", "uq_spider_name_project"):
            batch_op.create_unique_constraint(
                "uq_spider_name_project", ["name", "project"]
            )

    with op.batch_alter_table("scraped_items") as batch_op:
        if _index_exists("scraped_items", "ix_scraped_items_url"):
            batch_op.drop_index("ix_scraped_items_url")
        batch_op.create_index("ix_scraped_items_url", ["url"], unique=False)
        if not _constraint_exists("scraped_items", "uq_item_spider_url"):
            batch_op.create_unique_constraint(
                "uq_item_spider_url", ["spider_id", "url"]
            )


def downgrade() -> None:
    with op.batch_alter_table("scraped_items") as batch_op:
        if _constraint_exists("scraped_items", "uq_item_spider_url"):
            batch_op.drop_constraint("uq_item_spider_url", type_="unique")
        if _index_exists("scraped_items", "ix_scraped_items_url"):
            batch_op.drop_index("ix_scraped_items_url")
        batch_op.create_index("ix_scraped_items_url", ["url"], unique=True)

    with op.batch_alter_table("spiders") as batch_op:
        if _constraint_exists("spiders", "uq_spider_name_project"):
            batch_op.drop_constraint("uq_spider_name_project", type_="unique")
        if _index_exists("spiders", "ix_spiders_name"):
            batch_op.drop_index("ix_spiders_name")
        batch_op.create_index("ix_spiders_name", ["name"], unique=True)
