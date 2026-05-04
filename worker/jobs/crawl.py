"""Crawl job: drive the crawler and persist pages, links, images, issues, scores."""

from __future__ import annotations

import asyncio
import hashlib
from datetime import datetime, timezone

import structlog

from analyzers.base import Finding, FindingCategory
from analyzers.content import analyze_content
from analyzers.scoring import compute_scores, overall_score
from analyzers.structure import analyze_structure
from analyzers.tech_meta import analyze_tech_meta
from backend.app.core.settings import get_settings
from backend.app.db.base import get_session_factory
from backend.app.models.content_block import ContentBlock
from backend.app.models.crawl import Crawl, CrawlStatus
from backend.app.models.image import Image
from backend.app.models.issue import Issue, IssueCategory, IssueSeverity
from backend.app.models.link import Link
from backend.app.models.page import Page
from backend.app.models.project import Project
from backend.app.models.resource import Resource, ResourceType
from backend.app.models.sitemap import Sitemap
from crawler.engine import CrawlConfig, CrawledPage, CrawlResult
from crawler.engine import run_crawl as _run_crawler
from crawler.external import check_external_links, to_status_map
from crawler.fetcher import make_client
from crawler.resources import probe_resources
from crawler.sitemap import SitemapBundle, discover_and_fetch
from crawler.spellcheck import SpellingResult, check_spelling

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
            (
                crawl_result,
                external_statuses,
                sitemap_bundle,
                resource_statuses,
                spelling_results,
            ) = asyncio.run(_crawl_and_probes(config, settings))
        except Exception as exc:  # noqa: BLE001
            log.exception("crawl_failed", crawl_id=crawl_id)
            crawl.status = CrawlStatus.FAILED
            crawl.error_message = f"{type(exc).__name__}: {exc}"[:500]
            crawl.finished_at = datetime.now(tz=timezone.utc)
            db.commit()
            return

        try:
            url_to_page_id = _persist_pages_and_assets(
                db, crawl_id, crawl_result, external_statuses, resource_statuses
            )
            _persist_sitemaps(db, project.id, sitemap_bundle)
            findings = (
                analyze_tech_meta(crawl_result, resource_statuses=resource_statuses or None)
                + analyze_structure(
                    crawl_result,
                    base_url=project.base_url,
                    external_statuses=external_statuses,
                    sitemap_urls=sitemap_bundle.all_urls or None,
                )
                + analyze_content(
                    crawl_result,
                    spelling_results=spelling_results or None,
                    spelling_min_errors=settings.crawler_spellcheck_min_errors,
                )
            )
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


async def _crawl_and_probes(config: CrawlConfig, settings) -> tuple[  # noqa: ANN001 (Settings)
    CrawlResult,
    dict[str, int | None],
    SitemapBundle,
    dict[str, int | None],
    dict[str, SpellingResult],
]:
    """Run the main crawl, then external-link probe, sitemap discovery,
    resource probe, and (optionally) the LanguageTool spell-check — all in
    the same event loop.

    Each post-crawl step is best-effort: failures don't tank the whole crawl,
    the analyzer just skips findings that depend on the missing data.
    """
    concurrency = settings.crawler_max_concurrency
    crawl_result = await _run_crawler(config)

    try:
        checks = await check_external_links(
            crawl_result, user_agent=config.user_agent, concurrency=concurrency
        )
        external_statuses = to_status_map(checks)
    except Exception as exc:  # noqa: BLE001
        log.warning("external_link_check_failed", error=str(exc))
        external_statuses = {}

    try:
        async with make_client(
            user_agent=config.user_agent,
            timeout=config.timeout,
            max_connections=concurrency,
        ) as client:
            bundle = await discover_and_fetch(
                client, base_url=config.base_url, timeout=config.timeout
            )
    except Exception as exc:  # noqa: BLE001
        log.warning("sitemap_discovery_failed", error=str(exc))
        bundle = SitemapBundle()

    try:
        probes = await probe_resources(
            crawl_result, user_agent=config.user_agent, concurrency=concurrency
        )
        resource_statuses = {url: probe.status_code for url, probe in probes.items()}
    except Exception as exc:  # noqa: BLE001
        log.warning("resource_probe_failed", error=str(exc))
        resource_statuses = {}

    spelling_results: dict[str, SpellingResult] = {}
    if settings.crawler_spellcheck_enabled:
        try:
            spelling_results = await check_spelling(
                crawl_result,
                languagetool_url=settings.languagetool_url,
                max_chars=settings.crawler_spellcheck_max_chars,
                concurrency=min(concurrency, 4),
                timeout=float(settings.crawler_spellcheck_timeout_seconds),
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("spellcheck_failed", error=str(exc))

    return crawl_result, external_statuses, bundle, resource_statuses, spelling_results


# --- persistence helpers ---------------------------------------------------


def _persist_pages_and_assets(
    db,  # noqa: ANN001 (Session)
    crawl_id: int,
    crawl_result: CrawlResult,
    external_statuses: dict[str, int | None] | None = None,
    resource_statuses: dict[str, int | None] | None = None,
) -> dict[str, int]:
    """Insert ``Page``, ``Image``, ``Link``, ``Resource``, ``ContentBlock`` rows.

    Returns final_url → page_id mapping for the findings persistence step.

    ``external_statuses`` is the (optional) map produced by the external link
    checker; when present, link rows get their ``target_status_code`` filled in.
    ``resource_statuses`` is the analogous map for embedded CSS/JS/image
    assets — used to populate ``Resource.status_code``.
    """
    ext_statuses = external_statuses or {}
    res_statuses = resource_statuses or {}
    url_to_page_id: dict[str, int] = {}

    for cp in crawl_result.pages:
        page = _build_page(crawl_id, cp)
        db.add(page)
        db.flush()  # need page.id for images/links
        url_to_page_id[cp.fetch.final_url] = page.id

        if cp.page_data is None:
            continue

        page_is_https = cp.fetch.final_url.startswith("https://")

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
                    target_status_code=ext_statuses.get(link.target_url),
                )
            )
        for resource in cp.page_data.resources:
            db.add(
                Resource(
                    crawl_id=crawl_id,
                    source_page_id=page.id,
                    url=resource.url[:2048],
                    resource_type=ResourceType(resource.resource_type),
                    is_internal=resource.is_internal,
                    is_mixed_content=page_is_https and resource.url.startswith("http://"),
                    status_code=res_statuses.get(resource.url),
                )
            )
        for block in cp.page_data.content_blocks:
            normalized = block.lower().strip()
            block_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
            db.add(
                ContentBlock(
                    page_id=page.id,
                    block_hash=block_hash,
                    text_excerpt=block[:2000],
                    word_count=len(block.split()),
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
        redirect_chain=fr.redirect_chain or None,
        fetch_error=fr.error[:512] if fr.error else None,
    )


def _persist_sitemaps(
    db,  # noqa: ANN001
    project_id: int,
    bundle: SitemapBundle,
) -> None:
    """Replace this project's Sitemap rows with the freshly-fetched ones.

    Sitemaps live at the project level (not the crawl level), so each crawl
    overwrites the previous snapshot. Historical comparison would need a
    schema change; for now we only need the current sitemap state to drive
    the diff for this crawl.
    """
    if not bundle.sitemaps:
        return

    db.query(Sitemap).filter(Sitemap.project_id == project_id).delete(synchronize_session=False)
    now = datetime.now(tz=timezone.utc)
    for sm in bundle.sitemaps:
        db.add(
            Sitemap(
                project_id=project_id,
                url=sm.url[:2048],
                last_fetched_at=now,
                urls_count=len(sm.urls),
                urls=sm.urls or None,
                fetch_error=sm.fetch_error[:512] if sm.fetch_error else None,
            )
        )
    db.flush()


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
