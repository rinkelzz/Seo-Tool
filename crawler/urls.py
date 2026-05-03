"""URL utilities: normalisation, internal/external classification, parameter detection."""

from __future__ import annotations

from urllib.parse import urldefrag, urljoin, urlparse, urlunparse

# Schemes that the crawler will follow. Anything else (mailto, tel, javascript, …) is dropped.
FOLLOWABLE_SCHEMES = frozenset({"http", "https"})

# Common session-id query parameters we use to flag "URL has session id" issues.
SESSION_PARAM_NAMES = frozenset(
    {
        "sid",
        "sessid",
        "sessionid",
        "session_id",
        "phpsessid",
        "jsessionid",
        "aspsessionid",
        "cfid",
        "cftoken",
    }
)


def normalize_url(url: str, *, base: str | None = None) -> str | None:
    """Return a canonical absolute form of ``url``, or ``None`` if it's not crawlable.

    Steps:
    1. Resolve relative URLs against ``base`` (if given)
    2. Drop fragments (``#section``)
    3. Lowercase scheme and host
    4. Strip default ports (``:80`` for http, ``:443`` for https)
    5. Reject non-http(s) schemes
    """
    if base:
        url = urljoin(base, url)
    url, _ = urldefrag(url)

    parsed = urlparse(url.strip())
    if parsed.scheme.lower() not in FOLLOWABLE_SCHEMES:
        return None
    if not parsed.netloc:
        return None

    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    if (scheme == "http" and netloc.endswith(":80")) or (
        scheme == "https" and netloc.endswith(":443")
    ):
        netloc = netloc.rsplit(":", 1)[0]

    path = parsed.path or "/"
    return urlunparse((scheme, netloc, path, parsed.params, parsed.query, ""))


def host_of(url: str) -> str:
    """Lowercase host (without port) for ``url``."""
    netloc = urlparse(url).netloc.lower()
    return netloc.split(":", 1)[0]


def is_same_site(url: str, base_url: str) -> bool:
    """True if ``url`` and ``base_url`` share registrable host (subdomain-aware match).

    We treat ``example.com`` and ``www.example.com`` as the same site. Any other host
    (incl. ``shop.example.com``) is considered external.
    """
    a, b = host_of(url), host_of(base_url)
    if not a or not b:
        return False
    return _strip_www(a) == _strip_www(b)


def _strip_www(host: str) -> str:
    return host[4:] if host.startswith("www.") else host


def url_depth(url: str) -> int:
    """Number of path segments below root: ``/a/b/c`` → 3, ``/`` → 0."""
    path = urlparse(url).path or "/"
    return sum(1 for seg in path.split("/") if seg)


def has_session_id(url: str) -> bool:
    """True if the query string contains a recognised session-id parameter."""
    query = urlparse(url).query
    if not query:
        return False
    for chunk in query.split("&"):
        name = chunk.split("=", 1)[0].lower()
        if name in SESSION_PARAM_NAMES:
            return True
    return False


def has_dynamic_params(url: str) -> bool:
    """True if the URL has a non-empty query string."""
    return bool(urlparse(url).query)
