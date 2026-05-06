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


def test_main_text_extracted_via_trafilatura() -> None:
    body = _html("""
        <html lang="de">
        <body>
            <header><nav>Navigation hier mit vielen Links</nav></header>
            <main>
                <article>
                    <h1>Hauptartikel</h1>
                    <p>Dies ist ein ausreichend langer Hauptabsatz mit ein paar
                    sinnvollen Wörtern, damit trafilatura ihn als Hauptinhalt
                    erkennt und nicht als Boilerplate verwirft.</p>
                    <p>Hier kommt ein zweiter Absatz, ebenfalls mit genug Inhalt
                    damit er als eigenständiger Block aufgenommen wird.</p>
                </article>
            </main>
            <footer>Copyright 2026 — alle Rechte vorbehalten</footer>
        </body>
        </html>
        """)
    pd = extract_page(url=BASE, body=body)
    assert pd.main_text is not None
    assert "Hauptabsatz" in pd.main_text
    # Footer/Nav should be filtered out (favor_precision=True)
    assert "Copyright" not in pd.main_text
    assert pd.main_word_count > 0
    assert len(pd.content_blocks) >= 1
    # Each block should be a non-empty trimmed paragraph
    for block in pd.content_blocks:
        assert block == block.strip()
        assert len(block.split()) >= 5


def test_main_text_none_when_nothing_extractable() -> None:
    body = _html("<html><body></body></html>")
    pd = extract_page(url=BASE, body=body)
    assert pd.main_text is None
    assert pd.main_word_count == 0
    assert pd.content_blocks == []


def test_charset_html5_meta() -> None:
    body = _html('<html><head><meta charset="utf-8"></head><body></body></html>')
    pd = extract_page(url=BASE, body=body)
    assert pd.charset == "utf-8"


def test_charset_legacy_http_equiv() -> None:
    body = _html(
        "<html><head>"
        '<meta http-equiv="Content-Type" content="text/html; charset=ISO-8859-1">'
        "</head><body></body></html>"
    )
    pd = extract_page(url=BASE, body=body)
    assert pd.charset is not None
    # http-equiv parsing lowercases tokens
    assert pd.charset.lower() == "iso-8859-1"


def test_charset_absent_returns_none() -> None:
    body = _html("<html><head></head><body></body></html>")
    pd = extract_page(url=BASE, body=body)
    assert pd.charset is None


def test_resources_collected_from_link_script_and_img() -> None:
    body = _html("""
        <html>
        <head>
            <link rel="stylesheet" href="/css/main.css">
            <link rel="stylesheet" href="https://cdn.other.com/lib.css">
            <link rel="alternate stylesheet" href="/css/dark.css">
            <link rel="icon" href="/favicon.ico">
            <script src="/js/app.js"></script>
            <script src="https://cdn.other.com/jquery.js"></script>
        </head>
        <body>
            <img src="/img/hero.png" alt="hero">
        </body>
        </html>
        """)
    pd = extract_page(url=BASE, body=body)
    by_url = {r.url: r for r in pd.resources}

    # Stylesheets (incl. alternate stylesheet), scripts, image — but not favicon
    assert "https://example.com/css/main.css" in by_url
    assert "https://example.com/css/dark.css" in by_url
    assert "https://cdn.other.com/lib.css" in by_url
    assert "https://example.com/js/app.js" in by_url
    assert "https://cdn.other.com/jquery.js" in by_url
    assert "https://example.com/img/hero.png" in by_url
    assert "https://example.com/favicon.ico" not in by_url

    # Types
    assert by_url["https://example.com/css/main.css"].resource_type == "stylesheet"
    assert by_url["https://example.com/js/app.js"].resource_type == "script"
    assert by_url["https://example.com/img/hero.png"].resource_type == "image"

    # Internal flag
    assert by_url["https://example.com/css/main.css"].is_internal is True
    assert by_url["https://cdn.other.com/lib.css"].is_internal is False


def test_resources_deduplicated_within_page() -> None:
    body = _html("""
        <html><head>
        <link rel="stylesheet" href="/main.css">
        <link rel="stylesheet" href="/main.css">
        <script src="/app.js"></script>
        <script src="/app.js"></script>
        </head><body></body></html>
        """)
    pd = extract_page(url=BASE, body=body)
    urls = [r.url for r in pd.resources]
    assert urls.count("https://example.com/main.css") == 1
    assert urls.count("https://example.com/app.js") == 1


def test_no_resources_when_page_is_empty() -> None:
    pd = extract_page(url=BASE, body=_html("<html><body></body></html>"))
    assert pd.resources == []
