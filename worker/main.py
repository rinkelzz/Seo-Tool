"""RQ worker entrypoint."""

import logging

import structlog
from redis import Redis
from rq import Queue, Worker

from backend.app.core.settings import get_settings
from worker.jobs.scheduler import schedule_initial_tick


def _configure_logging(level: str) -> None:
    logging.basicConfig(level=level)
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
    )


def main() -> None:
    settings = get_settings()
    _configure_logging(settings.app_log_level)

    log = structlog.get_logger("worker")
    log.info("worker_starting", redis=settings.redis_url)

    redis_conn = Redis.from_url(settings.redis_url)
    queues = [Queue("crawl", connection=redis_conn)]

    # Kick off the recurring scheduler tick — replaces any stale tick from a
    # previous worker run so we don't double-tick after restarts. The tick
    # itself re-enqueues for the next interval at the end of each run.
    try:
        schedule_initial_tick()
    except Exception as exc:  # noqa: BLE001
        log.warning("scheduler_initial_tick_failed", error=str(exc))

    worker = Worker(queues, connection=redis_conn)
    worker.work(with_scheduler=True)


if __name__ == "__main__":
    main()
