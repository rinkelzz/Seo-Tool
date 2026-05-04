"""LanguageTool-based spell/grammar checker.

Optional fifth crawl pass — runs only when ``crawler_spellcheck_enabled``
is true. Each crawled HTML page's main content is sent to a self-hosted
LanguageTool instance, which returns an array of matches (rule_id,
message, offset/length, suggested replacements). The content analyzer
turns these into ``content.spelling.errors`` findings.

The LT API is HTTP only — we POST form-encoded payloads to ``/v2/check``
with ``text`` and ``language=auto`` (or the page's declared language if
LT supports it). We don't ship custom dictionaries here; the analyzer
threshold filters out the noise from minor false positives.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field

import httpx
import structlog

from crawler.engine import CrawlResult

log = structlog.get_logger(__name__)

# LanguageTool returns one entry per detected issue. We only keep the
# fields the analyzer actually needs.
_LT_LANGUAGE_FALLBACK = "auto"


@dataclass
class SpellingMatch:
    """One LT match — typo, grammar slip, or style hint."""

    rule_id: str
    message: str
    short_message: str
    excerpt: str
    suggestions: list[str] = field(default_factory=list)


@dataclass
class SpellingResult:
    """Outcome of one page's spell check."""

    url: str
    matches: list[SpellingMatch] = field(default_factory=list)
    error: str | None = None
    response_time_ms: int = 0


async def check_spelling(
    crawl: CrawlResult,
    *,
    languagetool_url: str,
    max_chars: int = 8000,
    concurrency: int = 4,
    timeout: float = 20.0,
) -> dict[str, SpellingResult]:
    """Probe LanguageTool for every HTML page that has extractable main text.

    Returns ``url → SpellingResult``. Pages without main text are skipped
    silently (login forms, asset-only pages, etc.).
    """
    targets: list[tuple[str, str, str | None]] = []
    for cp in crawl.html_pages():
        pd = cp.page_data
        if pd is None or not pd.main_text:
            continue
        text = pd.main_text[:max_chars]
        if not text.strip():
            continue
        targets.append((cp.fetch.final_url, text, pd.language))
    if not targets:
        return {}

    semaphore = asyncio.Semaphore(concurrency)
    results: dict[str, SpellingResult] = {}

    timeout_obj = httpx.Timeout(timeout, connect=5.0)
    async with httpx.AsyncClient(timeout=timeout_obj) as client:

        async def probe(url: str, text: str, language_hint: str | None) -> None:
            async with semaphore:
                results[url] = await _check_one(
                    client,
                    languagetool_url,
                    url=url,
                    text=text,
                    language_hint=language_hint,
                    timeout=timeout,
                )

        await asyncio.gather(
            *(probe(u, t, lang) for u, t, lang in targets),
            return_exceptions=False,
        )

    return results


async def _check_one(
    client: httpx.AsyncClient,
    base_url: str,
    *,
    url: str,
    text: str,
    language_hint: str | None,
    timeout: float,
) -> SpellingResult:
    started = time.perf_counter()
    payload = {
        "text": text,
        "language": _normalise_language(language_hint),
    }

    try:
        response = await client.post(
            f"{base_url.rstrip('/')}/v2/check",
            data=payload,
            timeout=timeout,
        )
    except httpx.HTTPError as exc:
        elapsed = int((time.perf_counter() - started) * 1000)
        log.debug("languagetool_request_failed", url=url, error=str(exc))
        return SpellingResult(
            url=url, error=f"{type(exc).__name__}: {exc}"[:500], response_time_ms=elapsed
        )

    elapsed = int((time.perf_counter() - started) * 1000)
    if response.status_code != 200:
        return SpellingResult(
            url=url,
            error=f"HTTP {response.status_code}: {response.text[:200]}",
            response_time_ms=elapsed,
        )

    try:
        body = response.json()
    except ValueError as exc:
        return SpellingResult(url=url, error=f"invalid JSON: {exc}", response_time_ms=elapsed)

    matches = [_parse_match(m, text) for m in body.get("matches") or []]
    return SpellingResult(url=url, matches=matches, response_time_ms=elapsed)


def _parse_match(match: dict, text: str) -> SpellingMatch:  # type: ignore[type-arg]
    """Turn one LT JSON match into a ``SpellingMatch``.

    ``offset``/``length`` define the slice of ``text`` that triggered the
    match — we extract that slice with ±20 characters of context for the
    finding payload.
    """
    offset = int(match.get("offset", 0))
    length = int(match.get("length", 0))
    pad = 20
    excerpt_start = max(0, offset - pad)
    excerpt_end = min(len(text), offset + length + pad)
    excerpt = text[excerpt_start:excerpt_end].strip()

    rule = match.get("rule") or {}
    suggestions = [
        r.get("value", "")
        for r in (match.get("replacements") or [])
        if isinstance(r, dict) and r.get("value")
    ][:5]

    return SpellingMatch(
        rule_id=str(rule.get("id") or "unknown"),
        message=str(match.get("message", ""))[:300],
        short_message=str(match.get("shortMessage", ""))[:80],
        excerpt=excerpt[:200],
        suggestions=suggestions,
    )


def _normalise_language(hint: str | None) -> str:
    """LanguageTool wants codes like ``de-DE`` or ``en-US`` or ``auto``.

    HTML pages declare ``lang="de"`` or ``lang="en"`` more often than the
    full BCP-47 form, so we map the common short codes to LT's canonical
    variants and fall back to ``auto`` for anything we don't recognise.
    """
    if not hint:
        return _LT_LANGUAGE_FALLBACK
    normalised = hint.strip().lower().replace("_", "-")
    base = normalised.split("-", 1)[0]
    canonical = {
        "de": "de-DE",
        "en": "en-US",
        "fr": "fr",
        "es": "es",
        "it": "it",
        "nl": "nl",
        "pt": "pt-PT",
    }
    if "-" in normalised and len(normalised) >= 5:
        return normalised  # already in the BCP-47 form, trust the page
    return canonical.get(base, _LT_LANGUAGE_FALLBACK)
