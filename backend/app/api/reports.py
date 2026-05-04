"""HTML-Report endpoint for a single crawl.

PDF rendering will arrive in Phase 7-B (WeasyPrint). The HTML produced
here is already print-friendly (``@page``, embedded CSS) so the same
template can be reused.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from backend.app.api.auth import require_token
from backend.app.db.base import get_db
from backend.app.models.crawl import Crawl
from backend.app.models.project import Project
from backend.app.services.reports import report_html

router = APIRouter(
    prefix="/api/projects/{project_id}/crawls/{crawl_id}",
    tags=["reports"],
    dependencies=[Depends(require_token)],
)


@router.get(
    "/report.html",
    response_class=HTMLResponse,
    responses={200: {"content": {"text/html": {}}}},
)
def crawl_report_html(
    project_id: int, crawl_id: int, db: Session = Depends(get_db)
) -> HTMLResponse:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    crawl = db.get(Crawl, crawl_id)
    if crawl is None or crawl.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Crawl not found")

    html = report_html(db, project, crawl)
    return HTMLResponse(content=html, media_type="text/html; charset=utf-8")
