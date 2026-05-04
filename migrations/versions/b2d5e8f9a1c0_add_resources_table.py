"""add resources table

Revision ID: b2d5e8f9a1c0
Revises: 7e9ab2c1d4f5
Create Date: 2026-05-04 10:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b2d5e8f9a1c0"
down_revision: str | None = "7e9ab2c1d4f5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "resources",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("crawl_id", sa.Integer(), nullable=False),
        sa.Column("source_page_id", sa.Integer(), nullable=False),
        sa.Column("url", sa.String(length=2048), nullable=False),
        sa.Column(
            "resource_type",
            sa.Enum("stylesheet", "script", "image", name="resource_type"),
            nullable=False,
        ),
        sa.Column("is_internal", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "is_mixed_content", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("probe_error", sa.String(length=512), nullable=True),
        sa.Column("response_time_ms", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["crawl_id"], ["crawls.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_page_id"], ["pages.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_resources_crawl_url", "resources", ["crawl_id", "url"])
    op.create_index("ix_resources_source_page", "resources", ["source_page_id"])


def downgrade() -> None:
    op.drop_index("ix_resources_source_page", table_name="resources")
    op.drop_index("ix_resources_crawl_url", table_name="resources")
    op.drop_table("resources")
    sa.Enum(name="resource_type").drop(op.get_bind(), checkfirst=False)
