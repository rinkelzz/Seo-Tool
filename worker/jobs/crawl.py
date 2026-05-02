"""Crawl job skeleton — Phase 0: just records that a crawl was triggered.

The real crawler implementation lives in Phase 1 (crawler/).
"""

from datetime import datetime, timezone

import structlog

from backend.app.db.base import get_session_factory
from backend.app.models.crawl import Crawl, CrawlStatus

log = structlog.get_logger(__name__)


def run_crawl(crawl_id: int) -> None:
    """Phase 0 stub: marks the crawl as completed without doing any actual crawling.

    Phase 1 will replace the body with the real crawler invocation.
    """
    SessionLocal = get_session_factory()
    with SessionLocal() as db:
        crawl = db.get(Crawl, crawl_id)
        if crawl is None:
            log.warning("crawl_not_found", crawl_id=crawl_id)
            return

        log.info("crawl_started", crawl_id=crawl_id, project_id=crawl.project_id)
        crawl.status = CrawlStatus.RUNNING
        crawl.started_at = datetime.now(tz=timezone.utc)
        db.commit()

        # Phase 1: invoke crawler.engine.run(project=crawl.project) here
        # and analyzers afterwards. For now we just complete the crawl.

        crawl.status = CrawlStatus.COMPLETED
        crawl.finished_at = datetime.now(tz=timezone.utc)
        crawl.pages_crawled = 0
        db.commit()

        log.info("crawl_completed", crawl_id=crawl_id)
