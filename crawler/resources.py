"""Resource (CSS/JS/Image) status checker.

Run after the main crawl to probe every distinct resource URL collected
across all pages. Mirrors the pattern of ``crawler/external.py`` but
narrower: we only care about HTTP status (and timing for diagnostics),
no follow-redirect concerns, no robots.txt — these are static assets.

Each unique URL is requested once, even when many pages reference it.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

import httpx
import structlog

from crawler.engine import CrawlResult
from crawler.fetcher import make_client

log = structlog.get_logger(__name__)


@dataclass
class ResourceProbe:
    """Outcome of one resource HEAD/GET request."""

    url: str
    status_code: int | None  # ``None`` when the request couldn't complete
    response_time_ms: int
    error: str | None = None


async def probe_resources(
    crawl: CrawlResult,
    *,
    user_agent: str = "SeoToolBot/0.1",
    concurrency: int = 8,
    timeout: float = 10.0,
    head_first: bool = True,
) -> dict[str, ResourceProbe]:
    """Probe every distinct resource URL referenced by any crawled page.

    Returns a map keyed by resource URL. The caller (worker) joins this map
    onto the per-page resource list when persisting.
    """
    targets = _collect_resource_urls(crawl)
    if not targets:
        return {}

    semaphore = asyncio.Semaphore(concurrency)
    results: dict[str, ResourceProbe] = {}

    async with make_client(
        user_agent=user_agent, timeout=timeout, max_connections=concurrency
    ) as client:

        async def probe(url: str) -> None:
            async with semaphore:
                results[url] = await _probe_one(client, url, head_first=head_first, timeout=timeout)

        await asyncio.gather(*(probe(u) for u in targets), return_exceptions=False)

    return results


def _collect_resource_urls(crawl: CrawlResult) -> set[str]:
    """Union of every distinct resource URL across all crawled HTML pages."""
    out: set[str] = set()
    for cp in crawl.html_pages():
        pd = cp.page_data
        if pd is None:
            continue
        for resource in pd.resources:
            out.add(resource.url)
    return out


async def _probe_one(
    client: httpx.AsyncClient, url: str, *, head_first: bool, timeout: float
) -> ResourceProbe:
    started = time.perf_counter()
    try:
        if head_first:
            response = await client.head(url, timeout=timeout, follow_redirects=True)
            # CDN buckets / cheap servers often return 405/501 for HEAD —
            # retry with GET so we don't falsely flag the asset.
            if response.status_code in {405, 501}:
                response = await client.get(url, timeout=timeout, follow_redirects=True)
        else:
            response = await client.get(url, timeout=timeout, follow_redirects=True)
    except httpx.HTTPError as exc:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        log.debug("resource_probe_failed", url=url, error=str(exc))
        return ResourceProbe(
            url=url,
            status_code=None,
            response_time_ms=elapsed_ms,
            error=f"{type(exc).__name__}: {exc}"[:500],
        )

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    return ResourceProbe(url=url, status_code=response.status_code, response_time_ms=elapsed_ms)
