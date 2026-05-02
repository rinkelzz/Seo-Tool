"""Sitemap-Model: gefundene Sitemaps eines Projekts."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base, PrimaryKey

if TYPE_CHECKING:
    from backend.app.models.project import Project


class Sitemap(Base):
    __tablename__ = "sitemaps"

    id: Mapped[PrimaryKey]
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    last_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    urls_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    fetch_error: Mapped[str | None] = mapped_column(String(512), nullable=True)

    project: Mapped["Project"] = relationship(back_populates="sitemaps")
