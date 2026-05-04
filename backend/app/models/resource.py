"""Resource-Model: eine eingebundene CSS/JS/Image-Ressource einer Page.

Trennen von ``Image`` und ``Link``:
- ``Image`` ist auf Alt-Text-Analyse fokussiert (existiert seit Phase 0).
- ``Link`` modelliert Anchor-Links (``<a href=…>``).
- ``Resource`` deckt ``<link rel="stylesheet">``, ``<script src>`` und
  Bilder ab — alles, was der Browser zusätzlich laden muss, mit dem
  Status-Code aus dem Probe-Pass.

Eine Ressource wird pro Crawl deduplikatfrei gespeichert (gleiche URL
kann auf vielen Pages auftauchen, dann gibt es viele Resource-Rows mit
demselben ``url``-Wert aber unterschiedlichen ``page_id``).
"""

from __future__ import annotations

import enum
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Enum, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base, PrimaryKey

if TYPE_CHECKING:
    from backend.app.models.crawl import Crawl
    from backend.app.models.page import Page


class ResourceType(str, enum.Enum):
    """Welche HTML-Stelle die Ressource referenziert."""

    STYLESHEET = "stylesheet"
    SCRIPT = "script"
    IMAGE = "image"


class Resource(Base):
    __tablename__ = "resources"
    __table_args__ = (
        Index("ix_resources_crawl_url", "crawl_id", "url"),
        Index("ix_resources_source_page", "source_page_id"),
    )

    id: Mapped[PrimaryKey]
    crawl_id: Mapped[int] = mapped_column(
        ForeignKey("crawls.id", ondelete="CASCADE"), nullable=False
    )
    source_page_id: Mapped[int] = mapped_column(
        ForeignKey("pages.id", ondelete="CASCADE"), nullable=False
    )
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    resource_type: Mapped[ResourceType] = mapped_column(
        Enum(ResourceType, name="resource_type"), nullable=False
    )
    is_internal: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # ``True`` if the page is HTTPS but the resource is HTTP (mixed content).
    is_mixed_content: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Status-Code nach dem Probe-Pass; ``None`` wenn die Probe nicht lief
    # oder fehlschlug (Timeout/DNS — siehe ``probe_error``).
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    probe_error: Mapped[str | None] = mapped_column(String(512), nullable=True)
    response_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    crawl: Mapped[Crawl] = relationship()
    page: Mapped[Page] = relationship()
