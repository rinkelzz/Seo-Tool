"""Schemas for the projects dashboard endpoint.

The dashboard view bundles each project with its latest two ``completed``
crawls so the UI can render a score + delta-vs-previous indicator without
N+1 follow-up requests.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from backend.app.models.crawl import CrawlStatus
from backend.app.schemas.project import ProjectRead


class DashboardCrawl(BaseModel):
    """Slim crawl summary — just what the dashboard cards need."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    status: CrawlStatus
    started_at: datetime | None
    finished_at: datetime | None
    score_overall: float | None
    score_tech: float | None
    score_struct: float | None
    score_content: float | None


class DashboardProject(BaseModel):
    """One row of the dashboard: project + latest + previous crawl."""

    project: ProjectRead
    latest_crawl: DashboardCrawl | None
    previous_crawl: DashboardCrawl | None
