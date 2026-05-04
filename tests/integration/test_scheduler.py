"""Tests for the cron-style scheduler tick + project schedule fields."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from backend.app.models.crawl import Crawl, CrawlStatus
from backend.app.models.project import Project


def _to_naive(dt: datetime | None) -> datetime:
    """SQLite stores datetimes as naive — drop tzinfo before comparing."""
    assert dt is not None
    return dt.replace(tzinfo=None) if dt.tzinfo else dt


# ---- Pydantic / API schedule fields --------------------------------------


def test_project_create_with_schedule(client, auth_headers) -> None:
    resp = client.post(
        "/api/projects",
        json={
            "name": "Sched",
            "domain": "sched.example",
            "base_url": "https://sched.example/",
            "schedule_interval_minutes": 60,
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["schedule_interval_minutes"] == 60
    # next_scheduled_at should be set ~1h from now
    assert body["next_scheduled_at"] is not None


def test_project_create_without_schedule_has_null_fields(client, auth_headers) -> None:
    resp = client.post(
        "/api/projects",
        json={
            "name": "NoSched",
            "domain": "nosched.example",
            "base_url": "https://nosched.example/",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["schedule_interval_minutes"] is None
    assert body["next_scheduled_at"] is None


def test_project_create_rejects_too_short_interval(client, auth_headers) -> None:
    resp = client.post(
        "/api/projects",
        json={
            "name": "Bad",
            "domain": "bad.example",
            "base_url": "https://bad.example/",
            "schedule_interval_minutes": 5,  # below 15-minute floor
        },
        headers=auth_headers,
    )
    assert resp.status_code == 422


def test_patch_schedule_updates_next_scheduled_at(client, auth_headers) -> None:
    project = client.post(
        "/api/projects",
        json={
            "name": "Patch",
            "domain": "patch.example",
            "base_url": "https://patch.example/",
        },
        headers=auth_headers,
    ).json()

    resp = client.patch(
        f"/api/projects/{project['id']}",
        json={"schedule_interval_minutes": 1440},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["schedule_interval_minutes"] == 1440
    assert body["next_scheduled_at"] is not None


def test_patch_clears_schedule(client, auth_headers, db_session) -> None:
    """Setting schedule_interval_minutes to null in PATCH must clear both
    fields so the scheduler stops touching the project."""
    project = client.post(
        "/api/projects",
        json={
            "name": "Clear",
            "domain": "clear.example",
            "base_url": "https://clear.example/",
            "schedule_interval_minutes": 60,
        },
        headers=auth_headers,
    ).json()
    assert project["next_scheduled_at"] is not None

    resp = client.patch(
        f"/api/projects/{project['id']}",
        json={"schedule_interval_minutes": None},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["schedule_interval_minutes"] is None
    assert body["next_scheduled_at"] is None


# ---- Scheduler tick ------------------------------------------------------


@pytest.fixture
def scheduler_with_mocked_queue(monkeypatch, engine) -> MagicMock:
    """Patch ``get_session_factory`` (so the tick uses the in-memory test DB)
    and ``get_crawl_queue`` (so we capture enqueues without touching Redis)."""
    from sqlalchemy.orm import sessionmaker

    SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    fake_queue = MagicMock()

    monkeypatch.setattr("worker.jobs.scheduler.get_session_factory", lambda: SessionLocal)
    monkeypatch.setattr("worker.jobs.scheduler.get_crawl_queue", lambda: fake_queue)
    return fake_queue


def _make_due_project(db_session, *, interval: int = 60) -> Project:
    project = Project(
        name="Due",
        domain=f"due-{interval}.example",
        base_url=f"https://due-{interval}.example/",
        robots_respect=True,
        js_render=False,
        schedule_interval_minutes=interval,
        # Force "due" by setting next run in the past
        next_scheduled_at=datetime.now(tz=timezone.utc) - timedelta(minutes=1),
    )
    db_session.add(project)
    db_session.commit()
    return project


def test_tick_enqueues_due_project(db_session, scheduler_with_mocked_queue) -> None:
    from worker.jobs.scheduler import run_scheduled_crawls

    project = _make_due_project(db_session, interval=60)
    project_id = project.id

    stats = run_scheduled_crawls()

    assert stats["enqueued"] == 1
    assert stats["advanced"] == 1
    # Crawl row created
    crawl = db_session.query(Crawl).filter(Crawl.project_id == project_id).one()
    assert crawl.status == CrawlStatus.QUEUED
    # Crawl was passed to the queue (the first enqueue is the crawl, the
    # second is the tick reschedule)
    enqueue_calls = scheduler_with_mocked_queue.enqueue.call_args_list
    assert any(
        call.args[0] == "worker.jobs.crawl.run_crawl" and call.args[1] == crawl.id
        for call in enqueue_calls
    )
    # next_scheduled_at advanced into the future
    db_session.expire_all()
    project = db_session.get(Project, project_id)
    # SQLite stores datetimes as naive — strip tzinfo before comparing
    assert _to_naive(project.next_scheduled_at) > datetime.now(tz=timezone.utc).replace(tzinfo=None)


def test_tick_skips_project_with_active_crawl(db_session, scheduler_with_mocked_queue) -> None:
    """If a queued/running crawl already exists for the project, the tick
    must NOT enqueue another one — but should still advance the schedule."""
    from worker.jobs.scheduler import run_scheduled_crawls

    project = _make_due_project(db_session, interval=60)
    project_id = project.id
    db_session.add(Crawl(project_id=project_id, status=CrawlStatus.RUNNING))
    db_session.commit()

    stats = run_scheduled_crawls()
    assert stats["enqueued"] == 0
    assert stats["skipped_in_flight"] == 1
    assert stats["advanced"] == 1

    # No new crawl row
    crawls = db_session.query(Crawl).filter(Crawl.project_id == project_id).all()
    assert len(crawls) == 1
    assert crawls[0].status == CrawlStatus.RUNNING

    # Schedule still advanced
    db_session.expire_all()
    project = db_session.get(Project, project_id)
    # SQLite stores datetimes as naive — strip tzinfo before comparing
    assert _to_naive(project.next_scheduled_at) > datetime.now(tz=timezone.utc).replace(tzinfo=None)


def test_tick_skips_project_without_schedule(db_session, scheduler_with_mocked_queue) -> None:
    project = Project(
        name="Manual",
        domain="manual.example",
        base_url="https://manual.example/",
        robots_respect=True,
        js_render=False,
        schedule_interval_minutes=None,
        next_scheduled_at=None,
    )
    db_session.add(project)
    db_session.commit()

    from worker.jobs.scheduler import run_scheduled_crawls

    stats = run_scheduled_crawls()
    assert stats["enqueued"] == 0
    assert stats["advanced"] == 0


def test_tick_skips_project_not_yet_due(db_session, scheduler_with_mocked_queue) -> None:
    project = Project(
        name="Future",
        domain="future.example",
        base_url="https://future.example/",
        robots_respect=True,
        js_render=False,
        schedule_interval_minutes=60,
        next_scheduled_at=datetime.now(tz=timezone.utc) + timedelta(hours=1),
    )
    db_session.add(project)
    db_session.commit()

    from worker.jobs.scheduler import run_scheduled_crawls

    stats = run_scheduled_crawls()
    assert stats["enqueued"] == 0
    assert stats["advanced"] == 0


def test_tick_reschedules_itself(db_session, scheduler_with_mocked_queue) -> None:
    """After running, the tick must enqueue itself again so the recurring
    loop doesn't stop."""
    from worker.jobs.scheduler import (
        SCHEDULER_TICK_JOB_ID,
        TICK_INTERVAL_SECONDS,
        run_scheduled_crawls,
    )

    # Patch Job.fetch so the dedup branch silently no-ops (no real Redis)
    with (
        patch("worker.jobs.scheduler.Job", create=True)
        if False
        else patch.dict(
            "sys.modules",
            {"rq.job": MagicMock()},
        )
    ):
        run_scheduled_crawls()

    # Look for an enqueue_in call with the stable tick job_id
    enqueue_in_calls = scheduler_with_mocked_queue.enqueue_in.call_args_list
    assert any(
        call.kwargs.get("job_id") == SCHEDULER_TICK_JOB_ID
        and call.args[0] == timedelta(seconds=TICK_INTERVAL_SECONDS)
        for call in enqueue_in_calls
    )
