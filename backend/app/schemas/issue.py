"""Pydantic schemas for the Issue resource and aggregations."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from backend.app.models.issue import IssueCategory, IssueSeverity


class IssueRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    crawl_id: int
    page_id: int | None
    rule_id: str
    category: IssueCategory
    severity: IssueSeverity
    payload: dict[str, Any] | None
    created_at: datetime


class IssueCount(BaseModel):
    """Aggregate row used by the crawl-summary endpoint."""

    rule_id: str
    category: IssueCategory
    severity: IssueSeverity
    count: int


class CrawlSummary(BaseModel):
    """Counts grouped by category and severity, plus a per-rule breakdown."""

    by_category: dict[IssueCategory, int]
    by_severity: dict[IssueSeverity, int]
    by_rule: list[IssueCount]
    total: int


class IssueListResponse(BaseModel):
    """Paginated wrapper around ``IssueRead``."""

    items: list[IssueRead]
    total: int
    limit: int
    offset: int
