"""Page-Model: eine einzelne gecrawlte Seite."""

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base, CreatedAt, PrimaryKey
from backend.app.db.types import JsonType

if TYPE_CHECKING:
    from backend.app.models.content_block import ContentBlock
    from backend.app.models.crawl import Crawl
    from backend.app.models.image import Image
    from backend.app.models.issue import Issue


class Page(Base):
    __tablename__ = "pages"
    __table_args__ = (
        Index("ix_pages_crawl_url", "crawl_id", "url"),
        Index("ix_pages_content_hash", "content_hash"),
    )

    id: Mapped[PrimaryKey]
    crawl_id: Mapped[int] = mapped_column(
        ForeignKey("crawls.id", ondelete="CASCADE"), nullable=False
    )
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    html_size: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # SEO-Felder
    title: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    meta_description: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    meta_robots: Mapped[str | None] = mapped_column(String(255), nullable=True)
    canonical_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    h1: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    language: Mapped[str | None] = mapped_column(String(16), nullable=True)
    word_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Strukturmetrik
    depth: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_indexable: Mapped[bool | None] = mapped_column(nullable=True)

    # Redirect-Kette: Liste der Hop-URLs vor der finalen URL (leer = keine Weiterleitung)
    redirect_chain: Mapped[list[str] | None] = mapped_column(JsonType, nullable=True)

    # Fehler-Marker (falls Page nicht abrufbar)
    fetch_error: Mapped[str | None] = mapped_column(String(512), nullable=True)

    created_at: Mapped[CreatedAt]

    crawl: Mapped["Crawl"] = relationship(back_populates="pages")
    images: Mapped[list["Image"]] = relationship(
        back_populates="page", cascade="all, delete-orphan"
    )
    issues: Mapped[list["Issue"]] = relationship(
        back_populates="page", cascade="all, delete-orphan"
    )
    content_blocks: Mapped[list["ContentBlock"]] = relationship(
        back_populates="page", cascade="all, delete-orphan"
    )
