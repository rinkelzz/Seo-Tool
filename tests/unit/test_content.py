"""Content-analyzer tests.

Builds synthetic ``CrawlResult`` objects with pre-extracted ``main_text`` and
``content_blocks`` so we don't depend on trafilatura's quirks here.
"""

from __future__ import annotations

from analyzers.content import (
    BLOCK_REPEAT_THRESHOLD,
    NEAR_DUPLICATE_THRESHOLD,
    RULE_BLOCK_REPEATED,
    RULE_CANNIBALIZATION,
    RULE_DUPLICATE_PAGE,
    RULE_H1_KEYWORD_MISSING,
    RULE_NEAR_DUPLICATE_PAGE,
    RULE_THIN_CONTENT,
    RULE_TITLE_KEYWORD_MISSING,
    THIN_CONTENT_MIN_WORDS,
    analyze_content,
)
from crawler.engine import CrawledPage, CrawlResult
from crawler.extract import PageData
from crawler.fetcher import FetchResult


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


def _make_page(
    *,
    url: str = "https://example.com/p",
    title: str | None = "Example",
    h1: str | None = "Heading",
    main_text: str | None = None,
    content_blocks: list[str] | None = None,
) -> CrawledPage:
    blocks = content_blocks or []
    text = main_text if main_text is not None else " ".join(blocks)
    pd = PageData(
        url=url,
        content_hash="x" * 64,
        html_size=1000,
        title=title,
        meta_description="Description",
        meta_robots=None,
        canonical_url=None,
        language="de",
        h1=h1,
        h1_count=1 if h1 else 0,
        word_count=len(text.split()),
        text_excerpt=text[:500],
        main_text=text or None,
        main_word_count=len(text.split()) if text else 0,
        content_blocks=blocks,
        images=[],
        links=[],
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


def _long_text(seed: str, words: int = 200) -> str:
    """Build a chunk of text that's long enough to dodge thin/duplicate-min thresholds."""
    return " ".join([seed] * words)


# --- thin content ---


def test_thin_content_flagged() -> None:
    p = _make_page(main_text="Just a few words here.")
    ids = _ids(analyze_content(_result(p)))
    assert RULE_THIN_CONTENT.rule_id in ids


def test_long_content_not_thin() -> None:
    p = _make_page(main_text=_long_text("wort", words=THIN_CONTENT_MIN_WORDS + 10))
    ids = _ids(analyze_content(_result(p)))
    assert RULE_THIN_CONTENT.rule_id not in ids


# --- exact duplicates ---


def test_exact_duplicate_pages_flagged_on_both() -> None:
    text = _long_text("foo", words=80)
    p1 = _make_page(url="https://example.com/a", main_text=text)
    p2 = _make_page(url="https://example.com/b", main_text=text)
    findings = analyze_content(_result(p1, p2))
    dupe = [f for f in findings if f.rule_id == RULE_DUPLICATE_PAGE.rule_id]
    assert len(dupe) == 2
    urls = {f.page_url for f in dupe}
    assert urls == {"https://example.com/a", "https://example.com/b"}


def test_short_pages_skipped_by_duplicate_check() -> None:
    text = "Two pages with very identical short text."
    p1 = _make_page(url="https://example.com/a", main_text=text)
    p2 = _make_page(url="https://example.com/b", main_text=text)
    ids = _ids(analyze_content(_result(p1, p2)))
    assert RULE_DUPLICATE_PAGE.rule_id not in ids
    assert RULE_NEAR_DUPLICATE_PAGE.rule_id not in ids


# --- near duplicates ---


def test_near_duplicate_pages_flagged() -> None:
    base = " ".join(f"sentence number {i}" for i in range(80))
    # Slight tweak — append/prepend a few words but keep most shingles identical
    near = base + " plus an extra closing sentence with some words"
    p1 = _make_page(url="https://example.com/a", main_text=base)
    p2 = _make_page(url="https://example.com/b", main_text=near)
    findings = analyze_content(_result(p1, p2))
    near_findings = [f for f in findings if f.rule_id == RULE_NEAR_DUPLICATE_PAGE.rule_id]
    assert len(near_findings) == 2
    payload = near_findings[0].payload
    assert payload["similarity"] >= NEAR_DUPLICATE_THRESHOLD


def test_distinct_pages_no_duplicate_finding() -> None:
    p1 = _make_page(
        url="https://example.com/a",
        main_text=_long_text("apple", words=80),
    )
    p2 = _make_page(
        url="https://example.com/b",
        main_text=_long_text("banana", words=80),
    )
    ids = _ids(analyze_content(_result(p1, p2)))
    assert RULE_DUPLICATE_PAGE.rule_id not in ids
    assert RULE_NEAR_DUPLICATE_PAGE.rule_id not in ids


def test_exact_takes_precedence_over_near() -> None:
    text = _long_text("xenon", words=80)
    p1 = _make_page(url="https://example.com/a", main_text=text)
    p2 = _make_page(url="https://example.com/b", main_text=text)
    findings = analyze_content(_result(p1, p2))
    near = [f for f in findings if f.rule_id == RULE_NEAR_DUPLICATE_PAGE.rule_id]
    assert near == []  # only exact duplicate findings, no near-dup noise


# --- block repetition ---


def test_block_repeated_across_many_pages() -> None:
    repeated = "Diese Box steht im Footer und kommt auf jeder Seite vor."
    pages = [
        _make_page(
            url=f"https://example.com/{i}",
            content_blocks=[
                f"Eindeutiger Inhalt fuer Seite {i} mit ausreichend vielen Woertern hier.",
                repeated,
            ],
        )
        for i in range(BLOCK_REPEAT_THRESHOLD + 1)
    ]
    findings = analyze_content(_result(*pages))
    block_findings = [f for f in findings if f.rule_id == RULE_BLOCK_REPEATED.rule_id]
    # one finding per page that contains the repeated block
    assert len(block_findings) == BLOCK_REPEAT_THRESHOLD + 1


def test_block_appearing_twice_not_flagged() -> None:
    repeated = "Nur auf zwei Seiten gemeinsamer Block."
    p1 = _make_page(
        url="https://example.com/a",
        content_blocks=["Einzigartig Seite a", repeated],
    )
    p2 = _make_page(
        url="https://example.com/b",
        content_blocks=["Einzigartig Seite b", repeated],
    )
    ids = _ids(analyze_content(_result(p1, p2)))
    assert RULE_BLOCK_REPEATED.rule_id not in ids


# --- keyword in body ---


def test_title_keyword_missing_in_body() -> None:
    p = _make_page(
        title="Spezialprodukt Premium Edition",
        h1="Heading",
        main_text=_long_text("ganz andere woerter und themen", words=50),
    )
    ids = _ids(analyze_content(_result(p)))
    assert RULE_TITLE_KEYWORD_MISSING.rule_id in ids


def test_title_keyword_present_in_body() -> None:
    p = _make_page(
        title="Spezialprodukt Premium Edition",
        h1="Heading",
        main_text="Unser Spezialprodukt ist hervorragend. " * 30,
    )
    ids = _ids(analyze_content(_result(p)))
    assert RULE_TITLE_KEYWORD_MISSING.rule_id not in ids


def test_h1_keyword_missing_in_body_separate_finding() -> None:
    p = _make_page(
        title="completely irrelevant",
        h1="Marketingaktion sehr besonders",
        main_text=_long_text("voellig anderer textblock hier nochmal", words=50),
    )
    ids = _ids(analyze_content(_result(p)))
    # h1 keyword (not the same as title) should be reported separately
    assert RULE_H1_KEYWORD_MISSING.rule_id in ids


# --- cannibalization ---


def test_cannibalization_when_multiple_pages_share_top_keyword() -> None:
    p1 = _make_page(
        url="https://example.com/a",
        main_text=("nachhaltigkeit produkt umwelt bio recycling klima " * 30),
    )
    p2 = _make_page(
        url="https://example.com/b",
        main_text=("nachhaltigkeit lieferung umwelt versand klima energie " * 30),
    )
    findings = analyze_content(_result(p1, p2))
    cann = [f for f in findings if f.rule_id == RULE_CANNIBALIZATION.rule_id]
    assert len(cann) >= 2  # both pages flagged
    # Same keyword appears in both findings
    keywords = {f.payload["keyword"] for f in cann}
    assert "nachhaltigkeit" in keywords or "umwelt" in keywords or "klima" in keywords


def test_no_cannibalization_when_pages_use_distinct_topics() -> None:
    p1 = _make_page(
        url="https://example.com/a",
        main_text=("photovoltaik solar wechselrichter speicher kilowattstunde " * 30),
    )
    p2 = _make_page(
        url="https://example.com/b",
        main_text=("haftpflicht versicherung beitrag leistung tarif schaden " * 30),
    )
    ids = _ids(analyze_content(_result(p1, p2)))
    assert RULE_CANNIBALIZATION.rule_id not in ids


def test_single_page_no_cannibalization() -> None:
    p = _make_page(main_text=_long_text("solo content here", words=80))
    ids = _ids(analyze_content(_result(p)))
    assert RULE_CANNIBALIZATION.rule_id not in ids


def test_pages_without_main_text_are_skipped() -> None:
    p = _make_page(url="https://example.com/x", main_text=None, content_blocks=[])
    findings = analyze_content(_result(p))
    # No content findings should fire — there's nothing to analyze
    assert findings == []
