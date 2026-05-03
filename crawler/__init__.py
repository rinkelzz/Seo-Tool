"""Async HTTP crawler engine.

Public surface:
- ``CrawlConfig``       — runtime knobs for a crawl
- ``CrawlResult``       — what the engine returns to the caller
- ``run_crawl``         — async coroutine driving the BFS crawl
- data records (``FetchResult``, ``PageData``, ``ExtractedLink``, ``ExtractedImage``)
"""

from crawler.engine import CrawlConfig, CrawlResult, run_crawl
from crawler.extract import ExtractedImage, ExtractedLink, PageData, extract_page
from crawler.fetcher import FetchResult, fetch

__all__ = [
    "CrawlConfig",
    "CrawlResult",
    "ExtractedImage",
    "ExtractedLink",
    "FetchResult",
    "PageData",
    "extract_page",
    "fetch",
    "run_crawl",
]
