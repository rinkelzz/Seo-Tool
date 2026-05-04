"""Pydantic schemas for the Sitemap resource."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class SitemapRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    url: str
    last_fetched_at: datetime | None
    urls_count: int
    fetch_error: str | None
