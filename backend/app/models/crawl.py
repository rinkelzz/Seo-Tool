"""Crawl model: a single crawl run for a project."""

import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, Numeric
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base, CreatedAt, PrimaryKey

if TYPE_CHECKING:
    from backend.app.models.issue import Issue
    from backend.app.models.link import Link
    from backend.app.models.page import Page
    from backend.app.models.project import Project


class CrawlStatus(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Crawl(Base):
    __tablename__ = "crawls"

    id: Mapped[PrimaryKey]
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[CrawlStatus] = mapped_column(
        Enum(CrawlStatus, name="crawl_status"), default=CrawlStatus.QUEUED, nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    pages_crawled: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(nullable=True)

    score_tech: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    score_struct: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    score_content: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    score_overall: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)

    created_at: Mapped[CreatedAt]

    project: Mapped["Project"] = relationship(back_populates="crawls")
    pages: Mapped[list["Page"]] = relationship(back_populates="crawl", cascade="all, delete-orphan")
    links: Mapped[list["Link"]] = relationship(back_populates="crawl", cascade="all, delete-orphan")
    issues: Mapped[list["Issue"]] = relationship(
        back_populates="crawl", cascade="all, delete-orphan"
    )
