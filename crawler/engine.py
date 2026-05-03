"""BFS crawl engine.

The engine drives the high-level crawl loop:
1. Start with ``base_url`` at depth 0
2. For each URL: check robots.txt, fetch, extract HTML
3. Enqueue same-site links (subject to ``max_pages`` / ``max_depth``)
4. Yield ``CrawledPage`` records as they finish (so the caller can persist them
   incrementally without holding the whole crawl in memory)

The engine produces no analyzers' findings — those run after the crawl on the
collected page data.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

import httpx
import structlog

from crawler.extract import PageData, extract_page
from crawler.fetcher import FetchResult, fetch, make_client
from crawler.robots import RobotsCache
from crawler.urls import is_same_site, normalize_url

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class CrawlConfig:
    base_url: str
    user_agent: str = "SeoToolBot/0.1"
    max_pages: int = 200
    max_depth: int = 5
    concurrency: int = 8
    timeout: float = 15.0
    respect_robots: bool = True


@dataclass
class CrawledPage:
    """One completed page: HTTP-level facts plus the parsed HTML (if any)."""

    fetch: FetchResult
    page_data: PageData | None
    depth: int
    discovered_from: str | None = None
    blocked_by_robots: bool = False


@dataclass
class CrawlResult:
    """Aggregate snapshot returned by ``run_crawl``."""

    pages: list[CrawledPage] = field(default_factory=list)
    pages_seen: int = 0  # incl. blocked / failed
    pages_fetched: int = 0  # only successful HTTP responses

    def html_pages(self) -> list[CrawledPage]:
        return [p for p in self.pages if p.page_data is not None]


async def run_crawl(config: CrawlConfig) -> CrawlResult:
    """Run a full crawl synchronously (i.e. await until finished) and return all pages."""
    result = CrawlResult()
    async for crawled in iter_crawl(config):
        result.pages.append(crawled)
        result.pages_seen += 1
        if crawled.fetch.ok:
            result.pages_fetched += 1
    return result


async def iter_crawl(config: CrawlConfig) -> AsyncIterator[CrawledPage]:
    """Async-iterate over crawled pages so callers can persist incrementally."""
    start = normalize_url(config.base_url)
    if start is None:
        raise ValueError(f"Invalid base_url: {config.base_url!r}")

    seen: set[str] = {start}
    queue: asyncio.Queue[tuple[str, int, str | None]] = asyncio.Queue()
    queue.put_nowait((start, 0, None))

    semaphore = asyncio.Semaphore(config.concurrency)
    pages_done = 0
    in_flight = 0
    output: asyncio.Queue[CrawledPage | None] = asyncio.Queue()

    async with make_client(
        user_agent=config.user_agent,
        timeout=config.timeout,
        max_connections=config.concurrency,
    ) as client:
        robots = RobotsCache(client, user_agent=config.user_agent, respect=config.respect_robots)

        async def worker(url: str, depth: int, src: str | None) -> None:
            nonlocal in_flight
            try:
                async with semaphore:
                    crawled = await _process_one(
                        client=client,
                        robots=robots,
                        url=url,
                        depth=depth,
                        src=src,
                    )
                # Enqueue newly discovered links (only from same-site HTML pages)
                if (
                    crawled.page_data is not None
                    and depth < config.max_depth
                    and is_same_site(crawled.fetch.final_url, config.base_url)
                ):
                    for link in crawled.page_data.links:
                        if not link.is_internal:
                            continue
                        target = link.target_url
                        if target in seen:
                            continue
                        if len(seen) >= config.max_pages:
                            break
                        seen.add(target)
                        queue.put_nowait((target, depth + 1, crawled.fetch.final_url))
                await output.put(crawled)
            finally:
                in_flight -= 1

        tasks: set[asyncio.Task[None]] = set()
        try:
            while True:
                # Spawn workers while we have capacity and queued URLs
                while (
                    in_flight < config.concurrency
                    and not queue.empty()
                    and pages_done < config.max_pages
                ):
                    url, depth, src = queue.get_nowait()
                    pages_done += 1
                    in_flight += 1
                    task = asyncio.create_task(worker(url, depth, src))
                    tasks.add(task)
                    task.add_done_callback(tasks.discard)

                # We may exit only when no work is in flight, no URLs are queued,
                # AND there are no completed pages still waiting to be yielded.
                if in_flight == 0 and queue.empty() and output.empty():
                    break

                # Wait for the next finished worker
                crawled = await output.get()
                if crawled is not None:
                    yield crawled

        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            for task in tasks:
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task


async def _process_one(
    *,
    client: httpx.AsyncClient,
    robots: RobotsCache,
    url: str,
    depth: int,
    src: str | None,
) -> CrawledPage:
    if not await robots.can_fetch(url):
        log.info("robots_blocked", url=url)
        return CrawledPage(
            fetch=FetchResult(
                url=url,
                final_url=url,
                status_code=None,
                response_time_ms=0,
                content_type=None,
                body=b"",
                encoding=None,
                error="blocked_by_robots",
            ),
            page_data=None,
            depth=depth,
            discovered_from=src,
            blocked_by_robots=True,
        )

    result = await fetch(client, url)
    page_data: PageData | None = None
    if result.ok and result.is_html and result.body:
        try:
            page_data = extract_page(
                url=result.final_url, body=result.body, encoding=result.encoding
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("extract_failed", url=url, error=str(exc))

    return CrawledPage(fetch=result, page_data=page_data, depth=depth, discovered_from=src)
