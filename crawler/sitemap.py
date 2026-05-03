"""Sitemap discovery, fetching, and parsing.

Strategy:
1. Look at robots.txt for ``Sitemap:`` directives — these are authoritative.
2. Fall back to ``<base_url>/sitemap.xml`` when robots.txt declares none.
3. For every discovered sitemap, fetch and parse:
   - regular ``<urlset>`` → collect ``<loc>`` entries
   - ``<sitemapindex>`` → recursively fetch each child sitemap
   - ``.xml.gz`` → ungzip transparently
4. Return a flat ``SitemapBundle`` with one ``SitemapResult`` per fetched
   sitemap (errors recorded, not raised).

Recursion is depth-bounded to avoid pathological loops.
"""

from __future__ import annotations

import gzip
import re
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

import httpx
import structlog
from selectolax.parser import HTMLParser

from crawler.fetcher import fetch
from crawler.urls import normalize_url

log = structlog.get_logger(__name__)

MAX_SITEMAP_DEPTH = 3
MAX_SITEMAPS_TOTAL = 50

# Pre-compiled patterns kept module-level — evaluated for every <loc> we parse.
_SITEMAP_DIRECTIVE_RE = re.compile(r"^\s*sitemap\s*:\s*(\S+)\s*$", re.IGNORECASE | re.MULTILINE)
_LOC_RE = re.compile(r"<loc>\s*([^<]+?)\s*</loc>", re.IGNORECASE)
_SITEMAPINDEX_RE = re.compile(r"<sitemapindex\b", re.IGNORECASE)


@dataclass
class SitemapResult:
    """Outcome of fetching one sitemap document."""

    url: str
    urls: list[str] = field(default_factory=list)
    child_sitemaps: list[str] = field(default_factory=list)
    fetch_error: str | None = None
    is_index: bool = False


@dataclass
class SitemapBundle:
    """Aggregate result of a discovery pass for one project."""

    sitemaps: list[SitemapResult] = field(default_factory=list)

    @property
    def all_urls(self) -> set[str]:
        """Union of every URL declared in any successfully-fetched sitemap."""
        out: set[str] = set()
        for sm in self.sitemaps:
            out.update(sm.urls)
        return out


async def discover_and_fetch(
    client: httpx.AsyncClient,
    *,
    base_url: str,
    timeout: float = 15.0,
) -> SitemapBundle:
    """Discover sitemap URLs (via robots.txt or default), then recursively fetch."""
    seeds = await _discover_seed_sitemaps(client, base_url=base_url, timeout=timeout)
    bundle = SitemapBundle()
    visited: set[str] = set()

    queue: list[tuple[str, int]] = [(s, 0) for s in seeds]
    while queue and len(bundle.sitemaps) < MAX_SITEMAPS_TOTAL:
        url, depth = queue.pop(0)
        if url in visited:
            continue
        visited.add(url)
        if depth > MAX_SITEMAP_DEPTH:
            continue

        result = await _fetch_one(client, url, timeout=timeout)
        bundle.sitemaps.append(result)
        for child in result.child_sitemaps:
            if child not in visited:
                queue.append((child, depth + 1))
    return bundle


async def _discover_seed_sitemaps(
    client: httpx.AsyncClient, *, base_url: str, timeout: float
) -> list[str]:
    parsed = urlparse(base_url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    seeds: list[str] = []

    robots_result = await fetch(client, robots_url, timeout=timeout)
    if robots_result.ok and robots_result.body:
        text = robots_result.body.decode(robots_result.encoding or "utf-8", "replace")
        for match in _SITEMAP_DIRECTIVE_RE.finditer(text):
            normalised = normalize_url(match.group(1).strip(), base=base_url)
            if normalised and normalised not in seeds:
                seeds.append(normalised)

    if not seeds:
        default = normalize_url("/sitemap.xml", base=base_url)
        if default:
            seeds.append(default)

    return seeds


async def _fetch_one(client: httpx.AsyncClient, url: str, *, timeout: float) -> SitemapResult:
    result = await fetch(client, url, timeout=timeout)
    if not result.ok:
        return SitemapResult(
            url=url,
            fetch_error=(
                result.error or f"HTTP {result.status_code}"
                if result.status_code is not None
                else "no response"
            ),
        )

    body = result.body
    if url.endswith(".gz") or _looks_gzipped(body):
        try:
            body = gzip.decompress(body)
        except OSError as exc:
            return SitemapResult(url=url, fetch_error=f"gunzip failed: {exc}"[:500])

    try:
        text = body.decode(result.encoding or "utf-8", "replace")
    except Exception as exc:  # noqa: BLE001
        return SitemapResult(url=url, fetch_error=f"decode failed: {exc}"[:500])

    return _parse_sitemap_text(url, text)


def _parse_sitemap_text(sitemap_url: str, text: str) -> SitemapResult:
    """Parse a sitemap's XML text. Cheap regex first, then a strict pass."""
    is_index = bool(_SITEMAPINDEX_RE.search(text))
    locs = [loc.strip() for loc in _LOC_RE.findall(text)]

    # Fallback: try selectolax XML parsing if regex returned nothing — handles
    # exotic spacing / namespaced documents reasonably well.
    if not locs and ("<loc" in text.lower()):
        try:
            tree = HTMLParser(text)
            locs = [
                node.text(deep=True, strip=True)
                for node in tree.css("loc")
                if node.text(deep=True, strip=True)
            ]
        except Exception:  # noqa: BLE001
            locs = []

    base_for_resolve = sitemap_url
    normalised: list[str] = []
    for loc in locs:
        absolute = urljoin(base_for_resolve, loc)
        norm = normalize_url(absolute)
        if norm:
            normalised.append(norm)

    if is_index:
        return SitemapResult(url=sitemap_url, child_sitemaps=normalised, is_index=True)
    return SitemapResult(url=sitemap_url, urls=normalised)


def _looks_gzipped(body: bytes) -> bool:
    return len(body) >= 2 and body[0] == 0x1F and body[1] == 0x8B
