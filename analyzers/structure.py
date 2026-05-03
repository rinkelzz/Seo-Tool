"""Structure analyzer rules.

Mirrors the "Struktur" section of the Seobility export:
- click depth from start page (>= 3 hops is a tip)
- internal in-link / out-link distribution (orphans, dead-end pages,
  pages with too many outgoing links)
- anchor-text consistency (same anchor → different targets, generic anchors)
- canonical hygiene (cross-domain, mismatch, chain)
- redirect chains and loops
- external link health (broken, unreachable) — only fires after the external
  status checker has populated ``external_statuses``

Findings work on the raw ``CrawlResult`` only; the worker turns them into
``Issue`` rows.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from analyzers.base import Finding, FindingCategory, FindingSeverity, Rule, registry
from crawler.engine import CrawlResult
from crawler.urls import host_of, is_same_site

CATEGORY = FindingCategory.STRUCTURE

# ---- thresholds -----------------------------------------------------------

DEPTH_TIP = 3  # depth >= this gets a tip ("hard to reach from start")
DEPTH_IMPORTANT = 5  # depth >= this gets bumped to important
OUTLINKS_MANY = 100  # > this many outgoing links per page is a tip
REDIRECT_CHAIN_LONG = 2  # more than 2 hops is a long chain

# Generic / unhelpful anchor texts. German + English defaults.
GENERIC_ANCHORS: frozenset[str] = frozenset(
    {
        "hier",
        "klick",
        "klicken",
        "klick hier",
        "hier klicken",
        "mehr",
        "mehr lesen",
        "weiterlesen",
        "weiter",
        "mehr erfahren",
        "click",
        "click here",
        "here",
        "more",
        "read more",
        "learn more",
        "link",
        "this",
        "this link",
    }
)


# ---- rule registry --------------------------------------------------------


def _r(rule_id: str, severity: FindingSeverity, description: str, weight: float = 1.0) -> Rule:
    return registry.register(
        Rule(
            rule_id=rule_id,
            category=CATEGORY,
            severity=severity,
            description=description,
            weight=weight,
        )
    )


RULE_DEPTH_DEEP = _r(
    "structure.depth.deep",
    FindingSeverity.TIP,
    "Page is several clicks away from the start page",
    0.5,
)
RULE_DEPTH_VERY_DEEP = _r(
    "structure.depth.very_deep",
    FindingSeverity.IMPORTANT,
    "Page is hard to reach from the start page",
    1.0,
)
RULE_INLINKS_NONE = _r(
    "structure.inlinks.none",
    FindingSeverity.IMPORTANT,
    "Orphan page with no internal incoming links",
    1.5,
)
RULE_OUTLINKS_NONE = _r(
    "structure.outlinks.none",
    FindingSeverity.TIP,
    "Page has no outgoing links",
    0.5,
)
RULE_OUTLINKS_MANY = _r(
    "structure.outlinks.many",
    FindingSeverity.TIP,
    "Page has very many outgoing links",
    0.5,
)
RULE_ANCHOR_GENERIC = _r(
    "structure.anchor.generic",
    FindingSeverity.TIP,
    "Generic anchor text (e.g. 'click here', 'mehr')",
    0.5,
)
RULE_ANCHOR_AMBIGUOUS = _r(
    "structure.anchor.ambiguous",
    FindingSeverity.IMPORTANT,
    "Same anchor text used for different target URLs",
    1.0,
)
RULE_CANONICAL_CROSS_DOMAIN = _r(
    "structure.canonical.cross_domain",
    FindingSeverity.IMPORTANT,
    "Canonical points to a different domain",
    1.5,
)
RULE_CANONICAL_MISMATCH = _r(
    "structure.canonical.mismatch",
    FindingSeverity.TIP,
    "Canonical URL differs from page URL",
    0.5,
)
RULE_REDIRECT_LONG_CHAIN = _r(
    "structure.redirect.long_chain",
    FindingSeverity.IMPORTANT,
    "Redirect chain longer than two hops",
    1.0,
)
RULE_REDIRECT_LOOP = _r(
    "structure.redirect.loop",
    FindingSeverity.CRITICAL,
    "Redirect returns to a URL already visited in the chain",
    2.0,
)
RULE_EXTERNAL_LINK_BROKEN = _r(
    "structure.external_link.broken",
    FindingSeverity.IMPORTANT,
    "External link returns an HTTP error",
    1.0,
)
RULE_EXTERNAL_LINK_UNREACHABLE = _r(
    "structure.external_link.unreachable",
    FindingSeverity.IMPORTANT,
    "External link is unreachable (timeout / DNS / connection error)",
    1.0,
)
RULE_SITEMAP_URL_NOT_CRAWLED = _r(
    "structure.sitemap.in_sitemap_only",
    FindingSeverity.IMPORTANT,
    "URL declared in sitemap but not reached by the crawl",
    1.0,
)
RULE_PAGE_NOT_IN_SITEMAP = _r(
    "structure.sitemap.in_crawl_only",
    FindingSeverity.TIP,
    "Page reached by the crawl but missing from sitemap",
    0.5,
)

STRUCTURE_RULES: list[Rule] = registry.by_category(CATEGORY)


# ---- analyzer entry point -------------------------------------------------


@dataclass
class _Graph:
    """Pre-computed link statistics over the crawl, indexed by source page URL."""

    incoming: dict[str, set[str]]  # page url → set of source page urls
    outgoing: dict[str, list[tuple[str, str]]]  # page url → [(target_url, anchor)]
    same_site_pages: set[str]  # all crawled HTML page URLs (used for orphan detection)
    start_pages: set[str]  # pages reached at depth 0 — exempt from orphan check


def analyze_structure(
    crawl: CrawlResult,
    *,
    base_url: str,
    external_statuses: dict[str, int | None] | None = None,
    sitemap_urls: set[str] | None = None,
) -> list[Finding]:
    """Run all structure rules against a completed crawl.

    Args:
        crawl: result from ``crawler.run_crawl``
        base_url: project base URL — used for canonical/cross-domain comparisons
        external_statuses: optional ``target_url → status_code`` map produced by
            the external link checker. ``None`` status means the request failed.
            If omitted, broken/unreachable external-link findings are skipped.
        sitemap_urls: optional set of URLs declared in the project's sitemaps.
            When supplied, the analyzer emits findings for URLs in the sitemap
            that the crawl missed and for crawled pages absent from the sitemap.
    """
    graph = _build_graph(crawl)
    findings: list[Finding] = []

    findings.extend(_depth_findings(crawl))
    findings.extend(_inlink_findings(graph))
    findings.extend(_outlink_findings(graph))
    findings.extend(_anchor_findings(graph))
    findings.extend(_canonical_findings(crawl, base_url=base_url))
    findings.extend(_redirect_findings(crawl))
    if external_statuses is not None:
        findings.extend(_external_link_findings(graph, external_statuses))
    if sitemap_urls is not None:
        findings.extend(_sitemap_diff_findings(graph, sitemap_urls, base_url=base_url))
    return findings


# ---- helpers --------------------------------------------------------------


def _build_graph(crawl: CrawlResult) -> _Graph:
    incoming: dict[str, set[str]] = defaultdict(set)
    outgoing: dict[str, list[tuple[str, str]]] = defaultdict(list)
    same_site_pages: set[str] = set()
    start_pages: set[str] = set()

    for cp in crawl.html_pages():
        page_url = cp.fetch.final_url
        same_site_pages.add(page_url)
        if cp.depth == 0:
            start_pages.add(page_url)
        pd = cp.page_data
        if pd is None:
            continue
        for link in pd.links:
            outgoing[page_url].append((link.target_url, link.anchor_text))
            if link.is_internal:
                incoming[link.target_url].add(page_url)

    return _Graph(
        incoming=incoming,
        outgoing=outgoing,
        same_site_pages=same_site_pages,
        start_pages=start_pages,
    )


def _depth_findings(crawl: CrawlResult) -> list[Finding]:
    out: list[Finding] = []
    for cp in crawl.html_pages():
        depth = cp.depth
        if depth >= DEPTH_IMPORTANT:
            out.append(
                _finding(
                    RULE_DEPTH_VERY_DEEP,
                    cp.fetch.final_url,
                    {"depth": depth, "threshold": DEPTH_IMPORTANT},
                )
            )
        elif depth >= DEPTH_TIP:
            out.append(
                _finding(
                    RULE_DEPTH_DEEP,
                    cp.fetch.final_url,
                    {"depth": depth, "threshold": DEPTH_TIP},
                )
            )
    return out


def _inlink_findings(graph: _Graph) -> list[Finding]:
    """Pages crawled but with no internal incoming link are orphans.

    The start page (``depth == 0``) is exempt — it has no inlinks by definition.
    """
    out: list[Finding] = []
    for page_url in graph.same_site_pages:
        if page_url in graph.start_pages:
            continue
        if not graph.incoming.get(page_url):
            out.append(_finding(RULE_INLINKS_NONE, page_url, {}))
    return out


def _outlink_findings(graph: _Graph) -> list[Finding]:
    out: list[Finding] = []
    for page_url in graph.same_site_pages:
        outs = graph.outgoing.get(page_url, [])
        if not outs:
            out.append(_finding(RULE_OUTLINKS_NONE, page_url, {}))
        elif len(outs) > OUTLINKS_MANY:
            out.append(
                _finding(
                    RULE_OUTLINKS_MANY,
                    page_url,
                    {"count": len(outs), "threshold": OUTLINKS_MANY},
                )
            )
    return out


def _anchor_findings(graph: _Graph) -> list[Finding]:
    """Two checks:
    1. Generic anchors (hier, klick, click here, …)
    2. Same anchor text → different target URLs (ambiguous linking)
    """
    out: list[Finding] = []
    # Aggregate anchor → set of distinct targets across the whole crawl.
    anchor_to_targets: dict[str, set[str]] = defaultdict(set)
    anchor_to_sources: dict[str, set[str]] = defaultdict(set)
    for source_url, edges in graph.outgoing.items():
        for target, anchor in edges:
            normalized = anchor.strip().lower()
            if not normalized:
                continue
            if normalized in GENERIC_ANCHORS:
                out.append(
                    _finding(
                        RULE_ANCHOR_GENERIC,
                        source_url,
                        {"anchor": anchor.strip(), "target": target},
                    )
                )
            anchor_to_targets[normalized].add(target)
            anchor_to_sources[normalized].add(source_url)

    for anchor, targets in anchor_to_targets.items():
        if len(targets) > 1:
            for source in anchor_to_sources[anchor]:
                out.append(
                    _finding(
                        RULE_ANCHOR_AMBIGUOUS,
                        source,
                        {"anchor": anchor, "targets": sorted(targets)[:5]},
                    )
                )
    return out


def _canonical_findings(crawl: CrawlResult, *, base_url: str) -> list[Finding]:
    out: list[Finding] = []
    for cp in crawl.html_pages():
        pd = cp.page_data
        if pd is None or not pd.canonical_url:
            continue
        canonical = pd.canonical_url
        page_url = cp.fetch.final_url
        if canonical == page_url:
            continue
        if not is_same_site(canonical, base_url):
            out.append(
                _finding(
                    RULE_CANONICAL_CROSS_DOMAIN,
                    page_url,
                    {"canonical": canonical, "canonical_host": host_of(canonical)},
                )
            )
        else:
            out.append(
                _finding(
                    RULE_CANONICAL_MISMATCH,
                    page_url,
                    {"canonical": canonical},
                )
            )
    return out


def _redirect_findings(crawl: CrawlResult) -> list[Finding]:
    out: list[Finding] = []
    for cp in crawl.pages:
        chain = cp.fetch.redirect_chain
        if not chain:
            continue
        page_url = cp.fetch.final_url
        # Loop detection: same URL appears more than once (incl. final URL)
        seen: set[str] = set()
        looped = False
        for hop in [*chain, page_url]:
            if hop in seen:
                looped = True
                break
            seen.add(hop)
        if looped:
            out.append(
                _finding(
                    RULE_REDIRECT_LOOP,
                    page_url,
                    {"chain": [*chain, page_url]},
                )
            )
            continue
        if len(chain) > REDIRECT_CHAIN_LONG:
            out.append(
                _finding(
                    RULE_REDIRECT_LONG_CHAIN,
                    page_url,
                    {"hops": len(chain), "chain": chain},
                )
            )
    return out


def _external_link_findings(graph: _Graph, statuses: dict[str, int | None]) -> list[Finding]:
    """Emit one finding per (source_page, broken_target) pair.

    ``statuses`` maps target URL → HTTP status code (None means the request
    couldn't complete at all — DNS error, timeout, connection refused).
    """
    out: list[Finding] = []
    for source_url, edges in graph.outgoing.items():
        for target, _anchor in edges:
            if target not in statuses:
                continue
            status = statuses[target]
            if status is None:
                out.append(
                    _finding(
                        RULE_EXTERNAL_LINK_UNREACHABLE,
                        source_url,
                        {"target": target},
                    )
                )
            elif status >= 400:
                out.append(
                    _finding(
                        RULE_EXTERNAL_LINK_BROKEN,
                        source_url,
                        {"target": target, "status_code": status},
                    )
                )
    return out


def _sitemap_diff_findings(
    graph: _Graph, sitemap_urls: set[str], *, base_url: str
) -> list[Finding]:
    """Compare crawled pages against the union of sitemap URLs.

    Two complementary findings:
    - URLs in the sitemap but never reached by the crawl (the more important
      direction — typically means broken internal linking or that the page
      isn't actually reachable from the start URL).
    - Pages reached by the crawl but absent from the sitemap (lower severity;
      common for paginated archives, filter combinations, search result pages).

    External-host URLs in the sitemap (e.g. canonical CDN URLs) are ignored
    because the crawler doesn't follow off-site links anyway.
    """
    out: list[Finding] = []
    crawled = graph.same_site_pages
    same_site_sitemap = {u for u in sitemap_urls if is_same_site(u, base_url)}

    for sitemap_url in same_site_sitemap - crawled:
        out.append(_finding(RULE_SITEMAP_URL_NOT_CRAWLED, sitemap_url, {}))

    for crawled_url in crawled - same_site_sitemap:
        out.append(_finding(RULE_PAGE_NOT_IN_SITEMAP, crawled_url, {}))

    return out


def _finding(rule: Rule, url: str | None, payload: dict) -> Finding:  # type: ignore[type-arg]
    return Finding(
        rule_id=rule.rule_id,
        category=rule.category,
        severity=rule.severity,
        page_url=url,
        payload=payload,
    )
