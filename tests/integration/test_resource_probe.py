"""Integration tests for ``crawler.resources.probe_resources`` (uses respx)."""

from __future__ import annotations

import httpx
import pytest
import respx

from crawler.engine import CrawledPage, CrawlResult
from crawler.extract import ExtractedResource, PageData
from crawler.fetcher import FetchResult
from crawler.resources import probe_resources


def _crawl_with_resources(*urls_and_types: tuple[str, str]) -> CrawlResult:
    resources = [
        ExtractedResource(url=u, resource_type=t, is_internal=False) for (u, t) in urls_and_types
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
        resources=resources,
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
async def test_probes_each_url_once_even_when_referenced_multiple_times() -> None:
    css = respx.head("https://cdn.test/main.css").mock(return_value=httpx.Response(200))
    crawl = _crawl_with_resources(
        ("https://cdn.test/main.css", "stylesheet"),
        ("https://cdn.test/main.css", "stylesheet"),
    )
    results = await probe_resources(crawl, concurrency=4)
    assert len(results) == 1
    assert results["https://cdn.test/main.css"].status_code == 200
    assert css.call_count == 1


@pytest.mark.asyncio
@respx.mock
async def test_falls_back_to_get_when_head_unsupported() -> None:
    head = respx.head("https://cdn.test/app.js").mock(return_value=httpx.Response(405))
    get = respx.get("https://cdn.test/app.js").mock(return_value=httpx.Response(200))
    crawl = _crawl_with_resources(("https://cdn.test/app.js", "script"))
    results = await probe_resources(crawl, concurrency=2)
    assert results["https://cdn.test/app.js"].status_code == 200
    assert head.called
    assert get.called


@pytest.mark.asyncio
@respx.mock
async def test_unreachable_resource_returns_none_status() -> None:
    respx.head("https://broken.test/x.css").mock(side_effect=httpx.ConnectError("boom"))
    crawl = _crawl_with_resources(("https://broken.test/x.css", "stylesheet"))
    results = await probe_resources(crawl, concurrency=2)
    probe = results["https://broken.test/x.css"]
    assert probe.status_code is None
    assert probe.error is not None


@pytest.mark.asyncio
async def test_no_resources_returns_empty() -> None:
    cr = CrawlResult()
    results = await probe_resources(cr, concurrency=2)
    assert results == {}


@pytest.mark.asyncio
@respx.mock
async def test_broken_resource_keeps_status_code() -> None:
    respx.head("https://cdn.test/dead.js").mock(return_value=httpx.Response(404))
    crawl = _crawl_with_resources(("https://cdn.test/dead.js", "script"))
    results = await probe_resources(crawl, concurrency=2)
    assert results["https://cdn.test/dead.js"].status_code == 404
