"""HTML-extractor tests — fixtures focus on edge cases analyzers will care about."""

from __future__ import annotations

from crawler.extract import extract_page

BASE = "https://example.com/page"


def _html(body: str) -> bytes:
    return body.encode("utf-8")


def test_extract_full_page() -> None:
    body = _html("""
        <!doctype html>
        <html lang="de">
        <head>
            <title>Beispielseite — Über uns</title>
            <meta name="description" content="Eine ausreichend lange Beschreibung der Seite, die vermutlich gut genug ist um den unteren Schwellwert zu überschreiten.">
            <meta name="robots" content="index, follow">
            <link rel="canonical" href="https://example.com/page">
        </head>
        <body>
            <h1>Hauptüberschrift</h1>
            <p>Erster Absatz mit ein paar <strong>fetten</strong> Wörtern.</p>
            <h2>Unter</h2>
            <img src="/img1.png" alt="Bild eins">
            <img src="/img2.png">
            <a href="/about">Mehr</a>
            <a href="https://other.com/" rel="nofollow noopener">Extern</a>
        </body>
        </html>
        """)
    pd = extract_page(url=BASE, body=body)

    assert pd.title == "Beispielseite — Über uns"
    assert pd.meta_description is not None and pd.meta_description.startswith("Eine ausreichend")
    assert pd.meta_robots == "index, follow"
    assert pd.canonical_url == "https://example.com/page"
    assert pd.language == "de"
    assert pd.h1 == "Hauptüberschrift"
    assert pd.h1_count == 1
    assert pd.headings.get("h2") == ["Unter"]
    assert pd.strong_count == 1
    assert pd.word_count > 0
    assert len(pd.images) == 2
    assert pd.images[0].has_alt is True
    assert pd.images[1].has_alt is False
    assert len(pd.links) == 2
    internal = next(link for link in pd.links if link.target_url.endswith("/about"))
    external = next(link for link in pd.links if "other.com" in link.target_url)
    assert internal.is_internal is True
    assert external.is_internal is False
    assert external.is_followed is False  # nofollow honoured
    assert pd.is_indexable is True


def test_missing_title_and_meta() -> None:
    pd = extract_page(url=BASE, body=_html("<html><body><p>x</p></body></html>"))
    assert pd.title is None
    assert pd.meta_description is None
    assert pd.h1 is None
    assert pd.h1_count == 0
    assert pd.canonical_url is None
    assert pd.language is None


def test_noindex_marks_not_indexable() -> None:
    body = _html(
        """<html><head><meta name="robots" content="noindex,follow"></head><body></body></html>"""
    )
    pd = extract_page(url=BASE, body=body)
    assert pd.is_indexable is False


def test_multiple_h1() -> None:
    body = _html("<html><body><h1>One</h1><h1>Two</h1></body></html>")
    pd = extract_page(url=BASE, body=body)
    assert pd.h1_count == 2
    assert pd.h1 == "One"


def test_javascript_link_skipped() -> None:
    body = _html('<html><body><a href="javascript:void(0)">x</a></body></html>')
    pd = extract_page(url=BASE, body=body)
    assert pd.links == []


def test_link_without_anchor_text_keeps_empty_string() -> None:
    body = _html('<html><body><a href="/x"><img src="/y.png" alt=""></a></body></html>')
    pd = extract_page(url=BASE, body=body)
    assert pd.links[0].anchor_text == ""


def test_content_hash_is_stable() -> None:
    body = _html("<html><body>Hello</body></html>")
    pd1 = extract_page(url=BASE, body=body)
    pd2 = extract_page(url=BASE, body=body)
    assert pd1.content_hash == pd2.content_hash


def test_strips_script_and_style_from_word_count() -> None:
    body = _html("""
        <html><body>
        <script>var x = 1; var y = 2;</script>
        <style>.a{color:red}</style>
        <p>Eins zwei drei vier</p>
        </body></html>
        """)
    pd = extract_page(url=BASE, body=body)
    assert pd.word_count == 4
