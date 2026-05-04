"""Content analyzer rules.

Mirrors the "Inhalt" section of the Seobility export:
- duplicate pages (exact and near-duplicate via SimHash on the main content)
- repeated content blocks across pages (boilerplate exceeding header/footer)
- keyword-in-body checks (Title/H1 keywords actually used in body text)
- keyword cannibalization (multiple pages competing for the same keyword)

Findings work on the raw ``CrawlResult`` only; the worker turns them into
``Issue`` rows. Pages without extracted main content are skipped — those
yield no useful signal.
"""

from __future__ import annotations

import hashlib
import re
from collections import Counter, defaultdict
from dataclasses import dataclass

from datasketch import LeanMinHash, MinHash

from analyzers.base import Finding, FindingCategory, FindingSeverity, Rule, registry
from crawler.engine import CrawlResult

CATEGORY = FindingCategory.CONTENT

# ---- thresholds -----------------------------------------------------------

# Minimum word count before we run duplicate detection on a page. Very short
# pages (login forms, contact pages) match each other by accident otherwise.
MIN_WORDS_FOR_DUPLICATE = 50

# MinHash Jaccard similarity threshold for "near duplicate". 0.85 = ~85 % of
# 4-word shingles match.
NEAR_DUPLICATE_THRESHOLD = 0.85

# Block must repeat on this many pages before it's flagged. 1 means "no
# repeat", so the threshold is "more than X". Header/footer text typically
# repeats on every page — that's expected, but we still surface it as a tip
# when the threshold is exceeded.
BLOCK_REPEAT_THRESHOLD = 3

# Minimum keyword length for "keyword in body" — anything shorter is noise.
KEYWORD_MIN_LEN = 4

# Stopwords (DE+EN) excluded from keyword extraction.
_STOPWORDS = frozenset(
    {
        # German
        "der",
        "die",
        "das",
        "den",
        "dem",
        "des",
        "ein",
        "eine",
        "einen",
        "einem",
        "einer",
        "eines",
        "und",
        "oder",
        "aber",
        "sondern",
        "denn",
        "weil",
        "wenn",
        "dann",
        "ist",
        "sind",
        "war",
        "waren",
        "wird",
        "werden",
        "wurde",
        "wurden",
        "hat",
        "haben",
        "hatte",
        "hatten",
        "auf",
        "für",
        "mit",
        "von",
        "zu",
        "im",
        "in",
        "an",
        "bei",
        "aus",
        "über",
        "unter",
        "vor",
        "nach",
        "ohne",
        "gegen",
        "durch",
        "um",
        "auch",
        "noch",
        "nur",
        "schon",
        "wieder",
        "sehr",
        "mehr",
        "alle",
        "sich",
        "sie",
        "es",
        "er",
        "wir",
        "ihr",
        "sein",
        "seine",
        "ihre",
        "als",
        "wie",
        "was",
        "wer",
        "wo",
        "warum",
        "wann",
        "welche",
        "diese",
        "dieser",
        "dieses",
        "diesen",
        "diesem",
        "uns",
        "ihnen",
        "mir",
        "mich",
        "dich",
        "dir",
        # English
        "the",
        "and",
        "for",
        "with",
        "from",
        "this",
        "that",
        "these",
        "those",
        "have",
        "has",
        "had",
        "are",
        "were",
        "will",
        "would",
        "could",
        "should",
        "you",
        "your",
        "our",
        "their",
        "his",
        "her",
        "but",
        "not",
        "all",
        "any",
        "more",
        "less",
        "than",
        "into",
        "onto",
    }
)

_WORD_RE = re.compile(r"\w+", re.UNICODE)


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


RULE_DUPLICATE_PAGE = _r(
    "content.duplicate.page",
    FindingSeverity.CRITICAL,
    "Page is an exact duplicate of another crawled page",
    2.5,
)
RULE_NEAR_DUPLICATE_PAGE = _r(
    "content.duplicate.near",
    FindingSeverity.IMPORTANT,
    "Page is a near-duplicate (>=85 % shingle overlap) of another crawled page",
    1.5,
)
RULE_BLOCK_REPEATED = _r(
    "content.block.repeated",
    FindingSeverity.TIP,
    "Content block repeats across many pages (boilerplate beyond header/footer)",
    0.5,
)
RULE_TITLE_KEYWORD_MISSING = _r(
    "content.keyword.title_not_in_body",
    FindingSeverity.IMPORTANT,
    "Significant title keyword is not used in the page's main content",
    1.0,
)
RULE_H1_KEYWORD_MISSING = _r(
    "content.keyword.h1_not_in_body",
    FindingSeverity.IMPORTANT,
    "Significant H1 keyword is not used in the page's main content",
    1.0,
)
RULE_CANNIBALIZATION = _r(
    "content.keyword.cannibalization",
    FindingSeverity.IMPORTANT,
    "Multiple pages compete strongly for the same keyword",
    1.5,
)
RULE_THIN_CONTENT = _r(
    "content.thin",
    FindingSeverity.IMPORTANT,
    "Page has very little main content",
    1.5,
)

THIN_CONTENT_MIN_WORDS = 100

# Phase 4B — Tippfehler/Grammatik via LanguageTool. Eine einzelne Regel pro
# Seite mit den gesammelten Top-Beispielen; Schwellwert (`min_errors`)
# kommt von außen, weil er Konfig ist, nicht hard-coded.
RULE_SPELLING_ERRORS = _r(
    "content.spelling.errors",
    FindingSeverity.TIP,
    "Page has spelling/grammar issues flagged by LanguageTool",
    0.5,
)

CONTENT_RULES: list[Rule] = registry.by_category(CATEGORY)


# ---- analyzer entry point -------------------------------------------------


@dataclass
class _PageContent:
    """Reduced view of a page used by the content analyzer."""

    url: str
    title: str | None
    h1: str | None
    main_text: str
    main_word_count: int
    content_blocks: list[str]


def analyze_content(
    crawl: CrawlResult,
    *,
    spelling_results: dict | None = None,  # url → SpellingResult; structural
    spelling_min_errors: int = 5,
) -> list[Finding]:
    """Run all content rules across the crawl and return all findings.

    Args:
        crawl: result from ``crawler.run_crawl``.
        spelling_results: optional ``url → crawler.SpellingResult`` map. When
            present, pages with at least ``spelling_min_errors`` matches get a
            ``content.spelling.errors`` finding (TIP severity). When absent
            (default), spelling rules don't fire.
        spelling_min_errors: threshold to keep noise from one-off false
            positives out of the report. Default 5 — generous enough that
            a single typo or stylistic LT hint won't trigger a finding.
    """
    pages = _collect_pages(crawl)
    findings: list[Finding] = []

    findings.extend(_thin_content_findings(pages))
    findings.extend(_duplicate_page_findings(pages))
    findings.extend(_block_repeat_findings(pages))
    findings.extend(_keyword_in_body_findings(pages))
    findings.extend(_cannibalization_findings(pages))
    if spelling_results:
        findings.extend(_spelling_findings(spelling_results, spelling_min_errors))

    return findings


# ---- helpers --------------------------------------------------------------


def _collect_pages(crawl: CrawlResult) -> list[_PageContent]:
    out: list[_PageContent] = []
    for cp in crawl.html_pages():
        pd = cp.page_data
        if pd is None or not pd.main_text:
            continue
        out.append(
            _PageContent(
                url=cp.fetch.final_url,
                title=pd.title,
                h1=pd.h1,
                main_text=pd.main_text,
                main_word_count=pd.main_word_count,
                content_blocks=list(pd.content_blocks),
            )
        )
    return out


def _thin_content_findings(pages: list[_PageContent]) -> list[Finding]:
    out: list[Finding] = []
    for p in pages:
        if p.main_word_count < THIN_CONTENT_MIN_WORDS:
            out.append(
                _finding(
                    RULE_THIN_CONTENT,
                    p.url,
                    {"word_count": p.main_word_count, "min": THIN_CONTENT_MIN_WORDS},
                )
            )
    return out


def _duplicate_page_findings(pages: list[_PageContent]) -> list[Finding]:
    """Detect both exact (SHA-256 over normalised main text) and near
    (MinHash Jaccard >= threshold) duplicate pages.

    Exact duplicates take precedence — when two pages match exactly we don't
    also emit a near-duplicate finding for the same pair.
    """
    out: list[Finding] = []
    eligible = [p for p in pages if p.main_word_count >= MIN_WORDS_FOR_DUPLICATE]
    if len(eligible) < 2:
        return out

    # Exact duplicates by normalised hash
    exact_groups: dict[str, list[str]] = defaultdict(list)
    for p in eligible:
        normalised = re.sub(r"\s+", " ", p.main_text).strip().lower()
        digest = hashlib.sha256(normalised.encode("utf-8")).hexdigest()
        exact_groups[digest].append(p.url)

    exact_pairs: set[frozenset[str]] = set()
    for urls in exact_groups.values():
        if len(urls) > 1:
            for url in urls:
                others = [u for u in urls if u != url]
                out.append(
                    _finding(
                        RULE_DUPLICATE_PAGE,
                        url,
                        {"duplicate_of": others[:5], "count": len(urls)},
                    )
                )
            for u1 in urls:
                for u2 in urls:
                    if u1 != u2:
                        exact_pairs.add(frozenset({u1, u2}))

    # Near-duplicates via MinHash on 4-word shingles.
    minhashes: dict[str, LeanMinHash] = {}
    for p in eligible:
        mh = MinHash(num_perm=128)
        for shingle in _shingles(p.main_text, k=4):
            mh.update(shingle.encode("utf-8"))
        minhashes[p.url] = LeanMinHash(mh)

    urls = list(minhashes.keys())
    seen_pairs: set[frozenset[str]] = set()
    for i, u1 in enumerate(urls):
        for u2 in urls[i + 1 :]:
            pair = frozenset({u1, u2})
            if pair in exact_pairs or pair in seen_pairs:
                continue
            sim = minhashes[u1].jaccard(minhashes[u2])
            if sim >= NEAR_DUPLICATE_THRESHOLD:
                seen_pairs.add(pair)
                out.append(
                    _finding(
                        RULE_NEAR_DUPLICATE_PAGE,
                        u1,
                        {"similar_to": u2, "similarity": round(sim, 3)},
                    )
                )
                out.append(
                    _finding(
                        RULE_NEAR_DUPLICATE_PAGE,
                        u2,
                        {"similar_to": u1, "similarity": round(sim, 3)},
                    )
                )
    return out


def _block_repeat_findings(pages: list[_PageContent]) -> list[Finding]:
    """A content block that appears on more than ``BLOCK_REPEAT_THRESHOLD``
    pages is flagged on each page that contains it.

    This catches large boilerplate sections that bloat every page (e.g. a
    multi-paragraph footer the trafilatura precision filter still picked up).
    """
    out: list[Finding] = []
    block_to_pages: dict[str, set[str]] = defaultdict(set)
    for p in pages:
        for block in p.content_blocks:
            block_to_pages[block].add(p.url)

    for block, urls in block_to_pages.items():
        if len(urls) > BLOCK_REPEAT_THRESHOLD:
            for url in urls:
                out.append(
                    _finding(
                        RULE_BLOCK_REPEATED,
                        url,
                        {
                            "excerpt": block[:200],
                            "page_count": len(urls),
                            "threshold": BLOCK_REPEAT_THRESHOLD,
                        },
                    )
                )
    return out


def _keyword_in_body_findings(pages: list[_PageContent]) -> list[Finding]:
    """For each page, take the most prominent content keyword from the title
    and from the H1 and check whether it appears in the body text.
    """
    out: list[Finding] = []
    for p in pages:
        body_words = {w.lower() for w in _WORD_RE.findall(p.main_text)}
        title_kw = _top_keyword(p.title or "")
        if title_kw and title_kw not in body_words:
            out.append(
                _finding(
                    RULE_TITLE_KEYWORD_MISSING,
                    p.url,
                    {"keyword": title_kw, "source": "title"},
                )
            )
        h1_kw = _top_keyword(p.h1 or "")
        if h1_kw and h1_kw != title_kw and h1_kw not in body_words:
            out.append(
                _finding(
                    RULE_H1_KEYWORD_MISSING,
                    p.url,
                    {"keyword": h1_kw, "source": "h1"},
                )
            )
    return out


def _cannibalization_findings(pages: list[_PageContent]) -> list[Finding]:
    """Detect cannibalization: two or more pages share their top keyword(s).

    We use raw term frequency (after stopword + length filtering), not TF-IDF.
    Cannibalization is fundamentally a "same main topic on multiple pages"
    problem — TF-IDF would deliberately *deprioritise* such terms because
    they're not document-distinguishing, which is the opposite of what we want.
    """
    out: list[Finding] = []
    if len(pages) < 2:
        return out

    top_per_page: dict[str, list[str]] = {}
    for p in pages:
        tokens = [t.lower() for t in _WORD_RE.findall(p.main_text)]
        tokens = [t for t in tokens if len(t) >= KEYWORD_MIN_LEN and t not in _STOPWORDS]
        if not tokens:
            continue
        tf = Counter(tokens)
        # Top-3 most frequent meaningful terms — these are the page's "topic"
        top_per_page[p.url] = [term for term, _ in tf.most_common(3)]

    if len(top_per_page) < 2:
        return out

    # Invert: keyword → pages that have it in top-3
    keyword_to_pages: dict[str, list[str]] = defaultdict(list)
    for url, kws in top_per_page.items():
        for kw in kws:
            keyword_to_pages[kw].append(url)

    for keyword, urls in keyword_to_pages.items():
        if len(urls) > 1:
            for url in urls:
                others = [u for u in urls if u != url]
                out.append(
                    _finding(
                        RULE_CANNIBALIZATION,
                        url,
                        {"keyword": keyword, "competing_with": others[:5]},
                    )
                )
    return out


def _spelling_findings(
    spelling_results: dict, min_errors: int  # type: ignore[type-arg]
) -> list[Finding]:
    """One finding per page with ``min_errors`` or more LT matches.

    Payload aggregates a top-N excerpt list and the most-frequent rule_ids
    so the report can show what kind of issues dominate.
    """
    out: list[Finding] = []
    for url, result in spelling_results.items():
        if getattr(result, "error", None):
            # LT call failed for this page — silently skip; the worker logs
            # the underlying error already.
            continue
        matches = getattr(result, "matches", []) or []
        if len(matches) < min_errors:
            continue
        rule_counts: Counter[str] = Counter(m.rule_id for m in matches)
        examples = [
            {
                "rule_id": m.rule_id,
                "message": m.message,
                "excerpt": m.excerpt,
                "suggestions": m.suggestions[:3],
            }
            for m in matches[:5]
        ]
        out.append(
            _finding(
                RULE_SPELLING_ERRORS,
                url,
                {
                    "count": len(matches),
                    "min_errors": min_errors,
                    "top_rules": [r for r, _ in rule_counts.most_common(5)],
                    "examples": examples,
                },
            )
        )
    return out


def _shingles(text: str, *, k: int) -> list[str]:
    tokens = _WORD_RE.findall(text.lower())
    if len(tokens) < k:
        return [" ".join(tokens)] if tokens else []
    return [" ".join(tokens[i : i + k]) for i in range(len(tokens) - k + 1)]


def _top_keyword(text: str) -> str | None:
    """Return the single most informative word from a short string."""
    words = [w.lower() for w in _WORD_RE.findall(text)]
    candidates = [w for w in words if len(w) >= KEYWORD_MIN_LEN and w not in _STOPWORDS]
    if not candidates:
        return None
    counts = Counter(candidates)
    return counts.most_common(1)[0][0]


def _finding(rule: Rule, url: str | None, payload: dict) -> Finding:  # type: ignore[type-arg]
    return Finding(
        rule_id=rule.rule_id,
        category=rule.category,
        severity=rule.severity,
        page_url=url,
        payload=payload,
    )
