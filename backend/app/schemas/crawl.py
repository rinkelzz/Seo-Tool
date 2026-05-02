"""Pydantic schemas for the Crawl resource."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from backend.app.models.crawl import CrawlStatus


class CrawlRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    status: CrawlStatus
    started_at: datetime | None
    finished_at: datetime | None
    pages_crawled: int
    error_message: str | None
    score_tech: float | None
    score_struct: float | None
    score_content: float | None
    score_overall: float | None
    created_at: datetime
