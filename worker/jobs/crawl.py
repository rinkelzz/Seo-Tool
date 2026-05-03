"""Crawl job: drive the crawler and persist pages, links, images, issues, scores."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import structlog

from analyzers.base import Finding, FindingCategory
from analyzers.scoring import compute_scores, overall_score
from analyzers.tech_meta import analyze_tech_meta
from backend.app.core.settings import get_settings
from backend.app.db.base import get_session_factory
from backend.app.models.crawl import Crawl, CrawlStatus
from backend.app.models.image import Image
from backend.app.models.issue import Issue, IssueCategory, IssueSeverity
from backend.app.models.link import Link
from backend.app.models.page import Page
from backend.app.models.project import Project
from crawler.engine import CrawlConfig, CrawledPage, CrawlResult
from crawler.engine import run_crawl as _run_crawler

log = structlog.get_logger(__name__)


def run_crawl_job(crawl_id: int) -> None:
    """Entry point invoked by RQ. Runs the async crawl in a fresh event loop."""
    SessionLocal = get_session_factory()
    settings = get_settings()

    with SessionLocal() as db:
        crawl = db.get(Crawl, crawl_id)
        if crawl is None:
            log.warning("crawl_not_found", crawl_id=crawl_id)
            return
        project = db.get(Project, crawl.project_id)
        if project is None:
            log.error("crawl_project_missing", crawl_id=crawl_id)
            crawl.status = CrawlStatus.FAILED
            crawl.error_message = "project not found"
            db.commit()
            return

        log.info(
            "crawl_started", crawl_id=crawl_id, project_id=project.id, base_url=project.base_url
        )
        crawl.status = CrawlStatus.RUNNING
        crawl.started_at = datetime.now(tz=timezone.utc)
        db.commit()

        config = CrawlConfig(
            base_url=project.base_url,
            user_agent=settings.crawler_user_agent,
            max_pages=200,
            max_depth=5,
            concurrency=settings.crawler_max_concurrency,
            timeout=float(settings.crawler_timeout_seconds),
            respect_robots=project.robots_respect,
        )

        try:
            crawl_result = asyncio.run(_run_crawler(config))
        except Exception as exc:  # noqa: BLE001
            log.exception("crawl_failed", crawl_id=crawl_id)
            crawl.status = CrawlStatus.FAILED
            crawl.error_message = f"{type(exc).__name__}: {exc}"[:500]
            crawl.finished_at = datetime.now(tz=timezone.utc)
            db.commit()
            return

        try:
            url_to_page_id = _persist_pages_and_assets(db, crawl_id, crawl_result)
            findings = analyze_tech_meta(crawl_result)
            _persist_findings(db, crawl_id, findings, url_to_page_id)
            _persist_scores(db, crawl, findings, len(crawl_result.html_pages()))
            crawl.status = CrawlStatus.COMPLETED
            crawl.pages_crawled = crawl_result.pages_fetched
            crawl.finished_at = datetime.now(tz=timezone.utc)
            db.commit()
        except Exception as exc:  # noqa: BLE001
            log.exception("crawl_persist_failed", crawl_id=crawl_id)
            db.rollback()
            crawl.status = CrawlStatus.FAILED
            crawl.error_message = f"persist: {type(exc).__name__}: {exc}"[:500]
            crawl.finished_at = datetime.now(tz=timezone.utc)
            db.commit()
            return

        log.info(
            "crawl_completed",
            crawl_id=crawl_id,
            pages=crawl.pages_crawled,
            findings=len(findings),
            score_overall=float(crawl.score_overall) if crawl.score_overall is not None else None,
        )


# The API enqueues "worker.jobs.crawl.run_crawl" — keep that name stable.
run_crawl = run_crawl_job


# --- persistence helpers ---------------------------------------------------


def _persist_pages_and_assets(
    db, crawl_id: int, crawl_result: CrawlResult  # noqa: ANN001 (Session)
) -> dict[str, int]:
    """Insert ``Page``, ``Image``, ``Link`` rows. Returns final_url → page_id."""
    url_to_page_id: dict[str, int] = {}

    for cp in crawl_result.pages:
        page = _build_page(crawl_id, cp)
        db.add(page)
        db.flush()  # need page.id for images/links
        url_to_page_id[cp.fetch.final_url] = page.id

        if cp.page_data is not None:
            for img in cp.page_data.images:
                db.add(
                    Image(
                        page_id=page.id,
                        src=img.src[:2048],
                        alt=img.alt[:2048] if img.alt else None,
                        has_alt=img.has_alt,
                    )
                )
            for link in cp.page_data.links:
                db.add(
                    Link(
                        crawl_id=crawl_id,
                        source_page_id=page.id,
                        target_url=link.target_url[:2048],
                        anchor_text=link.anchor_text[:2048] if link.anchor_text else None,
                        rel=link.rel[:255] if link.rel else None,
                        is_internal=link.is_internal,
                        is_followed=link.is_followed,
                    )
                )
    db.flush()
    return url_to_page_id


def _build_page(crawl_id: int, cp: CrawledPage) -> Page:
    fr = cp.fetch
    pd = cp.page_data
    return Page(
        crawl_id=crawl_id,
        url=fr.final_url[:2048],
        status_code=fr.status_code,
        response_time_ms=fr.response_time_ms,
        content_type=(fr.content_type or "")[:255] or None,
        content_hash=pd.content_hash if pd else None,
        html_size=pd.html_size if pd else (len(fr.body) if fr.body else None),
        title=(pd.title[:1024] if pd and pd.title else None),
        meta_description=(pd.meta_description[:2048] if pd and pd.meta_description else None),
        meta_robots=(pd.meta_robots[:255] if pd and pd.meta_robots else None),
        canonical_url=(pd.canonical_url[:2048] if pd and pd.canonical_url else None),
        h1=(pd.h1[:2048] if pd and pd.h1 else None),
        language=(pd.language[:16] if pd and pd.language else None),
        word_count=pd.word_count if pd else None,
        depth=cp.depth,
        is_indexable=(pd.is_indexable if pd else None),
        fetch_error=fr.error[:512] if fr.error else None,
    )


def _persist_findings(
    db,  # noqa: ANN001
    crawl_id: int,
    findings: list[Finding],
    url_to_page_id: dict[str, int],
) -> None:
    for f in findings:
        db.add(
            Issue(
                crawl_id=crawl_id,
                page_id=url_to_page_id.get(f.page_url) if f.page_url else None,
                rule_id=f.rule_id,
                category=IssueCategory(f.category.value),
                severity=IssueSeverity(f.severity.value),
                payload=f.payload or None,
            )
        )
    db.flush()


def _persist_scores(
    db,  # noqa: ANN001
    crawl: Crawl,
    findings: list[Finding],
    pages_evaluated: int,
) -> None:
    scores = compute_scores(findings, pages_evaluated=pages_evaluated)
    crawl.score_tech = scores.get(FindingCategory.TECH_META)
    crawl.score_struct = scores.get(FindingCategory.STRUCTURE)
    crawl.score_content = scores.get(FindingCategory.CONTENT)
    crawl.score_overall = overall_score(scores)
