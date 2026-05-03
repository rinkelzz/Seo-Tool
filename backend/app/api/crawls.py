"""Crawl endpoints: list, trigger, detail, summary."""

from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.api.auth import require_token
from backend.app.db.base import get_db
from backend.app.models.crawl import Crawl, CrawlStatus
from backend.app.models.issue import Issue, IssueCategory, IssueSeverity
from backend.app.models.project import Project
from backend.app.schemas.crawl import CrawlRead
from backend.app.schemas.issue import CrawlSummary, IssueCount
from backend.app.services.queue import get_crawl_queue

router = APIRouter(
    prefix="/api/projects/{project_id}/crawls",
    tags=["crawls"],
    dependencies=[Depends(require_token)],
)


def _require_crawl(project_id: int, crawl_id: int, db: Session) -> Crawl:
    if db.get(Project, project_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    crawl = db.get(Crawl, crawl_id)
    if crawl is None or crawl.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Crawl not found")
    return crawl


@router.get("", response_model=list[CrawlRead])
def list_crawls(project_id: int, db: Session = Depends(get_db)) -> list[Crawl]:
    if db.get(Project, project_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    stmt = select(Crawl).where(Crawl.project_id == project_id).order_by(Crawl.id.desc())
    return list(db.scalars(stmt).all())


@router.post("", response_model=CrawlRead, status_code=status.HTTP_201_CREATED)
def trigger_crawl(project_id: int, db: Session = Depends(get_db)) -> Crawl:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    crawl = Crawl(project_id=project.id, status=CrawlStatus.QUEUED)
    db.add(crawl)
    db.commit()
    db.refresh(crawl)

    queue = get_crawl_queue()
    queue.enqueue("worker.jobs.crawl.run_crawl", crawl.id, job_id=f"crawl:{crawl.id}")

    return crawl


@router.get("/{crawl_id}", response_model=CrawlRead)
def get_crawl(project_id: int, crawl_id: int, db: Session = Depends(get_db)) -> Crawl:
    return _require_crawl(project_id, crawl_id, db)


@router.get("/{crawl_id}/summary", response_model=CrawlSummary)
def get_crawl_summary(
    project_id: int, crawl_id: int, db: Session = Depends(get_db)
) -> CrawlSummary:
    """Issue counts grouped by category, severity, and rule."""
    _require_crawl(project_id, crawl_id, db)

    # Per-rule counts (also gives us category + severity for free)
    stmt = (
        select(Issue.rule_id, Issue.category, Issue.severity, func.count(Issue.id))
        .where(Issue.crawl_id == crawl_id)
        .group_by(Issue.rule_id, Issue.category, Issue.severity)
        .order_by(func.count(Issue.id).desc())
    )
    by_rule: list[IssueCount] = []
    by_category: dict[IssueCategory, int] = defaultdict(int)
    by_severity: dict[IssueSeverity, int] = defaultdict(int)
    total = 0
    for rule_id, category, severity, count in db.execute(stmt).all():
        by_rule.append(
            IssueCount(rule_id=rule_id, category=category, severity=severity, count=count)
        )
        by_category[category] += count
        by_severity[severity] += count
        total += count

    return CrawlSummary(
        by_category=dict(by_category),
        by_severity=dict(by_severity),
        by_rule=by_rule,
        total=total,
    )
