"""Issues endpoint: paginated, filterable list of findings for a crawl."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.api.auth import require_token
from backend.app.db.base import get_db
from backend.app.models.crawl import Crawl
from backend.app.models.issue import Issue, IssueCategory, IssueSeverity
from backend.app.models.project import Project
from backend.app.schemas.issue import IssueListResponse, IssueRead

router = APIRouter(
    prefix="/api/projects/{project_id}/crawls/{crawl_id}/issues",
    tags=["issues"],
    dependencies=[Depends(require_token)],
)


def _require_crawl(project_id: int, crawl_id: int, db: Session) -> None:
    if db.get(Project, project_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    crawl = db.get(Crawl, crawl_id)
    if crawl is None or crawl.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Crawl not found")


@router.get("", response_model=IssueListResponse)
def list_issues(
    project_id: int,
    crawl_id: int,
    severity: IssueSeverity | None = Query(default=None),
    category: IssueCategory | None = Query(default=None),
    rule_id: str | None = Query(default=None, max_length=128),
    page_id: int | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> IssueListResponse:
    _require_crawl(project_id, crawl_id, db)

    base = select(Issue).where(Issue.crawl_id == crawl_id)
    if severity is not None:
        base = base.where(Issue.severity == severity)
    if category is not None:
        base = base.where(Issue.category == category)
    if rule_id is not None:
        base = base.where(Issue.rule_id == rule_id)
    if page_id is not None:
        base = base.where(Issue.page_id == page_id)

    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0

    items_stmt = base.order_by(Issue.severity.desc(), Issue.id.asc()).limit(limit).offset(offset)
    items = list(db.scalars(items_stmt).all())

    return IssueListResponse(
        items=[IssueRead.model_validate(i) for i in items],
        total=total,
        limit=limit,
        offset=offset,
    )
