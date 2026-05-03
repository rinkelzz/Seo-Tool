"""Tests for ``crawler/sitemap.py`` — discovery + parsing using ``respx``."""

from __future__ import annotations

import gzip

import httpx
import pytest
import respx

from crawler.fetcher import make_client
from crawler.sitemap import discover_and_fetch

BASE = "https://site.test/"


def _urlset(urls: list[str]) -> str:
    body = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    for u in urls:
        body += f"  <url><loc>{u}</loc></url>\n"
    body += "</urlset>"
    return body


def _index(child_sitemap_urls: list[str]) -> str:
    body = '<?xml version="1.0" encoding="UTF-8"?>\n<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    for u in child_sitemap_urls:
        body += f"  <sitemap><loc>{u}</loc></sitemap>\n"
    body += "</sitemapindex>"
    return body


@pytest.mark.asyncio
@respx.mock
async def test_default_sitemap_xml_used_when_robots_silent() -> None:
    respx.get("https://site.test/robots.txt").mock(return_value=httpx.Response(404))
    respx.get("https://site.test/sitemap.xml").mock(
        return_value=httpx.Response(
            200,
            text=_urlset(["https://site.test/", "https://site.test/about"]),
            headers={"content-type": "application/xml"},
        )
    )

    async with make_client(user_agent="test/1.0") as client:
        bundle = await discover_and_fetch(client, base_url=BASE)

    assert len(bundle.sitemaps) == 1
    assert bundle.sitemaps[0].fetch_error is None
    assert bundle.all_urls == {"https://site.test/", "https://site.test/about"}


@pytest.mark.asyncio
@respx.mock
async def test_robots_txt_directive_is_followed() -> None:
    respx.get("https://site.test/robots.txt").mock(
        return_value=httpx.Response(
            200,
            text=("User-agent: *\n" "Allow: /\n" "Sitemap: https://site.test/custom-sitemap.xml\n"),
            headers={"content-type": "text/plain"},
        )
    )
    respx.get("https://site.test/custom-sitemap.xml").mock(
        return_value=httpx.Response(
            200,
            text=_urlset(["https://site.test/foo"]),
            headers={"content-type": "application/xml"},
        )
    )
    # Default sitemap.xml should NOT be requested
    default = respx.get("https://site.test/sitemap.xml").mock(
        return_value=httpx.Response(200, text="should-not-be-requested")
    )

    async with make_client(user_agent="test/1.0") as client:
        bundle = await discover_and_fetch(client, base_url=BASE)

    assert bundle.all_urls == {"https://site.test/foo"}
    assert default.call_count == 0


@pytest.mark.asyncio
@respx.mock
async def test_sitemapindex_is_followed_recursively() -> None:
    respx.get("https://site.test/robots.txt").mock(return_value=httpx.Response(404))
    respx.get("https://site.test/sitemap.xml").mock(
        return_value=httpx.Response(
            200,
            text=_index(
                [
                    "https://site.test/sitemaps/posts.xml",
                    "https://site.test/sitemaps/pages.xml",
                ]
            ),
            headers={"content-type": "application/xml"},
        )
    )
    respx.get("https://site.test/sitemaps/posts.xml").mock(
        return_value=httpx.Response(
            200,
            text=_urlset(["https://site.test/post-1", "https://site.test/post-2"]),
            headers={"content-type": "application/xml"},
        )
    )
    respx.get("https://site.test/sitemaps/pages.xml").mock(
        return_value=httpx.Response(
            200,
            text=_urlset(["https://site.test/about"]),
            headers={"content-type": "application/xml"},
        )
    )

    async with make_client(user_agent="test/1.0") as client:
        bundle = await discover_and_fetch(client, base_url=BASE)

    assert len(bundle.sitemaps) == 3  # 1 index + 2 children
    assert bundle.all_urls == {
        "https://site.test/post-1",
        "https://site.test/post-2",
        "https://site.test/about",
    }


@pytest.mark.asyncio
@respx.mock
async def test_gzipped_sitemap_is_decompressed() -> None:
    respx.get("https://site.test/robots.txt").mock(
        return_value=httpx.Response(
            200,
            text="Sitemap: https://site.test/sitemap.xml.gz",
            headers={"content-type": "text/plain"},
        )
    )
    payload = _urlset(["https://site.test/zipped"]).encode("utf-8")
    respx.get("https://site.test/sitemap.xml.gz").mock(
        return_value=httpx.Response(
            200, content=gzip.compress(payload), headers={"content-type": "application/gzip"}
        )
    )

    async with make_client(user_agent="test/1.0") as client:
        bundle = await discover_and_fetch(client, base_url=BASE)

    assert bundle.all_urls == {"https://site.test/zipped"}


@pytest.mark.asyncio
@respx.mock
async def test_sitemap_404_records_error_but_does_not_raise() -> None:
    respx.get("https://site.test/robots.txt").mock(return_value=httpx.Response(404))
    respx.get("https://site.test/sitemap.xml").mock(return_value=httpx.Response(404))

    async with make_client(user_agent="test/1.0") as client:
        bundle = await discover_and_fetch(client, base_url=BASE)

    assert len(bundle.sitemaps) == 1
    assert bundle.sitemaps[0].fetch_error is not None
    assert bundle.all_urls == set()


@pytest.mark.asyncio
@respx.mock
async def test_loop_in_sitemap_index_is_bounded() -> None:
    respx.get("https://site.test/robots.txt").mock(return_value=httpx.Response(404))
    # Index points to itself — should not infinite-loop
    respx.get("https://site.test/sitemap.xml").mock(
        return_value=httpx.Response(
            200,
            text=_index(["https://site.test/sitemap.xml"]),
            headers={"content-type": "application/xml"},
        )
    )

    async with make_client(user_agent="test/1.0") as client:
        bundle = await discover_and_fetch(client, base_url=BASE)

    # Visited tracking dedupes the self-reference, so we end up with just the
    # one entry (which is itself an index).
    assert len(bundle.sitemaps) == 1
    assert bundle.sitemaps[0].is_index is True
