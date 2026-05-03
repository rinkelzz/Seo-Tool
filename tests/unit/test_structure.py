"""Structure-analyzer tests.

Builds synthetic ``CrawlResult`` objects directly so we don't need real HTTP.
"""

from __future__ import annotations

from analyzers.structure import (
    OUTLINKS_MANY,
    RULE_ANCHOR_AMBIGUOUS,
    RULE_ANCHOR_GENERIC,
    RULE_CANONICAL_CROSS_DOMAIN,
    RULE_CANONICAL_MISMATCH,
    RULE_DEPTH_DEEP,
    RULE_DEPTH_VERY_DEEP,
    RULE_EXTERNAL_LINK_BROKEN,
    RULE_EXTERNAL_LINK_UNREACHABLE,
    RULE_INLINKS_NONE,
    RULE_OUTLINKS_MANY,
    RULE_OUTLINKS_NONE,
    RULE_REDIRECT_LONG_CHAIN,
    RULE_REDIRECT_LOOP,
    analyze_structure,
)
from crawler.engine import CrawledPage, CrawlResult
from crawler.extract import ExtractedLink, PageData
from crawler.fetcher import FetchResult

BASE = "https://example.com/"


def _ok_fetch(url: str, *, redirect_chain: list[str] | None = None) -> FetchResult:
    return FetchResult(
        url=redirect_chain[0] if redirect_chain else url,
        final_url=url,
        status_code=200,
        response_time_ms=100,
        content_type="text/html",
        body=b"<html></html>",
        encoding="utf-8",
        redirect_chain=redirect_chain or [],
    )


def _make_page(
    *,
    url: str = "https://example.com/p",
    depth: int = 0,
    canonical: str | None = None,
    links: list[tuple[str, str, bool]] | None = None,  # (target, anchor, is_internal)
    redirect_chain: list[str] | None = None,
) -> CrawledPage:
    extracted_links = [
        ExtractedLink(target_url=t, anchor_text=a, rel=None, is_internal=i, is_followed=True)
        for (t, a, i) in (links or [])
    ]
    pd = PageData(
        url=url,
        content_hash="x" * 64,
        html_size=1000,
        title="Title",
        meta_description="Description",
        meta_robots=None,
        canonical_url=canonical,
        language="de",
        h1="Heading",
        h1_count=1,
        word_count=100,
        text_excerpt="",
        images=[],
        links=extracted_links,
    )
    return CrawledPage(
        fetch=_ok_fetch(url, redirect_chain=redirect_chain), page_data=pd, depth=depth
    )


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


# --- depth ---


def test_depth_tip_at_three() -> None:
    p = _make_page(url="https://example.com/x", depth=3)
    ids = _ids(analyze_structure(_result(p), base_url=BASE))
    assert RULE_DEPTH_DEEP.rule_id in ids
    assert RULE_DEPTH_VERY_DEEP.rule_id not in ids


def test_depth_important_at_five() -> None:
    p = _make_page(url="https://example.com/x", depth=5)
    ids = _ids(analyze_structure(_result(p), base_url=BASE))
    assert RULE_DEPTH_VERY_DEEP.rule_id in ids
    assert RULE_DEPTH_DEEP.rule_id not in ids


def test_depth_one_no_finding() -> None:
    p = _make_page(url="https://example.com/x", depth=1)
    ids = _ids(analyze_structure(_result(p), base_url=BASE))
    assert RULE_DEPTH_DEEP.rule_id not in ids
    assert RULE_DEPTH_VERY_DEEP.rule_id not in ids


# --- inlinks (orphan detection) ---


def test_orphan_page_detected() -> None:
    # / links to /a, /b is orphan (in same_site_pages but no inlinks; / is exempt because it's the only no-inlink-with-outlinks page)
    home = _make_page(
        url="https://example.com/",
        depth=0,
        links=[("https://example.com/a", "a", True)],
    )
    a = _make_page(url="https://example.com/a", depth=1, links=[])
    orphan = _make_page(
        url="https://example.com/b",
        depth=2,
        links=[("https://example.com/", "back", True)],
    )
    findings = analyze_structure(_result(home, a, orphan), base_url=BASE)
    orphans = [f for f in findings if f.rule_id == RULE_INLINKS_NONE.rule_id]
    assert len(orphans) == 1
    assert orphans[0].page_url == "https://example.com/b"


def test_single_page_site_no_orphan() -> None:
    home = _make_page(url="https://example.com/", depth=0, links=[])
    findings = analyze_structure(_result(home), base_url=BASE)
    assert RULE_INLINKS_NONE.rule_id not in _ids(findings)


# --- outlinks ---


def test_outlinks_none() -> None:
    p = _make_page(url="https://example.com/", links=[])
    ids = _ids(analyze_structure(_result(p), base_url=BASE))
    assert RULE_OUTLINKS_NONE.rule_id in ids


def test_outlinks_many() -> None:
    too_many = [(f"https://example.com/{i}", str(i), True) for i in range(OUTLINKS_MANY + 5)]
    p = _make_page(url="https://example.com/", links=too_many)
    ids = _ids(analyze_structure(_result(p), base_url=BASE))
    assert RULE_OUTLINKS_MANY.rule_id in ids


# --- anchors ---


def test_generic_anchor_flagged() -> None:
    p = _make_page(
        url="https://example.com/",
        links=[("https://example.com/a", "hier klicken", True)],
    )
    ids = _ids(analyze_structure(_result(p), base_url=BASE))
    assert RULE_ANCHOR_GENERIC.rule_id in ids


def test_specific_anchor_not_flagged() -> None:
    p = _make_page(
        url="https://example.com/",
        links=[("https://example.com/a", "Über uns", True)],
    )
    ids = _ids(analyze_structure(_result(p), base_url=BASE))
    assert RULE_ANCHOR_GENERIC.rule_id not in ids


def test_ambiguous_anchor_flagged() -> None:
    # Same anchor "Mehr Info" pointing to two distinct targets across pages
    p1 = _make_page(
        url="https://example.com/a",
        links=[("https://example.com/x", "Mehr Info", True)],
    )
    p2 = _make_page(
        url="https://example.com/b",
        links=[("https://example.com/y", "Mehr Info", True)],
    )
    findings = analyze_structure(_result(p1, p2), base_url=BASE)
    ambiguous = [f for f in findings if f.rule_id == RULE_ANCHOR_AMBIGUOUS.rule_id]
    assert len(ambiguous) == 2  # one per source page


# --- canonical ---


def test_canonical_self_no_finding() -> None:
    p = _make_page(url="https://example.com/x", canonical="https://example.com/x")
    ids = _ids(analyze_structure(_result(p), base_url=BASE))
    assert RULE_CANONICAL_MISMATCH.rule_id not in ids
    assert RULE_CANONICAL_CROSS_DOMAIN.rule_id not in ids


def test_canonical_mismatch_same_domain() -> None:
    p = _make_page(url="https://example.com/x", canonical="https://example.com/y")
    ids = _ids(analyze_structure(_result(p), base_url=BASE))
    assert RULE_CANONICAL_MISMATCH.rule_id in ids


def test_canonical_cross_domain() -> None:
    p = _make_page(url="https://example.com/x", canonical="https://other.com/x")
    ids = _ids(analyze_structure(_result(p), base_url=BASE))
    assert RULE_CANONICAL_CROSS_DOMAIN.rule_id in ids


# --- redirect chains ---


def test_long_redirect_chain() -> None:
    # 3 hops counts as long (REDIRECT_CHAIN_LONG = 2)
    chain = [
        "https://example.com/a",
        "https://example.com/b",
        "https://example.com/c",
    ]
    p = _make_page(url="https://example.com/d", redirect_chain=chain)
    ids = _ids(analyze_structure(_result(p), base_url=BASE))
    assert RULE_REDIRECT_LONG_CHAIN.rule_id in ids


def test_short_redirect_chain_not_flagged() -> None:
    p = _make_page(url="https://example.com/b", redirect_chain=["https://example.com/a"])
    ids = _ids(analyze_structure(_result(p), base_url=BASE))
    assert RULE_REDIRECT_LONG_CHAIN.rule_id not in ids


def test_redirect_loop_detected() -> None:
    # /a → /b → /a (loop)
    chain = ["https://example.com/a", "https://example.com/b"]
    p = _make_page(url="https://example.com/a", redirect_chain=chain)
    ids = _ids(analyze_structure(_result(p), base_url=BASE))
    assert RULE_REDIRECT_LOOP.rule_id in ids
    # When a loop is detected, we don't also emit "long chain"
    assert RULE_REDIRECT_LONG_CHAIN.rule_id not in ids


# --- external link checks ---


def test_external_broken_flagged() -> None:
    p = _make_page(
        url="https://example.com/",
        links=[("https://other.com/dead", "ext", False)],
    )
    statuses = {"https://other.com/dead": 404}
    findings = analyze_structure(_result(p), base_url=BASE, external_statuses=statuses)
    ids = _ids(findings)
    assert RULE_EXTERNAL_LINK_BROKEN.rule_id in ids


def test_external_unreachable_flagged() -> None:
    p = _make_page(
        url="https://example.com/",
        links=[("https://other.com/x", "ext", False)],
    )
    statuses: dict[str, int | None] = {"https://other.com/x": None}
    findings = analyze_structure(_result(p), base_url=BASE, external_statuses=statuses)
    ids = _ids(findings)
    assert RULE_EXTERNAL_LINK_UNREACHABLE.rule_id in ids


def test_external_ok_no_finding() -> None:
    p = _make_page(
        url="https://example.com/",
        links=[("https://other.com/ok", "ext", False)],
    )
    statuses = {"https://other.com/ok": 200}
    findings = analyze_structure(_result(p), base_url=BASE, external_statuses=statuses)
    ids = _ids(findings)
    assert RULE_EXTERNAL_LINK_BROKEN.rule_id not in ids
    assert RULE_EXTERNAL_LINK_UNREACHABLE.rule_id not in ids


def test_external_check_skipped_without_statuses() -> None:
    p = _make_page(
        url="https://example.com/",
        links=[("https://other.com/x", "ext", False)],
    )
    findings = analyze_structure(_result(p), base_url=BASE, external_statuses=None)
    ids = _ids(findings)
    assert RULE_EXTERNAL_LINK_BROKEN.rule_id not in ids
    assert RULE_EXTERNAL_LINK_UNREACHABLE.rule_id not in ids
