"""Tech-meta analyzer tests.

Builds synthetic ``CrawlResult`` objects directly so we don't need real HTTP.
"""

from __future__ import annotations

from analyzers.tech_meta import (
    RULE_H1_MISSING,
    RULE_H1_MULTIPLE,
    RULE_HTML_TOO_LARGE,
    RULE_IMG_ALT_MISSING,
    RULE_LANG_MISSING,
    RULE_META_DESC_DUPLICATE,
    RULE_META_DESC_MISSING,
    RULE_PAGE_FETCH_FAILED,
    RULE_PAGE_HTTP_ERROR,
    RULE_PAGE_NOINDEX,
    RULE_RESPONSE_MEDIUM,
    RULE_RESPONSE_SLOW,
    RULE_TITLE_DUPLICATE,
    RULE_TITLE_MISSING,
    RULE_TITLE_TOO_LONG,
    RULE_TITLE_TOO_SHORT,
    RULE_URL_DYNAMIC,
    RULE_URL_SESSION,
    RULE_URL_TOO_DEEP,
    RULE_URL_TOO_LONG,
    analyze_tech_meta,
)
from crawler.engine import CrawledPage, CrawlResult
from crawler.extract import ExtractedImage, ExtractedLink, PageData
from crawler.fetcher import FetchResult


def _ok_fetch(url: str, ms: int = 100, status: int = 200) -> FetchResult:
    return FetchResult(
        url=url,
        final_url=url,
        status_code=status,
        response_time_ms=ms,
        content_type="text/html",
        body=b"<html></html>",
        encoding="utf-8",
    )


def _make_page(
    *,
    url: str = "https://example.com/p",
    title: str | None = "A reasonable, sensible page title for SEO purposes",
    meta_description: (
        str | None
    ) = "A meta description that is sufficiently long to satisfy our heuristics for being good enough.",
    h1: str | None = "Heading",
    h1_count: int = 1,
    language: str | None = "de",
    images: list[ExtractedImage] | None = None,
    links: list[ExtractedLink] | None = None,
    meta_robots: str | None = None,
    html_size: int = 5000,
    response_ms: int = 100,
    status: int = 200,
    fetch_error: str | None = None,
) -> CrawledPage:
    fr = _ok_fetch(url, ms=response_ms, status=status)
    if fetch_error:
        fr.error = fetch_error
        fr.status_code = None
    pd = PageData(
        url=url,
        content_hash="x" * 64,
        html_size=html_size,
        title=title,
        meta_description=meta_description,
        meta_robots=meta_robots,
        canonical_url=None,
        language=language,
        h1=h1,
        h1_count=h1_count,
        word_count=100,
        text_excerpt="",
        images=images or [],
        links=links or [],
    )
    return CrawledPage(fetch=fr, page_data=pd if not fetch_error else None, depth=0)


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


# --- title rules ---


def test_title_missing() -> None:
    r = _result(_make_page(title=None))
    assert RULE_TITLE_MISSING.rule_id in _ids(analyze_tech_meta(r))


def test_title_too_short() -> None:
    r = _result(_make_page(title="Short"))
    assert RULE_TITLE_TOO_SHORT.rule_id in _ids(analyze_tech_meta(r))


def test_title_too_long() -> None:
    r = _result(_make_page(title="x" * 200))
    assert RULE_TITLE_TOO_LONG.rule_id in _ids(analyze_tech_meta(r))


def test_title_duplicate() -> None:
    p1 = _make_page(url="https://example.com/a", title="Identical title for two pages here")
    p2 = _make_page(url="https://example.com/b", title="Identical title for two pages here")
    findings = analyze_tech_meta(_result(p1, p2))
    dupe = [f for f in findings if f.rule_id == RULE_TITLE_DUPLICATE.rule_id]
    assert len(dupe) == 2  # one finding per page


# --- meta description ---


def test_meta_desc_missing() -> None:
    r = _result(_make_page(meta_description=None))
    assert RULE_META_DESC_MISSING.rule_id in _ids(analyze_tech_meta(r))


def test_meta_desc_duplicate() -> None:
    same = "Sufficiently long meta description that is identical across two pages here for sure."
    p1 = _make_page(url="https://example.com/a", meta_description=same)
    p2 = _make_page(url="https://example.com/b", meta_description=same)
    ids = _ids(analyze_tech_meta(_result(p1, p2)))
    assert ids.count(RULE_META_DESC_DUPLICATE.rule_id) == 2


# --- H1 ---


def test_h1_missing() -> None:
    r = _result(_make_page(h1=None, h1_count=0))
    assert RULE_H1_MISSING.rule_id in _ids(analyze_tech_meta(r))


def test_h1_multiple() -> None:
    r = _result(_make_page(h1_count=3))
    assert RULE_H1_MULTIPLE.rule_id in _ids(analyze_tech_meta(r))


# --- images ---


def test_image_missing_alt() -> None:
    images = [ExtractedImage(src="/a.png", alt=None), ExtractedImage(src="/b.png", alt="x")]
    r = _result(_make_page(images=images))
    findings = [f for f in analyze_tech_meta(r) if f.rule_id == RULE_IMG_ALT_MISSING.rule_id]
    assert len(findings) == 1
    assert findings[0].payload["count"] == 1


def test_image_all_alt_no_finding() -> None:
    images = [ExtractedImage(src="/a.png", alt="alt")]
    r = _result(_make_page(images=images))
    assert RULE_IMG_ALT_MISSING.rule_id not in _ids(analyze_tech_meta(r))


# --- response time ---


def test_response_medium() -> None:
    r = _result(_make_page(response_ms=900))
    assert RULE_RESPONSE_MEDIUM.rule_id in _ids(analyze_tech_meta(r))


def test_response_slow() -> None:
    r = _result(_make_page(response_ms=2500))
    assert RULE_RESPONSE_SLOW.rule_id in _ids(analyze_tech_meta(r))


def test_response_fast_no_finding() -> None:
    r = _result(_make_page(response_ms=80))
    ids = _ids(analyze_tech_meta(r))
    assert RULE_RESPONSE_MEDIUM.rule_id not in ids
    assert RULE_RESPONSE_SLOW.rule_id not in ids


# --- language / html size / robots ---


def test_language_missing() -> None:
    r = _result(_make_page(language=None))
    assert RULE_LANG_MISSING.rule_id in _ids(analyze_tech_meta(r))


def test_html_too_large() -> None:
    r = _result(_make_page(html_size=2_000_000))
    assert RULE_HTML_TOO_LARGE.rule_id in _ids(analyze_tech_meta(r))


def test_noindex_emits_tip() -> None:
    r = _result(_make_page(meta_robots="noindex,follow"))
    assert RULE_PAGE_NOINDEX.rule_id in _ids(analyze_tech_meta(r))


# --- url hygiene ---


def test_url_too_long() -> None:
    long_url = "https://example.com/" + "a" * 200
    r = _result(_make_page(url=long_url))
    assert RULE_URL_TOO_LONG.rule_id in _ids(analyze_tech_meta(r))


def test_url_too_deep() -> None:
    r = _result(_make_page(url="https://example.com/a/b/c/d/e/f"))
    assert RULE_URL_TOO_DEEP.rule_id in _ids(analyze_tech_meta(r))


def test_url_session() -> None:
    r = _result(_make_page(url="https://example.com/x?phpsessid=abc"))
    ids = _ids(analyze_tech_meta(r))
    assert RULE_URL_SESSION.rule_id in ids
    assert RULE_URL_DYNAMIC.rule_id not in ids  # session takes precedence


def test_url_dynamic_only() -> None:
    r = _result(_make_page(url="https://example.com/x?utm=foo"))
    assert RULE_URL_DYNAMIC.rule_id in _ids(analyze_tech_meta(r))


# --- fetch errors ---


def test_fetch_failed_short_circuits() -> None:
    r = _result(_make_page(fetch_error="ConnectError: boom"))
    findings = analyze_tech_meta(r)
    ids = _ids(findings)
    assert RULE_PAGE_FETCH_FAILED.rule_id in ids
    # No HTML rules should fire when fetch failed
    assert RULE_TITLE_MISSING.rule_id not in ids


def test_http_error_emits_finding() -> None:
    r = _result(_make_page(status=404))
    assert RULE_PAGE_HTTP_ERROR.rule_id in _ids(analyze_tech_meta(r))


def test_clean_page_no_findings() -> None:
    r = _result(
        _make_page(
            url="https://example.com/clean",
            images=[ExtractedImage(src="/x.png", alt="x")],
        )
    )
    ids = _ids(analyze_tech_meta(r))
    assert ids == [], f"unexpected findings on clean page: {ids}"
