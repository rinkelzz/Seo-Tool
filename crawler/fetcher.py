"""HTTP fetcher: a tiny wrapper around ``httpx.AsyncClient`` with timing + redirects.

The fetcher does not interpret HTML at all — it just records the wire-level facts
(status, response time, final URL after redirects, body, content-type). HTML parsing
lives in ``crawler.extract``.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import httpx

DEFAULT_HEADERS: dict[str, str] = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "de,en;q=0.5",
    "Accept-Encoding": "gzip, deflate",
}


@dataclass
class FetchResult:
    """Outcome of one HTTP request."""

    url: str
    final_url: str  # may differ from ``url`` after redirects
    status_code: int | None
    response_time_ms: int
    content_type: str | None
    body: bytes
    encoding: str | None
    redirect_chain: list[str] = field(default_factory=list)
    error: str | None = None  # set when status_code is None (network/timeout)

    @property
    def ok(self) -> bool:
        return self.status_code is not None and 200 <= self.status_code < 400

    @property
    def is_html(self) -> bool:
        if not self.content_type:
            return False
        return self.content_type.split(";", 1)[0].strip().lower() in {
            "text/html",
            "application/xhtml+xml",
        }


async def fetch(
    client: httpx.AsyncClient,
    url: str,
    *,
    timeout: float = 15.0,
) -> FetchResult:
    """Fetch ``url`` once. Never raises — failures land in ``FetchResult.error``.

    The HTTP client is passed in (rather than created here) so that connection
    pooling and the user-agent live with the engine, not with each call.
    """
    started = time.perf_counter()
    try:
        response = await client.get(url, timeout=timeout, follow_redirects=True)
    except httpx.HTTPError as exc:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return FetchResult(
            url=url,
            final_url=url,
            status_code=None,
            response_time_ms=elapsed_ms,
            content_type=None,
            body=b"",
            encoding=None,
            error=f"{type(exc).__name__}: {exc}"[:500],
        )

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    redirect_chain = [str(r.url) for r in response.history]

    return FetchResult(
        url=url,
        final_url=str(response.url),
        status_code=response.status_code,
        response_time_ms=elapsed_ms,
        content_type=response.headers.get("content-type"),
        body=response.content,
        encoding=response.encoding,
        redirect_chain=redirect_chain,
    )


def make_client(
    *, user_agent: str, timeout: float = 15.0, max_connections: int = 16
) -> httpx.AsyncClient:
    """Return a configured ``httpx.AsyncClient`` ready for crawling.

    The client follows redirects automatically. Callers are responsible for
    closing it (use as ``async with``).
    """
    headers = {**DEFAULT_HEADERS, "User-Agent": user_agent}
    limits = httpx.Limits(
        max_connections=max_connections, max_keepalive_connections=max_connections
    )
    return httpx.AsyncClient(
        headers=headers,
        timeout=timeout,
        limits=limits,
        follow_redirects=True,
        http2=False,
    )
