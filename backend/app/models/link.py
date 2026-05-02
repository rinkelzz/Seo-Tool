"""Link-Model: eine Verlinkung von einer Seite zu einer URL (intern oder extern)."""

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base, PrimaryKey

if TYPE_CHECKING:
    from backend.app.models.crawl import Crawl


class Link(Base):
    __tablename__ = "links"
    __table_args__ = (
        Index("ix_links_crawl_internal", "crawl_id", "is_internal"),
        Index("ix_links_target_url", "target_url"),
    )

    id: Mapped[PrimaryKey]
    crawl_id: Mapped[int] = mapped_column(
        ForeignKey("crawls.id", ondelete="CASCADE"), nullable=False
    )
    source_page_id: Mapped[int] = mapped_column(
        ForeignKey("pages.id", ondelete="CASCADE"), nullable=False, index=True
    )
    target_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    anchor_text: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    rel: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_internal: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_followed: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    target_status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)

    crawl: Mapped["Crawl"] = relationship(back_populates="links")
