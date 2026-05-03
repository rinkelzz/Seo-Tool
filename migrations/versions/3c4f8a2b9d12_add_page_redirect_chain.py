"""add page.redirect_chain

Revision ID: 3c4f8a2b9d12
Revises: 018a435b9e03
Create Date: 2026-05-03 11:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "3c4f8a2b9d12"
down_revision: str | None = "018a435b9e03"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    json_type = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
    op.add_column("pages", sa.Column("redirect_chain", json_type, nullable=True))


def downgrade() -> None:
    op.drop_column("pages", "redirect_chain")
