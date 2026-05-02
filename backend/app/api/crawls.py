"""Crawl endpoints: list project crawls and trigger new ones."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.api.auth import require_token
from backend.app.db.base import get_db
from backend.app.models.crawl import Crawl, CrawlStatus
from backend.app.models.project import Project
from backend.app.schemas.crawl import CrawlRead
from backend.app.services.queue import get_crawl_queue

router = APIRouter(
    prefix="/api/projects/{project_id}/crawls",
    tags=["crawls"],
    dependencies=[Depends(require_token)],
)


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

    # Enqueue the job (Phase 0: stub job; Phase 1: real crawler)
    queue = get_crawl_queue()
    queue.enqueue("worker.jobs.crawl.run_crawl", crawl.id, job_id=f"crawl:{crawl.id}")

    return crawl
