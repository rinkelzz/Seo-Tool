"""Project CRUD endpoints."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.api.auth import require_token
from backend.app.db.base import get_db
from backend.app.models.project import Project
from backend.app.schemas.project import ProjectCreate, ProjectRead, ProjectUpdate

router = APIRouter(
    prefix="/api/projects",
    tags=["projects"],
    dependencies=[Depends(require_token)],
)


@router.get("", response_model=list[ProjectRead])
def list_projects(db: Session = Depends(get_db)) -> list[Project]:
    return list(db.scalars(select(Project).order_by(Project.id)).all())


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
def create_project(payload: ProjectCreate, db: Session = Depends(get_db)) -> Project:
    project = Project(
        name=payload.name,
        domain=payload.domain,
        base_url=str(payload.base_url),
        robots_respect=payload.robots_respect,
        js_render=payload.js_render,
        schedule_interval_minutes=payload.schedule_interval_minutes,
        next_scheduled_at=_compute_next_scheduled_at(payload.schedule_interval_minutes),
    )
    db.add(project)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Project with domain '{payload.domain}' already exists",
        ) from None
    db.refresh(project)
    return project


@router.get("/{project_id}", response_model=ProjectRead)
def get_project(project_id: int, db: Session = Depends(get_db)) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


@router.patch("/{project_id}", response_model=ProjectRead)
def update_project(
    project_id: int, payload: ProjectUpdate, db: Session = Depends(get_db)
) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        if field == "base_url" and value is not None:
            value = str(value)
        setattr(project, field, value)
    # Recompute next_scheduled_at whenever the user touches the schedule.
    # ``exclude_unset=True`` means we only enter this branch when the
    # client explicitly included the field in the request.
    if "schedule_interval_minutes" in updates:
        project.next_scheduled_at = _compute_next_scheduled_at(updates["schedule_interval_minutes"])
    db.commit()
    db.refresh(project)
    return project


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(project_id: int, db: Session = Depends(get_db)) -> None:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    db.delete(project)
    db.commit()


def _compute_next_scheduled_at(interval_minutes: int | None) -> datetime | None:
    """Initial ``next_scheduled_at`` after creating/changing the schedule.

    ``None`` means no schedule. Otherwise the project's first auto-crawl
    fires roughly one interval after the change — that's intentional: it
    gives the user a chance to look at the freshly-created project before
    it starts crawling itself, and avoids stampedes when many projects
    are created in a batch.
    """
    if interval_minutes is None:
        return None
    return datetime.now(tz=timezone.utc) + timedelta(minutes=interval_minutes)
