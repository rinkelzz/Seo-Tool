"""Image-Model: ein Bild auf einer Seite."""

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base, PrimaryKey

if TYPE_CHECKING:
    from backend.app.models.page import Page


class Image(Base):
    __tablename__ = "images"

    id: Mapped[PrimaryKey]
    page_id: Mapped[int] = mapped_column(
        ForeignKey("pages.id", ondelete="CASCADE"), nullable=False, index=True
    )
    src: Mapped[str] = mapped_column(String(2048), nullable=False)
    alt: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    has_alt: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)

    page: Mapped["Page"] = relationship(back_populates="images")
