"""robots.txt fetching and per-host caching.

Wraps `protego` (a strict, well-tested robots.txt parser). One ``RobotsCache``
instance lives for the duration of a crawl: the first time we see a host, we
fetch ``/robots.txt`` once and consult the cached parser thereafter.
"""

from __future__ import annotations

from urllib.parse import urlparse

import httpx
import structlog
from protego import Protego

from crawler.fetcher import fetch
from crawler.urls import host_of

log = structlog.get_logger(__name__)


class RobotsCache:
    """Per-host robots.txt cache for one crawl run."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        user_agent: str,
        respect: bool = True,
    ) -> None:
        self._client = client
        self._user_agent = user_agent
        self._respect = respect
        self._cache: dict[str, Protego | None] = {}

    async def can_fetch(self, url: str) -> bool:
        """True if the configured user-agent may fetch ``url``.

        When ``respect=False`` we always allow. When the robots fetch fails or the
        host has no robots.txt we treat that as "allowed" (the conservative-for-
        availability default — matches Googlebot's behaviour for 404).
        """
        if not self._respect:
            return True

        parser = await self._parser_for(url)
        if parser is None:
            return True
        return parser.can_fetch(url, self._user_agent)

    async def crawl_delay(self, url: str) -> float | None:
        """Return the per-host crawl-delay declared in robots.txt, if any."""
        if not self._respect:
            return None
        parser = await self._parser_for(url)
        if parser is None:
            return None
        try:
            return parser.crawl_delay(self._user_agent)
        except Exception:  # pragma: no cover - protego internals
            return None

    async def _parser_for(self, url: str) -> Protego | None:
        host = host_of(url)
        if host in self._cache:
            return self._cache[host]

        parsed = urlparse(url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        result = await fetch(self._client, robots_url, timeout=10.0)

        parser: Protego | None = None
        if result.ok and result.body:
            try:
                parser = Protego.parse(result.body.decode(result.encoding or "utf-8", "replace"))
            except Exception as exc:  # pragma: no cover - parse-failure path
                log.warning("robots_parse_failed", host=host, error=str(exc))
                parser = None
        else:
            log.debug(
                "robots_unavailable",
                host=host,
                status=result.status_code,
                error=result.error,
            )

        self._cache[host] = parser
        return parser
