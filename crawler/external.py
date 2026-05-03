"""External-link status checker.

After the main crawl, we may want to know whether outbound links to other
domains still resolve. This module collects all distinct external URLs from a
``CrawlResult`` and probes each with a single ``HEAD`` request (falling back
to ``GET`` if HEAD is not supported), in parallel with a configurable
concurrency limit.

The output is a ``target_url → status_code | None`` mapping the structure
analyzer turns into ``broken`` / ``unreachable`` findings.
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
class ExternalCheck:
    """Outcome of one external HTTP probe."""

    url: str
    status_code: int | None  # None == request did not complete
    response_time_ms: int
    error: str | None = None


async def check_external_links(
    crawl: CrawlResult,
    *,
    user_agent: str = "SeoToolBot/0.1",
    concurrency: int = 8,
    timeout: float = 10.0,
    head_first: bool = True,
) -> dict[str, ExternalCheck]:
    """Probe all distinct external URLs found in ``crawl``. Returns a map
    keyed by target URL.

    The result deduplicates: if the same external URL is linked from many
    pages, it's still requested only once.
    """
    targets = _collect_external_targets(crawl)
    if not targets:
        return {}

    semaphore = asyncio.Semaphore(concurrency)
    results: dict[str, ExternalCheck] = {}

    async with make_client(
        user_agent=user_agent, timeout=timeout, max_connections=concurrency
    ) as client:

        async def probe(url: str) -> None:
            async with semaphore:
                result = await _probe_one(client, url, head_first=head_first, timeout=timeout)
                results[url] = result

        await asyncio.gather(*(probe(u) for u in targets), return_exceptions=False)

    return results


def _collect_external_targets(crawl: CrawlResult) -> set[str]:
    targets: set[str] = set()
    for cp in crawl.html_pages():
        pd = cp.page_data
        if pd is None:
            continue
        for link in pd.links:
            if not link.is_internal:
                targets.add(link.target_url)
    return targets


async def _probe_one(
    client: httpx.AsyncClient, url: str, *, head_first: bool, timeout: float
) -> ExternalCheck:
    started = time.perf_counter()
    try:
        if head_first:
            response = await client.head(url, timeout=timeout, follow_redirects=True)
            # Many servers don't implement HEAD properly (return 405 / 501) —
            # retry with GET in that case so we don't falsely flag the link.
            if response.status_code in {405, 501}:
                response = await client.get(url, timeout=timeout, follow_redirects=True)
        else:
            response = await client.get(url, timeout=timeout, follow_redirects=True)
    except httpx.HTTPError as exc:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        log.debug("external_probe_failed", url=url, error=str(exc))
        return ExternalCheck(
            url=url,
            status_code=None,
            response_time_ms=elapsed_ms,
            error=f"{type(exc).__name__}: {exc}"[:500],
        )

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    return ExternalCheck(
        url=url,
        status_code=response.status_code,
        response_time_ms=elapsed_ms,
    )


def to_status_map(checks: dict[str, ExternalCheck]) -> dict[str, int | None]:
    """Convenience: drop the per-URL detail and return only ``url → status``."""
    return {url: check.status_code for url, check in checks.items()}
