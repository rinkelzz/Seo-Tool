"""Integration tests for the external link checker (uses ``respx``)."""

from __future__ import annotations

import httpx
import pytest
import respx

from crawler.engine import CrawledPage, CrawlResult
from crawler.external import check_external_links, to_status_map
from crawler.extract import ExtractedLink, PageData
from crawler.fetcher import FetchResult


def _crawl_with_externals(*urls: str) -> CrawlResult:
    """Build a one-page crawl whose page links to all given external URLs."""
    links = [
        ExtractedLink(target_url=u, anchor_text="x", rel=None, is_internal=False, is_followed=True)
        for u in urls
    ]
    pd = PageData(
        url="https://site.test/",
        content_hash="x" * 64,
        html_size=1000,
        title="t",
        meta_description="d",
        meta_robots=None,
        canonical_url=None,
        language="de",
        h1="h",
        h1_count=1,
        word_count=10,
        text_excerpt="",
        images=[],
        links=links,
    )
    fr = FetchResult(
        url="https://site.test/",
        final_url="https://site.test/",
        status_code=200,
        response_time_ms=1,
        content_type="text/html",
        body=b"<html></html>",
        encoding="utf-8",
    )
    cp = CrawledPage(fetch=fr, page_data=pd, depth=0)
    cr = CrawlResult()
    cr.pages.append(cp)
    cr.pages_seen = 1
    cr.pages_fetched = 1
    return cr


@pytest.mark.asyncio
@respx.mock
async def test_probes_distinct_urls_once() -> None:
    a = respx.head("https://other.test/a").mock(return_value=httpx.Response(200))
    b = respx.head("https://other.test/b").mock(return_value=httpx.Response(404))
    crawl = _crawl_with_externals(
        "https://other.test/a",
        "https://other.test/a",  # duplicate — should be deduplicated
        "https://other.test/b",
    )

    results = await check_external_links(crawl, concurrency=4)
    statuses = to_status_map(results)

    assert statuses == {"https://other.test/a": 200, "https://other.test/b": 404}
    assert a.call_count == 1  # deduplicated
    assert b.call_count == 1


@pytest.mark.asyncio
@respx.mock
async def test_falls_back_to_get_when_head_unsupported() -> None:
    head = respx.head("https://other.test/x").mock(return_value=httpx.Response(405))
    get = respx.get("https://other.test/x").mock(return_value=httpx.Response(200))
    crawl = _crawl_with_externals("https://other.test/x")

    results = await check_external_links(crawl, concurrency=2)
    assert to_status_map(results) == {"https://other.test/x": 200}
    assert head.called
    assert get.called


@pytest.mark.asyncio
@respx.mock
async def test_unreachable_url_returns_none_status() -> None:
    respx.head("https://other.test/x").mock(side_effect=httpx.ConnectError("boom"))
    crawl = _crawl_with_externals("https://other.test/x")

    results = await check_external_links(crawl, concurrency=2)
    statuses = to_status_map(results)

    assert statuses == {"https://other.test/x": None}
    assert results["https://other.test/x"].error is not None


@pytest.mark.asyncio
async def test_no_externals_returns_empty() -> None:
    cr = CrawlResult()  # no pages
    results = await check_external_links(cr, concurrency=2)
    assert results == {}
