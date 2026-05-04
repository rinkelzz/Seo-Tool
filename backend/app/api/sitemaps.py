"""Sitemap list endpoint — surfaces what the crawler discovered."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.api.auth import require_token
from backend.app.db.base import get_db
from backend.app.models.project import Project
from backend.app.models.sitemap import Sitemap
from backend.app.schemas.sitemap import SitemapRead

router = APIRouter(
    prefix="/api/projects/{project_id}/sitemaps",
    tags=["sitemaps"],
    dependencies=[Depends(require_token)],
)


@router.get("", response_model=list[SitemapRead])
def list_sitemaps(project_id: int, db: Session = Depends(get_db)) -> list[Sitemap]:
    if db.get(Project, project_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    stmt = select(Sitemap).where(Sitemap.project_id == project_id).order_by(Sitemap.id.asc())
    return list(db.scalars(stmt).all())
