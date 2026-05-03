"""Shared SQLAlchemy column type variants used across multiple models."""

from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import JSONB

# JSONB on Postgres (efficient indexing/querying), plain JSON on SQLite (used in tests).
# Same Python API in both cases.
JsonType = JSON().with_variant(JSONB(), "postgresql")
