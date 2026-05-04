"""HTML and PDF report endpoints for a single crawl.

Both routes use the same Jinja2 template — ``report.html`` returns it
straight to the browser (print-friendly), ``report.pdf`` runs it through
WeasyPrint server-side and serves the resulting bytes.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.orm import Session

from backend.app.api.auth import require_token
from backend.app.db.base import get_db
from backend.app.models.crawl import Crawl
from backend.app.models.project import Project
from backend.app.services.reports import report_html, report_pdf

router = APIRouter(
    prefix="/api/projects/{project_id}/crawls/{crawl_id}",
    tags=["reports"],
    dependencies=[Depends(require_token)],
)


def _require_project_and_crawl(
    project_id: int, crawl_id: int, db: Session
) -> tuple[Project, Crawl]:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    crawl = db.get(Crawl, crawl_id)
    if crawl is None or crawl.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Crawl not found")
    return project, crawl


@router.get(
    "/report.html",
    response_class=HTMLResponse,
    responses={200: {"content": {"text/html": {}}}},
)
def crawl_report_html(
    project_id: int, crawl_id: int, db: Session = Depends(get_db)
) -> HTMLResponse:
    project, crawl = _require_project_and_crawl(project_id, crawl_id, db)
    html = report_html(db, project, crawl)
    return HTMLResponse(content=html, media_type="text/html; charset=utf-8")


@router.get(
    "/report.pdf",
    responses={200: {"content": {"application/pdf": {}}}},
)
def crawl_report_pdf(project_id: int, crawl_id: int, db: Session = Depends(get_db)) -> Response:
    project, crawl = _require_project_and_crawl(project_id, crawl_id, db)
    pdf = report_pdf(db, project, crawl)
    filename = f"seo-report-{project.domain}-crawl-{crawl.id}.pdf"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )
