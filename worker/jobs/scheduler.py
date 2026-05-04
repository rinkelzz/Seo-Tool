"""Scheduler tick — enqueue crawls for projects that are due.

Runs as a recurring RQ job every ``TICK_INTERVAL`` seconds. The worker
process is started with ``with_scheduler=True``, which lets us re-enqueue
ourselves via ``Queue.enqueue_in``.

The mechanism is intentionally simple:
1. Find all projects with ``next_scheduled_at <= now`` and a non-null
   ``schedule_interval_minutes``.
2. For each: skip if a crawl is already queued/running for it (no
   double-enqueue when the previous crawl is still in flight); otherwise
   create a new ``Crawl`` row and enqueue the regular crawl job.
3. Advance ``next_scheduled_at`` by the interval — even when we skipped
   the enqueue, so a long-running crawl doesn't pile up missed slots.
4. Re-enqueue the tick for ``now + TICK_INTERVAL``.

A single worker is assumed. Multiple workers running this concurrently
would race on the project rows; we'd then need a row-level lock.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db.base import get_session_factory
from backend.app.models.crawl import Crawl, CrawlStatus
from backend.app.models.project import Project
from backend.app.services.queue import get_crawl_queue

log = structlog.get_logger(__name__)

# How often the tick runs. 60 s strikes a reasonable balance: the smallest
# user-configurable interval is 15 min, so we never miss a slot by more
# than a minute.
TICK_INTERVAL_SECONDS = 60

# Stable RQ job_id for the recurring tick — lets us detect/replace an
# existing pending tick instead of stacking duplicates on every worker
# restart.
SCHEDULER_TICK_JOB_ID = "scheduler-tick"


def run_scheduled_crawls() -> dict[str, int]:
    """One scheduler tick. Returns small stats dict for the caller/log."""
    SessionLocal = get_session_factory()
    enqueued = 0
    skipped_in_flight = 0
    advanced = 0

    with SessionLocal() as db:
        due = _find_due_projects(db)
        for project in due:
            advanced += 1
            if _has_active_crawl(db, project.id):
                skipped_in_flight += 1
            else:
                _enqueue_scheduled_crawl(db, project.id)
                enqueued += 1
            project.next_scheduled_at = datetime.now(tz=timezone.utc) + timedelta(
                minutes=project.schedule_interval_minutes or 0
            )
        if due:
            db.commit()

    log.info(
        "scheduler_tick",
        enqueued=enqueued,
        skipped_in_flight=skipped_in_flight,
        advanced=advanced,
    )
    _reschedule_self()
    return {
        "enqueued": enqueued,
        "skipped_in_flight": skipped_in_flight,
        "advanced": advanced,
    }


def schedule_initial_tick() -> None:
    """Enqueue the very first tick when the worker starts up.

    Called from ``worker/main.py`` right before ``worker.work(...)``. Idempotent
    on repeated calls — any stale tick from a previous run is deleted first
    so we don't double-tick.
    """
    _enqueue_tick(TICK_INTERVAL_SECONDS)
    log.info("scheduler_initial_tick_enqueued", in_seconds=TICK_INTERVAL_SECONDS)


# ---- helpers --------------------------------------------------------------


def _find_due_projects(db: Session) -> list[Project]:
    now = datetime.now(tz=timezone.utc)
    stmt = (
        select(Project)
        .where(Project.schedule_interval_minutes.is_not(None))
        .where(Project.next_scheduled_at.is_not(None))
        .where(Project.next_scheduled_at <= now)
    )
    return list(db.scalars(stmt).all())


def _has_active_crawl(db: Session, project_id: int) -> bool:
    stmt = (
        select(Crawl.id)
        .where(Crawl.project_id == project_id)
        .where(Crawl.status.in_([CrawlStatus.QUEUED, CrawlStatus.RUNNING]))
        .limit(1)
    )
    return db.scalar(stmt) is not None


def _enqueue_scheduled_crawl(db: Session, project_id: int) -> None:
    crawl = Crawl(project_id=project_id, status=CrawlStatus.QUEUED)
    db.add(crawl)
    db.commit()
    db.refresh(crawl)
    queue = get_crawl_queue()
    queue.enqueue(
        "worker.jobs.crawl.run_crawl",
        crawl.id,
        job_id=f"crawl-{crawl.id}",
    )


def _reschedule_self() -> None:
    _enqueue_tick(TICK_INTERVAL_SECONDS)


def _enqueue_tick(in_seconds: int) -> None:
    """Schedule the tick ``in_seconds`` from now, replacing any existing one.

    The stable ``job_id`` (``scheduler-tick``) makes this de-dup easy: we try
    to fetch+delete the existing job first, then enqueue a fresh one. RQ's
    ``Job.fetch`` raises when the job doesn't exist — that's the no-op path.
    """
    queue = get_crawl_queue()
    try:
        from rq.job import Job

        existing = Job.fetch(SCHEDULER_TICK_JOB_ID, connection=queue.connection)
        existing.delete()
    except Exception:  # noqa: BLE001 — NoSuchJobError or any registry weirdness
        pass
    queue.enqueue_in(
        timedelta(seconds=in_seconds),
        "worker.jobs.scheduler.run_scheduled_crawls",
        job_id=SCHEDULER_TICK_JOB_ID,
    )
