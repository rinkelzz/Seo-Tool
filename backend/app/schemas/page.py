"""Pydantic schemas for the Page resource."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from backend.app.schemas.issue import IssueRead


class ImageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    src: str
    alt: str | None
    has_alt: bool


class LinkRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    target_url: str
    anchor_text: str | None
    rel: str | None
    is_internal: bool
    is_followed: bool
    target_status_code: int | None


class ResourceRead(BaseModel):
    """One CSS/JS/image resource linked from a page."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    url: str
    resource_type: str  # serialized enum value (stylesheet/script/image)
    is_internal: bool
    is_mixed_content: bool
    status_code: int | None
    probe_error: str | None


class PageRead(BaseModel):
    """Page summary row — used by the page-list endpoint."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    crawl_id: int
    url: str
    status_code: int | None
    response_time_ms: int | None
    content_type: str | None
    html_size: int | None
    title: str | None
    meta_description: str | None
    h1: str | None
    language: str | None
    word_count: int | None
    depth: int | None
    is_indexable: bool | None
    fetch_error: str | None
    created_at: datetime


class PageDetail(PageRead):
    """Page with everything attached: redirect chain, images, links, resources, issues."""

    canonical_url: str | None
    meta_robots: str | None
    redirect_chain: list[str] | None
    images: list[ImageRead]
    links: list[LinkRead]
    resources: list[ResourceRead]
    issues: list[IssueRead]


class PageListResponse(BaseModel):
    items: list[PageRead]
    total: int
    limit: int
    offset: int
