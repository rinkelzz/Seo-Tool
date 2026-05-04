"""Tech & Meta analyzer rules.

Mirrors the "Technik & Meta" section of the Seobility export:
- title problems (missing / empty / too short / too long / duplicate)
- meta description problems (missing / too long / duplicate)
- H1 problems (missing / multiple)
- alt-attribute coverage
- response-time bucketing
- charset / language declarations
- URL hygiene (dynamic params, session ids, depth, length)
- HTML size guard

Each finding maps 1:1 to an ``Issue`` row (the worker handles persistence).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from analyzers.base import Finding, FindingCategory, FindingSeverity, Rule, registry
from crawler.engine import CrawledPage, CrawlResult
from crawler.urls import has_dynamic_params, has_session_id, url_depth

CATEGORY = FindingCategory.TECH_META

# ---- thresholds (kept here so they're easy to tune) -----------------------

TITLE_MIN_LEN = 30
TITLE_MAX_LEN = 65
META_DESC_MIN_LEN = 70
META_DESC_MAX_LEN = 160
URL_MAX_LEN = 115
URL_MAX_DEPTH = 4
HTML_MAX_BYTES = 1_000_000  # ~1 MB
RESPONSE_FAST_MS = 500
RESPONSE_MEDIUM_MS = 1500


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


# Title
RULE_TITLE_MISSING = _r("meta.title.missing", FindingSeverity.CRITICAL, "Page has no <title>", 3.0)
RULE_TITLE_EMPTY = _r("meta.title.empty", FindingSeverity.CRITICAL, "<title> is empty", 3.0)
RULE_TITLE_TOO_SHORT = _r(
    "meta.title.too_short", FindingSeverity.IMPORTANT, "<title> too short", 1.5
)
RULE_TITLE_TOO_LONG = _r("meta.title.too_long", FindingSeverity.IMPORTANT, "<title> too long", 1.5)
RULE_TITLE_DUPLICATE = _r(
    "meta.title.duplicate", FindingSeverity.IMPORTANT, "<title> reused on multiple pages", 2.0
)

# Meta description
RULE_META_DESC_MISSING = _r(
    "meta.description.missing", FindingSeverity.IMPORTANT, "Meta description missing", 2.0
)
RULE_META_DESC_TOO_LONG = _r(
    "meta.description.too_long", FindingSeverity.TIP, "Meta description too long", 1.0
)
RULE_META_DESC_TOO_SHORT = _r(
    "meta.description.too_short", FindingSeverity.TIP, "Meta description too short", 1.0
)
RULE_META_DESC_DUPLICATE = _r(
    "meta.description.duplicate",
    FindingSeverity.IMPORTANT,
    "Meta description reused on multiple pages",
    2.0,
)

# H1
RULE_H1_MISSING = _r("heading.h1.missing", FindingSeverity.CRITICAL, "Page has no <h1>", 2.5)
RULE_H1_MULTIPLE = _r(
    "heading.h1.multiple", FindingSeverity.IMPORTANT, "Page has multiple <h1> tags", 1.5
)

# Images
RULE_IMG_ALT_MISSING = _r(
    "content.image.alt_missing", FindingSeverity.IMPORTANT, "<img> without alt attribute", 1.0
)

# Tech: response time, charset, language, html size
RULE_RESPONSE_SLOW = _r(
    "tech.response_time.slow", FindingSeverity.IMPORTANT, "Slow page response", 1.5
)
RULE_RESPONSE_MEDIUM = _r(
    "tech.response_time.medium", FindingSeverity.TIP, "Medium page response", 0.5
)
RULE_LANG_MISSING = _r(
    "tech.language.missing", FindingSeverity.TIP, "<html lang=…> not declared", 1.0
)
RULE_HTML_TOO_LARGE = _r(
    "tech.html.too_large", FindingSeverity.TIP, "HTML response is very large", 1.0
)

# URLs
RULE_URL_TOO_LONG = _r("url.too_long", FindingSeverity.TIP, "URL is very long", 0.5)
RULE_URL_TOO_DEEP = _r("url.too_deep", FindingSeverity.TIP, "URL has many path segments", 0.5)
RULE_URL_DYNAMIC = _r(
    "url.dynamic_params", FindingSeverity.TIP, "URL contains query parameters", 0.3
)
RULE_URL_SESSION = _r("url.session_id", FindingSeverity.IMPORTANT, "URL contains a session id", 1.5)

# Indexability / fetch
RULE_PAGE_FETCH_FAILED = _r(
    "tech.fetch.failed", FindingSeverity.CRITICAL, "Page could not be fetched", 3.0
)
RULE_PAGE_HTTP_ERROR = _r(
    "tech.fetch.http_error", FindingSeverity.CRITICAL, "Page returned HTTP error", 3.0
)
RULE_PAGE_NOINDEX = _r("meta.robots.noindex", FindingSeverity.TIP, "Page set to noindex", 0.5)

# Eingebundene Ressourcen (CSS/JS/Bilder) — siehe Phase 1B-2
RULE_RESOURCE_BROKEN = _r(
    "tech.resource.broken",
    FindingSeverity.IMPORTANT,
    "Embedded resource (CSS/JS/image) returns an HTTP error",
    1.0,
)
RULE_RESOURCE_UNREACHABLE = _r(
    "tech.resource.unreachable",
    FindingSeverity.IMPORTANT,
    "Embedded resource cannot be reached (DNS / timeout / connection error)",
    1.0,
)
RULE_RESOURCE_MIXED_CONTENT = _r(
    "tech.resource.mixed_content",
    FindingSeverity.IMPORTANT,
    "HTTPS page embeds a resource over plain HTTP — browser will block it",
    1.5,
)


TECH_META_RULES: list[Rule] = registry.by_category(CATEGORY)


# ---- analyzer entry point -------------------------------------------------


@dataclass
class _Counts:
    titles: dict[str, list[str]]
    descriptions: dict[str, list[str]]


def analyze_tech_meta(
    crawl: CrawlResult,
    *,
    resource_statuses: dict[str, int | None] | None = None,
) -> list[Finding]:
    """Run all tech/meta rules across the crawl and return all findings.

    Args:
        crawl: result from ``crawler.run_crawl``.
        resource_statuses: optional ``resource_url → status_code`` map produced
            by ``crawler.resources.probe_resources``. ``None`` status means the
            request couldn't complete (DNS / timeout). When omitted, the
            broken/unreachable resource rules are skipped — mixed-content is
            still emitted because that's a pure URL-scheme check.
    """
    findings: list[Finding] = []
    counts = _build_counts(crawl)

    for cp in crawl.pages:
        findings.extend(_per_page(cp))

    findings.extend(_duplicates(counts))
    findings.extend(_resource_findings(crawl, resource_statuses))
    return findings


def _build_counts(crawl: CrawlResult) -> _Counts:
    titles: dict[str, list[str]] = defaultdict(list)
    descs: dict[str, list[str]] = defaultdict(list)
    for cp in crawl.html_pages():
        pd = cp.page_data
        if pd is None:
            continue
        if pd.title:
            titles[pd.title.strip()].append(pd.url)
        if pd.meta_description:
            descs[pd.meta_description.strip()].append(pd.url)
    return _Counts(titles=titles, descriptions=descs)


def _per_page(cp: CrawledPage) -> list[Finding]:
    out: list[Finding] = []
    fr = cp.fetch
    url = fr.final_url

    # Fetch-level failures
    if fr.error:
        out.append(_finding(RULE_PAGE_FETCH_FAILED, url, {"error": fr.error}))
        return out
    if fr.status_code is not None and fr.status_code >= 400:
        out.append(_finding(RULE_PAGE_HTTP_ERROR, url, {"status_code": fr.status_code}))
        # We still continue with URL-level rules below — but skip HTML rules.

    # URL hygiene applies regardless of HTML success
    out.extend(_url_findings(url))

    # Response time
    out.extend(_response_findings(url, fr.response_time_ms))

    # HTML-level rules require successful HTML extraction
    pd = cp.page_data
    if pd is None:
        return out

    out.extend(_title_findings(url, pd.title))
    out.extend(_meta_desc_findings(url, pd.meta_description))
    out.extend(_h1_findings(url, pd.h1_count))
    out.extend(_image_findings(url, pd.images))
    out.extend(_lang_findings(url, pd.language))
    out.extend(_html_size_findings(url, pd.html_size))
    out.extend(_robots_findings(url, pd.meta_robots))

    return out


def _title_findings(url: str, title: str | None) -> list[Finding]:
    if title is None:
        return [_finding(RULE_TITLE_MISSING, url, {})]
    if not title.strip():
        return [_finding(RULE_TITLE_EMPTY, url, {})]
    length = len(title)
    if length < TITLE_MIN_LEN:
        return [_finding(RULE_TITLE_TOO_SHORT, url, {"length": length, "min": TITLE_MIN_LEN})]
    if length > TITLE_MAX_LEN:
        return [_finding(RULE_TITLE_TOO_LONG, url, {"length": length, "max": TITLE_MAX_LEN})]
    return []


def _meta_desc_findings(url: str, desc: str | None) -> list[Finding]:
    if desc is None or not desc.strip():
        return [_finding(RULE_META_DESC_MISSING, url, {})]
    length = len(desc)
    if length < META_DESC_MIN_LEN:
        return [
            _finding(RULE_META_DESC_TOO_SHORT, url, {"length": length, "min": META_DESC_MIN_LEN})
        ]
    if length > META_DESC_MAX_LEN:
        return [
            _finding(RULE_META_DESC_TOO_LONG, url, {"length": length, "max": META_DESC_MAX_LEN})
        ]
    return []


def _h1_findings(url: str, count: int) -> list[Finding]:
    if count == 0:
        return [_finding(RULE_H1_MISSING, url, {})]
    if count > 1:
        return [_finding(RULE_H1_MULTIPLE, url, {"count": count})]
    return []


def _image_findings(url: str, images: list) -> list[Finding]:  # type: ignore[type-arg]
    missing = [img.src for img in images if not img.has_alt]
    if not missing:
        return []
    return [
        _finding(
            RULE_IMG_ALT_MISSING,
            url,
            {"count": len(missing), "examples": missing[:5]},
        )
    ]


def _lang_findings(url: str, lang: str | None) -> list[Finding]:
    if lang is None or not lang.strip():
        return [_finding(RULE_LANG_MISSING, url, {})]
    return []


def _html_size_findings(url: str, size: int) -> list[Finding]:
    if size > HTML_MAX_BYTES:
        return [_finding(RULE_HTML_TOO_LARGE, url, {"bytes": size, "max": HTML_MAX_BYTES})]
    return []


def _robots_findings(url: str, robots: str | None) -> list[Finding]:
    if not robots:
        return []
    directives = {d.strip().lower() for d in robots.split(",")}
    if "noindex" in directives or "none" in directives:
        return [_finding(RULE_PAGE_NOINDEX, url, {"directives": sorted(directives)})]
    return []


def _url_findings(url: str) -> list[Finding]:
    out: list[Finding] = []
    if len(url) > URL_MAX_LEN:
        out.append(_finding(RULE_URL_TOO_LONG, url, {"length": len(url), "max": URL_MAX_LEN}))
    if url_depth(url) > URL_MAX_DEPTH:
        out.append(
            _finding(RULE_URL_TOO_DEEP, url, {"depth": url_depth(url), "max": URL_MAX_DEPTH})
        )
    if has_session_id(url):
        out.append(_finding(RULE_URL_SESSION, url, {}))
    elif has_dynamic_params(url):
        out.append(_finding(RULE_URL_DYNAMIC, url, {}))
    return out


def _response_findings(url: str, ms: int) -> list[Finding]:
    if ms > RESPONSE_MEDIUM_MS:
        return [_finding(RULE_RESPONSE_SLOW, url, {"ms": ms, "threshold": RESPONSE_MEDIUM_MS})]
    if ms > RESPONSE_FAST_MS:
        return [_finding(RULE_RESPONSE_MEDIUM, url, {"ms": ms, "threshold": RESPONSE_FAST_MS})]
    return []


def _duplicates(counts: _Counts) -> list[Finding]:
    out: list[Finding] = []
    for title, urls in counts.titles.items():
        if len(urls) > 1:
            for url in urls:
                out.append(
                    _finding(
                        RULE_TITLE_DUPLICATE,
                        url,
                        {
                            "title": title,
                            "count": len(urls),
                            "other_urls": [u for u in urls if u != url][:5],
                        },
                    )
                )
    for desc, urls in counts.descriptions.items():
        if len(urls) > 1:
            for url in urls:
                out.append(
                    _finding(
                        RULE_META_DESC_DUPLICATE,
                        url,
                        {
                            "description": desc[:200],
                            "count": len(urls),
                            "other_urls": [u for u in urls if u != url][:5],
                        },
                    )
                )
    return out


def _resource_findings(crawl: CrawlResult, statuses: dict[str, int | None] | None) -> list[Finding]:
    """Per-page findings for embedded CSS/JS/image resources.

    Mixed-content is checked from the URL alone (no probe needed). Broken
    and unreachable findings only fire when ``statuses`` was supplied — i.e.
    the worker actually ran the resource probe pass.

    Each (page_url, resource_url) pair generates at most one finding per rule.
    A resource referenced from many pages produces one finding per page.
    """
    out: list[Finding] = []
    for cp in crawl.html_pages():
        pd = cp.page_data
        if pd is None or not pd.resources:
            continue
        page_url = cp.fetch.final_url
        page_is_https = page_url.startswith("https://")

        for resource in pd.resources:
            if page_is_https and resource.url.startswith("http://"):
                out.append(
                    _finding(
                        RULE_RESOURCE_MIXED_CONTENT,
                        page_url,
                        {"resource_url": resource.url, "resource_type": resource.resource_type},
                    )
                )

            if statuses is None:
                continue
            if resource.url not in statuses:
                continue
            status = statuses[resource.url]
            if status is None:
                out.append(
                    _finding(
                        RULE_RESOURCE_UNREACHABLE,
                        page_url,
                        {"resource_url": resource.url, "resource_type": resource.resource_type},
                    )
                )
            elif status >= 400:
                out.append(
                    _finding(
                        RULE_RESOURCE_BROKEN,
                        page_url,
                        {
                            "resource_url": resource.url,
                            "resource_type": resource.resource_type,
                            "status_code": status,
                        },
                    )
                )
    return out


def _finding(rule: Rule, url: str | None, payload: dict) -> Finding:  # type: ignore[type-arg]
    return Finding(
        rule_id=rule.rule_id,
        category=rule.category,
        severity=rule.severity,
        page_url=url,
        payload=payload,
    )
