"""uppercase resource_type enum values

Aligns the ``resource_type`` Postgres enum with SQLAlchemy's default
serialization (which uses Python enum *names*, i.e. UPPERCASE). Other
enum types in the schema (``crawl_status``, ``issue_category``,
``issue_severity``) were already created with uppercase values in the
initial migration; only ``resource_type`` from b2d5e8f9a1c0 used
lowercase, which made every Resource INSERT fail with
``invalid input value for enum resource_type: "STYLESHEET"``.

The fix uses ``ALTER TYPE … RENAME VALUE`` (Postgres ≥ 10), which
also rewrites every existing row that used the old value — so even
DBs that somehow got a row in are migrated cleanly. SQLite has no
native enum type and stores these as VARCHAR, so the migration is a
no-op there.

Revision ID: d3a8b6f2e9c1
Revises: b2d5e8f9a1c0
Create Date: 2026-05-04 12:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d3a8b6f2e9c1"
down_revision: str | None = "b2d5e8f9a1c0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_RENAMES = [
    ("stylesheet", "STYLESHEET"),
    ("script", "SCRIPT"),
    ("image", "IMAGE"),
]


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        # SQLite stores enums as VARCHAR — no rename needed.
        return
    for old, new in _RENAMES:
        op.execute(f"ALTER TYPE resource_type RENAME VALUE '{old}' TO '{new}'")


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    for old, new in _RENAMES:
        op.execute(f"ALTER TYPE resource_type RENAME VALUE '{new}' TO '{old}'")
