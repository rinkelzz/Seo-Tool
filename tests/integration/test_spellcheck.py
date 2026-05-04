"""Tests for ``crawler/spellcheck.py`` and the content.spelling.errors rule."""

from __future__ import annotations

import httpx
import pytest
import respx

from analyzers.content import RULE_SPELLING_ERRORS, analyze_content
from crawler.engine import CrawledPage, CrawlResult
from crawler.extract import PageData
from crawler.fetcher import FetchResult
from crawler.spellcheck import SpellingMatch, SpellingResult, check_spelling


def _ok_fetch(url: str) -> FetchResult:
    return FetchResult(
        url=url,
        final_url=url,
        status_code=200,
        response_time_ms=100,
        content_type="text/html",
        body=b"<html></html>",
        encoding="utf-8",
    )


def _make_page(*, url: str, main_text: str, language: str = "de") -> CrawledPage:
    pd = PageData(
        url=url,
        content_hash="x" * 64,
        html_size=1000,
        title="t",
        meta_description="d",
        meta_robots=None,
        canonical_url=None,
        language=language,
        h1="h",
        h1_count=1,
        word_count=len(main_text.split()),
        text_excerpt=main_text[:500],
        main_text=main_text,
        main_word_count=len(main_text.split()),
        content_blocks=[],
    )
    return CrawledPage(fetch=_ok_fetch(url), page_data=pd, depth=0)


def _result(*pages: CrawledPage) -> CrawlResult:
    cr = CrawlResult()
    for p in pages:
        cr.pages.append(p)
        cr.pages_seen += 1
        if p.fetch.ok:
            cr.pages_fetched += 1
    return cr


def _ids(findings) -> list[str]:  # type: ignore[no-untyped-def]
    return [f.rule_id for f in findings]


# ---- crawler.spellcheck (HTTP layer) ------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_spellcheck_parses_lt_response() -> None:
    respx.post("http://lt.test/v2/check").mock(
        return_value=httpx.Response(
            200,
            json={
                "matches": [
                    {
                        "message": "Schreibweise stimmt nicht",
                        "shortMessage": "Tippfehler",
                        "offset": 5,
                        "length": 4,
                        "rule": {"id": "GERMAN_SPELLER_RULE"},
                        "replacements": [{"value": "Hallo"}, {"value": "Hello"}],
                    }
                ]
            },
        )
    )
    crawl = _result(_make_page(url="https://x.test/", main_text="Hier Helo welt."))
    out = await check_spelling(crawl, languagetool_url="http://lt.test", concurrency=2)

    assert "https://x.test/" in out
    result = out["https://x.test/"]
    assert result.error is None
    assert len(result.matches) == 1
    m = result.matches[0]
    assert m.rule_id == "GERMAN_SPELLER_RULE"
    assert m.message.startswith("Schreibweise")
    assert "Hallo" in m.suggestions
    assert m.excerpt  # non-empty


@pytest.mark.asyncio
@respx.mock
async def test_spellcheck_skips_pages_without_main_text() -> None:
    crawl = _result(_make_page(url="https://x.test/", main_text=""))
    out = await check_spelling(crawl, languagetool_url="http://lt.test", concurrency=2)
    assert out == {}


@pytest.mark.asyncio
@respx.mock
async def test_spellcheck_records_http_errors_without_raising() -> None:
    respx.post("http://lt.test/v2/check").mock(return_value=httpx.Response(500, text="boom"))
    crawl = _result(_make_page(url="https://x.test/", main_text="Etwas Text hier."))
    out = await check_spelling(crawl, languagetool_url="http://lt.test", concurrency=2)
    assert out["https://x.test/"].error is not None
    assert out["https://x.test/"].matches == []


@pytest.mark.asyncio
@respx.mock
async def test_spellcheck_records_connect_errors() -> None:
    respx.post("http://lt.test/v2/check").mock(side_effect=httpx.ConnectError("nope"))
    crawl = _result(_make_page(url="https://x.test/", main_text="Etwas Text hier."))
    out = await check_spelling(crawl, languagetool_url="http://lt.test", concurrency=2)
    assert out["https://x.test/"].error is not None


@pytest.mark.asyncio
@respx.mock
async def test_spellcheck_truncates_long_text() -> None:
    """``max_chars`` must clip the request payload — protects LT from being
    flooded with megabyte-scale documents."""
    captured: dict[str, str] = {}

    def _capture(req: httpx.Request) -> httpx.Response:
        body = req.content.decode("utf-8")
        # form-encoded; locate "text=..." and unquote roughly enough to compare length
        captured["body"] = body
        return httpx.Response(200, json={"matches": []})

    respx.post("http://lt.test/v2/check").mock(side_effect=_capture)
    long_text = "wort " * 10000  # 50k chars
    crawl = _result(_make_page(url="https://x.test/", main_text=long_text))
    await check_spelling(crawl, languagetool_url="http://lt.test", concurrency=1, max_chars=200)
    body = captured["body"]
    # The body contains the URL-encoded text. A simple length check on the
    # body is a usable proxy: 200 chars of "wort " should stay well below
    # 5 KB after URL encoding.
    assert len(body) < 5000


# ---- content analyzer integration ---------------------------------------


def _spelling_input(*matches: tuple[str, ...]) -> dict[str, SpellingResult]:
    """Helper: build the spelling_results dict the analyzer expects."""
    return {
        "https://x.test/": SpellingResult(
            url="https://x.test/",
            matches=[
                SpellingMatch(
                    rule_id=m[0] if m else "GENERIC",
                    message="x",
                    short_message="x",
                    excerpt="x",
                    suggestions=[],
                )
                for m in matches
            ],
        )
    }


def test_spelling_finding_emitted_when_threshold_exceeded() -> None:
    crawl = _result(_make_page(url="https://x.test/", main_text="some content"))
    spelling = _spelling_input(("RULE_A",), ("RULE_A",), ("RULE_B",), ("RULE_C",), ("RULE_C",))
    findings = analyze_content(crawl, spelling_results=spelling, spelling_min_errors=5)
    spelling_findings = [f for f in findings if f.rule_id == RULE_SPELLING_ERRORS.rule_id]
    assert len(spelling_findings) == 1
    payload = spelling_findings[0].payload
    assert payload["count"] == 5
    # top_rules ordered by frequency (RULE_A and RULE_C both 2× → tie ok)
    assert "RULE_A" in payload["top_rules"]
    assert payload["min_errors"] == 5


def test_spelling_finding_skipped_below_threshold() -> None:
    crawl = _result(_make_page(url="https://x.test/", main_text="some content"))
    spelling = _spelling_input(("RULE_A",), ("RULE_B",))  # 2 errors, threshold 5
    findings = analyze_content(crawl, spelling_results=spelling, spelling_min_errors=5)
    assert RULE_SPELLING_ERRORS.rule_id not in _ids(findings)


def test_spelling_finding_skipped_when_lt_failed() -> None:
    crawl = _result(_make_page(url="https://x.test/", main_text="some content"))
    spelling = {
        "https://x.test/": SpellingResult(url="https://x.test/", matches=[], error="HTTP 500")
    }
    findings = analyze_content(crawl, spelling_results=spelling, spelling_min_errors=5)
    assert RULE_SPELLING_ERRORS.rule_id not in _ids(findings)


def test_no_spelling_results_means_no_findings() -> None:
    crawl = _result(_make_page(url="https://x.test/", main_text="some content"))
    findings = analyze_content(crawl, spelling_results=None)
    assert RULE_SPELLING_ERRORS.rule_id not in _ids(findings)
