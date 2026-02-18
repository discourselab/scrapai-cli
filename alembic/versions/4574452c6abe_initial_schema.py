"""initial_schema

Revision ID: 4574452c6abe
Revises: 
Create Date: 2026-02-18 18:20:03.672405

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4574452c6abe'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - Create initial tables."""
    # Import models to ensure all tables are registered
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

    from core.db import Base, engine
    from core import models  # Register all models

    # Create all tables (idempotent - won't fail if tables already exist)
    Base.metadata.create_all(bind=engine)


def downgrade() -> None:
    """Downgrade schema - Drop all tables."""
    # Import models
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

    from core.db import Base, engine
    from core import models

    # Drop all tables
    Base.metadata.drop_all(bind=engine)
