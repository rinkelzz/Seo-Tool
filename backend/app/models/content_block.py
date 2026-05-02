"""ContentBlock-Model: ein Textblock auf einer Seite, für Boilerplate/Duplicate-Erkennung."""

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base, PrimaryKey

if TYPE_CHECKING:
    from backend.app.models.page import Page


class ContentBlock(Base):
    __tablename__ = "content_blocks"
    __table_args__ = (Index("ix_content_blocks_hash", "block_hash"),)

    id: Mapped[PrimaryKey]
    page_id: Mapped[int] = mapped_column(
        ForeignKey("pages.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # SHA-256 oder MinHash-Signatur des normalisierten Textes
    block_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    text_excerpt: Mapped[str] = mapped_column(Text, nullable=False)
    word_count: Mapped[int] = mapped_column(nullable=False)

    page: Mapped["Page"] = relationship(back_populates="content_blocks")
