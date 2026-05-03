"""add sitemap.urls

Revision ID: 7e9ab2c1d4f5
Revises: 3c4f8a2b9d12
Create Date: 2026-05-04 09:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "7e9ab2c1d4f5"
down_revision: str | None = "3c4f8a2b9d12"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    json_type = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
    op.add_column("sitemaps", sa.Column("urls", json_type, nullable=True))


def downgrade() -> None:
    op.drop_column("sitemaps", "urls")
