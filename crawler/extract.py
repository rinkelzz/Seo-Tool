"""HTML → structured page data.

Pure parsing: takes HTML bytes (plus the URL it came from for link resolution),
returns a ``PageData`` record. No DB writes, no analysis. The analyzers in
``analyzers/`` consume ``PageData`` and produce ``Issue`` records.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

import trafilatura
from selectolax.parser import HTMLParser, Node

from crawler.urls import is_same_site, normalize_url

# Word-token regex used for word-count and "keyword in body?" checks.
_WORD_RE = re.compile(r"\w+", re.UNICODE)

# Minimum word count for a paragraph to count as a "content block" worth
# tracking for boilerplate / duplicate detection. Anything shorter is noise
# (single words, button labels, copyright lines).
_BLOCK_MIN_WORDS = 5


@dataclass
class ExtractedLink:
    """A single ``<a href=…>`` link found on the page."""

    target_url: str
    anchor_text: str
    rel: str | None
    is_internal: bool
    is_followed: bool


@dataclass
class ExtractedImage:
    """A single ``<img>`` element."""

    src: str
    alt: str | None

    @property
    def has_alt(self) -> bool:
        return self.alt is not None and self.alt.strip() != ""


@dataclass
class PageData:
    """Everything we extract from one HTML page.

    Field naming mirrors the ``Page`` SQLAlchemy model so persistence is direct.
    """

    url: str
    content_hash: str
    html_size: int

    title: str | None
    meta_description: str | None
    meta_robots: str | None
    canonical_url: str | None
    language: str | None

    h1: str | None
    headings: dict[str, list[str]] = field(default_factory=dict)
    h1_count: int = 0
    strong_count: int = 0
    bold_count: int = 0

    word_count: int = 0
    text_excerpt: str = ""

    # Main-content extraction (boilerplate stripped via trafilatura). Used by
    # the content analyzer for duplicate detection, keyword-in-body checks,
    # and TF-IDF keyword extraction.
    main_text: str | None = None
    main_word_count: int = 0
    content_blocks: list[str] = field(default_factory=list)

    images: list[ExtractedImage] = field(default_factory=list)
    links: list[ExtractedLink] = field(default_factory=list)

    @property
    def is_indexable(self) -> bool:
        """True if no robots directive forbids indexing."""
        if not self.meta_robots:
            return True
        directives = {d.strip().lower() for d in self.meta_robots.split(",")}
        return "noindex" not in directives and "none" not in directives


def extract_page(*, url: str, body: bytes, encoding: str | None = None) -> PageData:
    """Parse ``body`` (HTML bytes) into a ``PageData``.

    ``url`` is the *final* URL after redirects — it's used to resolve relative
    hrefs and to decide whether a link is internal.
    """
    html_size = len(body)
    content_hash = hashlib.sha256(body).hexdigest()

    # selectolax accepts both bytes and str; passing bytes lets it sniff encoding.
    tree = HTMLParser(body)

    title = _text_of(tree.css_first("title"))
    meta_description = _meta_content(tree, "description")
    meta_robots = _meta_content(tree, "robots")
    canonical_url = _link_href(tree, "canonical")
    if canonical_url:
        canonical_url = normalize_url(canonical_url, base=url) or canonical_url
    language = _detect_language(tree)

    headings = _collect_headings(tree)
    h1_list = headings.get("h1", [])
    strong_count = len(tree.css("strong"))
    bold_count = len(tree.css("b"))

    body_text = _visible_text(tree)
    words = _WORD_RE.findall(body_text)
    word_count = len(words)
    text_excerpt = body_text[:500]

    main_text = _extract_main_content(body)
    main_words = _WORD_RE.findall(main_text) if main_text else []
    main_word_count = len(main_words)
    content_blocks = _split_blocks(main_text) if main_text else []

    images = _collect_images(tree)
    links = _collect_links(tree, base_url=url)

    return PageData(
        url=url,
        content_hash=content_hash,
        html_size=html_size,
        title=title,
        meta_description=meta_description,
        meta_robots=meta_robots,
        canonical_url=canonical_url,
        language=language,
        h1=h1_list[0] if h1_list else None,
        headings=headings,
        h1_count=len(h1_list),
        strong_count=strong_count,
        bold_count=bold_count,
        word_count=word_count,
        text_excerpt=text_excerpt,
        main_text=main_text,
        main_word_count=main_word_count,
        content_blocks=content_blocks,
        images=images,
        links=links,
    )


# --- helpers ---------------------------------------------------------------


def _text_of(node: Node | None) -> str | None:
    if node is None:
        return None
    text = node.text(deep=True, strip=True)
    return text or None


def _meta_content(tree: HTMLParser, name: str) -> str | None:
    """Return the ``content`` attribute of ``<meta name="...">``, case-insensitive."""
    for meta in tree.css("meta[name]"):
        attr = meta.attributes.get("name", "") or ""
        if attr.lower() == name:
            content = meta.attributes.get("content")
            return content.strip() if content else None
    return None


def _link_href(tree: HTMLParser, rel: str) -> str | None:
    """Return the ``href`` of the first ``<link rel="...">`` matching ``rel``."""
    for link in tree.css("link[rel]"):
        rels = (link.attributes.get("rel") or "").lower().split()
        if rel in rels:
            href = link.attributes.get("href")
            return href.strip() if href else None
    return None


def _detect_language(tree: HTMLParser) -> str | None:
    html = tree.css_first("html")
    if html is None:
        return None
    lang = html.attributes.get("lang")
    return lang.strip() if lang else None


def _collect_headings(tree: HTMLParser) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for level in ("h1", "h2", "h3", "h4", "h5", "h6"):
        items = [t for n in tree.css(level) if (t := _text_of(n))]
        if items:
            out[level] = items
    return out


def _visible_text(tree: HTMLParser) -> str:
    """Strip script/style/template, return whitespace-collapsed visible text."""
    for tag in ("script", "style", "template", "noscript"):
        for node in tree.css(tag):
            node.decompose()
    body = tree.css_first("body") or tree
    text = body.text(separator=" ", deep=True, strip=True)
    return re.sub(r"\s+", " ", text).strip()


def _collect_images(tree: HTMLParser) -> list[ExtractedImage]:
    out: list[ExtractedImage] = []
    for img in tree.css("img"):
        src = img.attributes.get("src")
        if not src:
            continue
        alt = img.attributes.get("alt")
        out.append(ExtractedImage(src=src.strip(), alt=alt))
    return out


def _extract_main_content(body: bytes) -> str | None:
    """Run trafilatura against the raw HTML to get the main article text.

    Returns ``None`` when nothing extractable was found (login pages, pure
    navigation, etc.). We pass ``favor_precision=True`` so that the extractor
    prefers leaving boilerplate out — false negatives are better than
    contaminating duplicate detection with header/footer text.
    """
    try:
        result = trafilatura.extract(
            body,
            output_format="txt",
            favor_precision=True,
            include_comments=False,
            include_tables=True,
            no_fallback=False,
        )
    except Exception:  # noqa: BLE001 — trafilatura may raise on weird HTML
        return None
    if not result:
        return None
    text = result.strip()
    return text or None


def _split_blocks(main_text: str) -> list[str]:
    """Split main content into paragraph-level blocks for boilerplate detection.

    Trafilatura's plaintext output uses ``\\n`` between paragraphs. We split,
    normalise whitespace, drop very short blocks, and deduplicate within the
    page (one block tracked once even if repeated within the page).
    """
    seen: set[str] = set()
    out: list[str] = []
    for raw in main_text.split("\n"):
        block = re.sub(r"\s+", " ", raw).strip()
        if not block:
            continue
        if len(_WORD_RE.findall(block)) < _BLOCK_MIN_WORDS:
            continue
        if block in seen:
            continue
        seen.add(block)
        out.append(block)
    return out


def _collect_links(tree: HTMLParser, *, base_url: str) -> list[ExtractedLink]:
    out: list[ExtractedLink] = []
    for a in tree.css("a[href]"):
        raw = a.attributes.get("href") or ""
        target = normalize_url(raw, base=base_url)
        if target is None:
            continue
        anchor = (a.text(deep=True, strip=True) or "").strip()
        rel_attr = a.attributes.get("rel")
        rel_tokens = (rel_attr or "").lower().split()
        is_followed = "nofollow" not in rel_tokens
        out.append(
            ExtractedLink(
                target_url=target,
                anchor_text=anchor[:1024],
                rel=rel_attr,
                is_internal=is_same_site(target, base_url),
                is_followed=is_followed,
            )
        )
    return out
