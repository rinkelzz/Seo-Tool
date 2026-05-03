"""HTML → structured page data.

Pure parsing: takes HTML bytes (plus the URL it came from for link resolution),
returns a ``PageData`` record. No DB writes, no analysis. The analyzers in
``analyzers/`` consume ``PageData`` and produce ``Issue`` records.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

from selectolax.parser import HTMLParser, Node

from crawler.urls import is_same_site, normalize_url

# Word-token regex used for word-count and "keyword in body?" checks.
_WORD_RE = re.compile(r"\w+", re.UNICODE)


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
