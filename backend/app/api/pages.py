"""Pages endpoint: list of crawled pages and per-page detail with issues."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.api.auth import require_token
from backend.app.db.base import get_db
from backend.app.models.crawl import Crawl
from backend.app.models.issue import Issue
from backend.app.models.link import Link
from backend.app.models.page import Page
from backend.app.models.project import Project
from backend.app.schemas.issue import IssueRead
from backend.app.schemas.page import (
    ImageRead,
    LinkRead,
    PageDetail,
    PageListResponse,
    PageRead,
)

router = APIRouter(
    prefix="/api/projects/{project_id}/crawls/{crawl_id}/pages",
    tags=["pages"],
    dependencies=[Depends(require_token)],
)


def _require_crawl(project_id: int, crawl_id: int, db: Session) -> None:
    if db.get(Project, project_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    crawl = db.get(Crawl, crawl_id)
    if crawl is None or crawl.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Crawl not found")


@router.get("", response_model=PageListResponse)
def list_pages(
    project_id: int,
    crawl_id: int,
    has_issues: bool | None = Query(default=None),
    status_code: int | None = Query(default=None, ge=100, le=599),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> PageListResponse:
    _require_crawl(project_id, crawl_id, db)

    base = select(Page).where(Page.crawl_id == crawl_id)
    if status_code is not None:
        base = base.where(Page.status_code == status_code)
    if has_issues is True:
        base = base.where(Page.id.in_(select(Issue.page_id).where(Issue.crawl_id == crawl_id)))
    elif has_issues is False:
        base = base.where(Page.id.notin_(select(Issue.page_id).where(Issue.crawl_id == crawl_id)))

    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    items_stmt = base.order_by(Page.depth.asc(), Page.id.asc()).limit(limit).offset(offset)
    items = list(db.scalars(items_stmt).all())

    return PageListResponse(
        items=[PageRead.model_validate(p) for p in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{page_id}", response_model=PageDetail)
def get_page(
    project_id: int,
    crawl_id: int,
    page_id: int,
    db: Session = Depends(get_db),
) -> PageDetail:
    _require_crawl(project_id, crawl_id, db)
    page = db.get(Page, page_id)
    if page is None or page.crawl_id != crawl_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Page not found")

    # Outgoing links from this page
    links = list(db.scalars(select(Link).where(Link.source_page_id == page_id)).all())
    issues = list(db.scalars(select(Issue).where(Issue.page_id == page_id)).all())

    return PageDetail(
        **PageRead.model_validate(page).model_dump(),
        canonical_url=page.canonical_url,
        meta_robots=page.meta_robots,
        redirect_chain=page.redirect_chain,
        images=[ImageRead.model_validate(i) for i in page.images],
        links=[LinkRead.model_validate(link) for link in links],
        issues=[IssueRead.model_validate(i) for i in issues],
    )
