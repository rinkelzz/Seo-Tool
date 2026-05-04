"""HTML / PDF report and crawl-comparison endpoints.

- ``report.html`` / ``report.pdf`` — single-crawl reports (Phase 7-A/B).
- ``compare/{other_id}.html`` — diff between two crawls of the same
  project, ordered by which is older (the smaller-id crawl is treated
  as "before"). Same Jinja2 template engine, separate template.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, Response, StreamingResponse
from sqlalchemy.orm import Session

from backend.app.api.auth import require_token
from backend.app.db.base import get_db
from backend.app.models.crawl import Crawl
from backend.app.models.project import Project
from backend.app.services.comparison import build_comparison
from backend.app.services.csv_export import stream_issues_csv
from backend.app.services.reports import (
    render_comparison_html,
    report_html,
    report_pdf,
)

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


@router.get(
    "/compare/{other_id}.html",
    response_class=HTMLResponse,
    responses={200: {"content": {"text/html": {}}}},
)
def crawl_compare_html(
    project_id: int,
    crawl_id: int,
    other_id: int,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Render the diff between ``crawl_id`` and ``other_id``.

    The smaller of the two ids is treated as "before" so the comparison
    always reads chronologically (assuming crawl ids are monotonic).
    """
    if crawl_id == other_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot compare a crawl with itself",
        )

    project, crawl_primary = _require_project_and_crawl(project_id, crawl_id, db)
    other = db.get(Crawl, other_id)
    if other is None or other.project_id != project_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Other crawl not found in this project",
        )

    crawl_a, crawl_b = (
        (crawl_primary, other) if crawl_primary.id < other.id else (other, crawl_primary)
    )
    ctx = build_comparison(db, project, crawl_a, crawl_b)
    return HTMLResponse(
        content=render_comparison_html(ctx),
        media_type="text/html; charset=utf-8",
    )


@router.get(
    "/issues.csv",
    responses={200: {"content": {"text/csv": {}}}},
)
def crawl_issues_csv(
    project_id: int, crawl_id: int, db: Session = Depends(get_db)
) -> StreamingResponse:
    """Stream all findings of one crawl as a CSV file (UTF-8 with BOM)."""
    project, crawl = _require_project_and_crawl(project_id, crawl_id, db)
    filename = f"seo-issues-{project.domain}-crawl-{crawl.id}.csv"
    return StreamingResponse(
        stream_issues_csv(db, crawl.id),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
