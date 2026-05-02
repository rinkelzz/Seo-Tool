"""Backlink-Model: Backlinks aus GSC + Bing WMT (Phase 5)."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base, PrimaryKey

if TYPE_CHECKING:
    from backend.app.models.project import Project


class Backlink(Base):
    __tablename__ = "backlinks"
    __table_args__ = (
        UniqueConstraint(
            "project_id", "source_url", "target_url", name="uq_backlinks_source_target"
        ),
        Index("ix_backlinks_project_status", "project_id", "status"),
    )

    id: Mapped[PrimaryKey]
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    source_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    target_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    anchor: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    # "google_search_console" oder "bing_wmt"
    source_provider: Mapped[str] = mapped_column(String(64), nullable=False)
    # "active" / "lost"
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)

    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    project: Mapped["Project"] = relationship(back_populates="backlinks")
