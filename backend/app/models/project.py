"""Project-Model: ein zu analysierendes Web-Projekt."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base, CreatedAt, PrimaryKey, UpdatedAt

if TYPE_CHECKING:
    from backend.app.models.backlink import Backlink
    from backend.app.models.crawl import Crawl
    from backend.app.models.keyword import Keyword
    from backend.app.models.sitemap import Sitemap


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (UniqueConstraint("domain", name="uq_projects_domain"),)

    id: Mapped[PrimaryKey]
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    domain: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    base_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    robots_respect: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    js_render: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Periodic crawls (Phase 8-B). When schedule_interval_minutes is None
    # the project has no auto-crawls and next_scheduled_at stays null. When
    # set, the scheduler tick enqueues a crawl every time
    # next_scheduled_at <= now and advances it by the interval afterwards.
    schedule_interval_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    next_scheduled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

    created_at: Mapped[CreatedAt]
    updated_at: Mapped[UpdatedAt]

    crawls: Mapped[list["Crawl"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    keywords: Mapped[list["Keyword"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    backlinks: Mapped[list["Backlink"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    sitemaps: Mapped[list["Sitemap"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
