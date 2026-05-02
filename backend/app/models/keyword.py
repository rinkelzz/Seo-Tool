"""Keyword-Tracking via Google Search Console (Phase 4)."""

from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import Date, ForeignKey, Index, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base, CreatedAt, PrimaryKey

if TYPE_CHECKING:
    from backend.app.models.project import Project


class Keyword(Base):
    __tablename__ = "keywords"
    __table_args__ = (
        UniqueConstraint("project_id", "keyword", "country", name="uq_keywords_project_keyword"),
    )

    id: Mapped[PrimaryKey]
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    keyword: Mapped[str] = mapped_column(String(512), nullable=False)
    country: Mapped[str] = mapped_column(String(8), default="de", nullable=False)
    device: Mapped[str] = mapped_column(String(16), default="desktop", nullable=False)
    created_at: Mapped[CreatedAt]

    project: Mapped["Project"] = relationship(back_populates="keywords")
    rankings: Mapped[list["KeywordRanking"]] = relationship(
        back_populates="keyword", cascade="all, delete-orphan"
    )


class KeywordRanking(Base):
    __tablename__ = "keyword_rankings"
    __table_args__ = (Index("ix_kw_rankings_keyword_date", "keyword_id", "checked_on"),)

    id: Mapped[PrimaryKey]
    keyword_id: Mapped[int] = mapped_column(
        ForeignKey("keywords.id", ondelete="CASCADE"), nullable=False
    )
    checked_on: Mapped[date] = mapped_column(Date, nullable=False)
    # GSC liefert Durchschnittsposition als Float
    position: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)
    impressions: Mapped[int | None] = mapped_column(Integer, nullable=True)
    clicks: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ctr: Mapped[float | None] = mapped_column(Numeric(6, 4), nullable=True)
    landing_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)

    keyword: Mapped["Keyword"] = relationship(back_populates="rankings")
