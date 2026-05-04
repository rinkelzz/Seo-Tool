"""add project schedule fields

Revision ID: f5c1a8d3b2e0
Revises: d3a8b6f2e9c1
Create Date: 2026-05-04 18:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f5c1a8d3b2e0"
down_revision: str | None = "d3a8b6f2e9c1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("schedule_interval_minutes", sa.Integer(), nullable=True))
    op.add_column(
        "projects",
        sa.Column("next_scheduled_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_projects_next_scheduled_at",
        "projects",
        ["next_scheduled_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_projects_next_scheduled_at", table_name="projects")
    op.drop_column("projects", "next_scheduled_at")
    op.drop_column("projects", "schedule_interval_minutes")
