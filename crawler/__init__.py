"""Async HTTP crawler engine.

Public surface:
- ``CrawlConfig``       — runtime knobs for a crawl
- ``CrawlResult``       — what the engine returns to the caller
- ``run_crawl``         — async coroutine driving the BFS crawl
- data records (``FetchResult``, ``PageData``, ``ExtractedLink``, ``ExtractedImage``)
"""

from crawler.engine import CrawlConfig, CrawlResult, run_crawl
from crawler.external import ExternalCheck, check_external_links, to_status_map
from crawler.extract import (
    ExtractedImage,
    ExtractedLink,
    ExtractedResource,
    PageData,
    extract_page,
)
from crawler.fetcher import FetchResult, fetch
from crawler.resources import ResourceProbe, probe_resources
from crawler.sitemap import SitemapBundle, SitemapResult, discover_and_fetch
from crawler.spellcheck import SpellingMatch, SpellingResult, check_spelling

__all__ = [
    "CrawlConfig",
    "CrawlResult",
    "ExternalCheck",
    "ExtractedImage",
    "ExtractedLink",
    "ExtractedResource",
    "FetchResult",
    "PageData",
    "ResourceProbe",
    "SitemapBundle",
    "SitemapResult",
    "SpellingMatch",
    "SpellingResult",
    "check_external_links",
    "check_spelling",
    "discover_and_fetch",
    "extract_page",
    "fetch",
    "probe_resources",
    "run_crawl",
    "to_status_map",
]
