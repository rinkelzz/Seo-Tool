"""End-to-end crawl-engine tests using ``respx`` to mock HTTP."""

from __future__ import annotations

import httpx
import pytest
import respx

from crawler.engine import CrawlConfig, run_crawl


def _html(body: str) -> str:
    return f"<html lang='de'><head><title>OK</title></head><body>{body}</body></html>"


@pytest.mark.asyncio
@respx.mock
async def test_crawls_internal_links_only() -> None:
    respx.get("https://site.test/robots.txt").mock(return_value=httpx.Response(404))
    respx.get("https://site.test/").mock(
        return_value=httpx.Response(
            200,
            html=_html('<a href="/about">About</a><a href="https://other.test/">Ext</a>'),
            headers={"content-type": "text/html"},
        )
    )
    respx.get("https://site.test/about").mock(
        return_value=httpx.Response(
            200,
            html=_html('<a href="/contact">Contact</a>'),
            headers={"content-type": "text/html"},
        )
    )
    respx.get("https://site.test/contact").mock(
        return_value=httpx.Response(
            200, html=_html("<p>contact</p>"), headers={"content-type": "text/html"}
        )
    )

    config = CrawlConfig(base_url="https://site.test/", concurrency=2, max_pages=20)
    result = await run_crawl(config)

    urls = sorted(p.fetch.final_url for p in result.pages)
    assert urls == [
        "https://site.test/",
        "https://site.test/about",
        "https://site.test/contact",
    ]
    assert result.pages_fetched == 3


@pytest.mark.asyncio
@respx.mock
async def test_max_pages_stops_crawl() -> None:
    respx.get("https://site.test/robots.txt").mock(return_value=httpx.Response(404))
    # Build a long internal chain: /, /1, /2, /3, /4, /5
    respx.get("https://site.test/").mock(
        return_value=httpx.Response(
            200,
            html=_html(
                '<a href="/1">1</a><a href="/2">2</a>'
                '<a href="/3">3</a><a href="/4">4</a><a href="/5">5</a>'
            ),
            headers={"content-type": "text/html"},
        )
    )
    for i in range(1, 6):
        respx.get(f"https://site.test/{i}").mock(
            return_value=httpx.Response(
                200, html=_html(f"<p>{i}</p>"), headers={"content-type": "text/html"}
            )
        )

    config = CrawlConfig(base_url="https://site.test/", max_pages=3, concurrency=2)
    result = await run_crawl(config)

    assert result.pages_seen == 3


@pytest.mark.asyncio
@respx.mock
async def test_max_depth_stops_descent() -> None:
    respx.get("https://site.test/robots.txt").mock(return_value=httpx.Response(404))
    respx.get("https://site.test/").mock(
        return_value=httpx.Response(
            200,
            html=_html('<a href="/a">a</a>'),
            headers={"content-type": "text/html"},
        )
    )
    respx.get("https://site.test/a").mock(
        return_value=httpx.Response(
            200, html=_html('<a href="/b">b</a>'), headers={"content-type": "text/html"}
        )
    )
    respx.get("https://site.test/b").mock(
        return_value=httpx.Response(
            200, html=_html('<a href="/c">c</a>'), headers={"content-type": "text/html"}
        )
    )

    config = CrawlConfig(base_url="https://site.test/", max_depth=1, concurrency=2)
    result = await run_crawl(config)

    urls = sorted(p.fetch.final_url for p in result.pages)
    # depth 0 (/) and depth 1 (/a) — but /b at depth 2 is not enqueued
    assert urls == ["https://site.test/", "https://site.test/a"]


@pytest.mark.asyncio
@respx.mock
async def test_robots_blocks_path() -> None:
    respx.get("https://site.test/robots.txt").mock(
        return_value=httpx.Response(
            200,
            text="User-agent: *\nDisallow: /private",
            headers={"content-type": "text/plain"},
        )
    )
    respx.get("https://site.test/").mock(
        return_value=httpx.Response(
            200,
            html=_html('<a href="/private">x</a><a href="/public">y</a>'),
            headers={"content-type": "text/html"},
        )
    )
    respx.get("https://site.test/public").mock(
        return_value=httpx.Response(200, html=_html("ok"), headers={"content-type": "text/html"})
    )
    # /private should NOT be requested. respx will fail the test if it is.

    config = CrawlConfig(base_url="https://site.test/", concurrency=2)
    result = await run_crawl(config)

    blocked = [p for p in result.pages if p.blocked_by_robots]
    fetched = sorted(p.fetch.final_url for p in result.pages if not p.blocked_by_robots)
    assert any("/private" in p.fetch.url for p in blocked)
    assert "https://site.test/public" in fetched


@pytest.mark.asyncio
@respx.mock
async def test_respect_robots_false_ignores_robots() -> None:
    respx.get("https://site.test/robots.txt").mock(
        return_value=httpx.Response(
            200,
            text="User-agent: *\nDisallow: /",
            headers={"content-type": "text/plain"},
        )
    )
    respx.get("https://site.test/").mock(
        return_value=httpx.Response(200, html=_html("ok"), headers={"content-type": "text/html"})
    )

    config = CrawlConfig(base_url="https://site.test/", respect_robots=False, concurrency=2)
    result = await run_crawl(config)
    assert result.pages_fetched == 1


@pytest.mark.asyncio
@respx.mock
async def test_external_links_not_crawled() -> None:
    respx.get("https://site.test/robots.txt").mock(return_value=httpx.Response(404))
    respx.get("https://site.test/").mock(
        return_value=httpx.Response(
            200,
            html=_html('<a href="https://other.test/x">ext</a>'),
            headers={"content-type": "text/html"},
        )
    )
    config = CrawlConfig(base_url="https://site.test/", concurrency=2)
    result = await run_crawl(config)
    urls = [p.fetch.final_url for p in result.pages]
    assert urls == ["https://site.test/"]


@pytest.mark.asyncio
@respx.mock
async def test_failed_fetch_recorded() -> None:
    respx.get("https://site.test/robots.txt").mock(return_value=httpx.Response(404))
    respx.get("https://site.test/").mock(side_effect=httpx.ConnectError("boom"))

    config = CrawlConfig(base_url="https://site.test/", concurrency=2)
    result = await run_crawl(config)
    assert len(result.pages) == 1
    assert result.pages[0].fetch.error is not None
    assert result.pages[0].page_data is None


@pytest.mark.asyncio
@respx.mock
async def test_non_html_recorded_but_not_parsed() -> None:
    respx.get("https://site.test/robots.txt").mock(return_value=httpx.Response(404))
    respx.get("https://site.test/").mock(
        return_value=httpx.Response(
            200, content=b"%PDF-1.4 ...", headers={"content-type": "application/pdf"}
        )
    )
    config = CrawlConfig(base_url="https://site.test/", concurrency=2)
    result = await run_crawl(config)
    assert result.pages[0].page_data is None
    assert result.pages[0].fetch.ok is True
