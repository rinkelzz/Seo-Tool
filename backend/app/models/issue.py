"""Issue model: a finding from an analyzer (missing title, duplicate content, etc.)."""

import enum
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, Enum, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base, CreatedAt, PrimaryKey

# JSONB on Postgres, JSON on SQLite (for tests). Same Python API.
JsonType = JSON().with_variant(JSONB(), "postgresql")

if TYPE_CHECKING:
    from backend.app.models.crawl import Crawl
    from backend.app.models.page import Page


class IssueSeverity(str, enum.Enum):
    """Mirrors Seobility severities."""

    CRITICAL = "critical"
    IMPORTANT = "important"
    TIP = "tip"


class IssueCategory(str, enum.Enum):
    """Three top-level categories like the Seobility report."""

    TECH_META = "tech_meta"
    STRUCTURE = "structure"
    CONTENT = "content"


class Issue(Base):
    __tablename__ = "issues"
    __table_args__ = (
        Index("ix_issues_crawl_rule", "crawl_id", "rule_id"),
        Index("ix_issues_crawl_severity", "crawl_id", "severity"),
    )

    id: Mapped[PrimaryKey]
    crawl_id: Mapped[int] = mapped_column(
        ForeignKey("crawls.id", ondelete="CASCADE"), nullable=False
    )
    page_id: Mapped[int | None] = mapped_column(
        ForeignKey("pages.id", ondelete="CASCADE"), nullable=True, index=True
    )
    rule_id: Mapped[str] = mapped_column(String(128), nullable=False)
    category: Mapped[IssueCategory] = mapped_column(
        Enum(IssueCategory, name="issue_category"), nullable=False
    )
    severity: Mapped[IssueSeverity] = mapped_column(
        Enum(IssueSeverity, name="issue_severity"), nullable=False
    )
    payload: Mapped[dict[str, Any] | None] = mapped_column(JsonType, nullable=True)

    created_at: Mapped[CreatedAt]

    crawl: Mapped["Crawl"] = relationship(back_populates="issues")
    page: Mapped["Page | None"] = relationship(back_populates="issues")
