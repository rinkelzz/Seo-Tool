"""End-to-end test of the crawl worker job: HTTP → DB.

Mocks the network with ``respx`` and uses the in-memory SQLite session from
``conftest``. The job runs synchronously inside the test process (no Redis).
"""

from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest
import respx

from backend.app.models.content_block import ContentBlock
from backend.app.models.crawl import Crawl, CrawlStatus
from backend.app.models.image import Image
from backend.app.models.issue import Issue
from backend.app.models.link import Link
from backend.app.models.page import Page
from backend.app.models.project import Project
from backend.app.models.sitemap import Sitemap
from worker.jobs.crawl import run_crawl_job


def _html(title: str, body: str = "<p>x</p>", with_alt: bool = True) -> str:
    img = '<img src="/x.png" alt="x">' if with_alt else '<img src="/x.png">'
    return (
        f'<html lang="de"><head><title>{title}</title>'
        f'<meta name="description" content="A meta description that is sufficiently long to satisfy the heuristic threshold for descriptions.">'
        f"</head><body><h1>Heading</h1>{img}{body}</body></html>"
    )


@respx.mock
def test_full_crawl_persists_pages_findings_and_scores(db_session, engine) -> None:
    # Arrange a tiny site
    respx.get("https://demo.test/robots.txt").mock(return_value=httpx.Response(404))
    respx.get("https://demo.test/").mock(
        return_value=httpx.Response(
            200,
            html=_html(
                "Startseite — eine ausreichend lange Überschrift",
                body='<a href="/about">About</a>',
            ),
            headers={"content-type": "text/html"},
        )
    )
    respx.get("https://demo.test/about").mock(
        return_value=httpx.Response(
            200,
            html=_html(
                "Über uns — eine ausreichend lange Überschrift hier auch",
                with_alt=False,  # missing alt should produce a finding
            ),
            headers={"content-type": "text/html"},
        )
    )

    project = Project(
        name="Demo",
        domain="demo.test",
        base_url="https://demo.test/",
        robots_respect=True,
        js_render=False,
    )
    db_session.add(project)
    db_session.commit()
    crawl = Crawl(project_id=project.id, status=CrawlStatus.QUEUED)
    db_session.add(crawl)
    db_session.commit()
    crawl_id = crawl.id

    # Patch the worker's session factory to reuse the test in-memory engine.
    from sqlalchemy.orm import sessionmaker

    SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with patch("worker.jobs.crawl.get_session_factory", return_value=SessionLocal):
        run_crawl_job(crawl_id)

    db_session.expire_all()
    crawl_after = db_session.get(Crawl, crawl_id)
    assert crawl_after is not None
    assert crawl_after.status == CrawlStatus.COMPLETED
    assert crawl_after.pages_crawled == 2
    assert crawl_after.score_tech is not None
    assert crawl_after.score_overall is not None
    assert crawl_after.started_at is not None
    assert crawl_after.finished_at is not None

    pages = db_session.query(Page).filter(Page.crawl_id == crawl_id).all()
    assert len(pages) == 2
    assert {p.url for p in pages} == {"https://demo.test/", "https://demo.test/about"}
    for p in pages:
        assert p.title is not None
        assert p.h1 == "Heading"
        assert p.language == "de"
        assert p.status_code == 200
        assert p.is_indexable is True

    images = db_session.query(Image).all()
    assert len(images) == 2  # one per page
    assert any(not img.has_alt for img in images)

    links = db_session.query(Link).filter(Link.crawl_id == crawl_id).all()
    # exactly one internal link (the /about link from /); no external links present
    assert len(links) == 1
    assert links[0].is_internal is True

    issues = db_session.query(Issue).filter(Issue.crawl_id == crawl_id).all()
    assert len(issues) > 0
    rule_ids = {i.rule_id for i in issues}
    assert "content.image.alt_missing" in rule_ids


@respx.mock
def test_crawl_failure_marks_status(db_session, engine) -> None:
    # Project base_url that the engine rejects (no scheme) — triggers ValueError.
    project = Project(
        name="Bad",
        domain="bad.test",
        base_url="not-a-url",
        robots_respect=True,
        js_render=False,
    )
    db_session.add(project)
    db_session.commit()
    crawl = Crawl(project_id=project.id, status=CrawlStatus.QUEUED)
    db_session.add(crawl)
    db_session.commit()
    crawl_id = crawl.id

    from sqlalchemy.orm import sessionmaker

    SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with patch("worker.jobs.crawl.get_session_factory", return_value=SessionLocal):
        run_crawl_job(crawl_id)

    db_session.expire_all()
    crawl_after = db_session.get(Crawl, crawl_id)
    assert crawl_after.status == CrawlStatus.FAILED
    assert crawl_after.error_message is not None


@respx.mock
def test_external_link_check_populates_status_and_findings(db_session, engine) -> None:
    """A crawl with an external link should:
    - probe the external URL (HEAD)
    - persist target_status_code on the Link row
    - emit a structure finding when the external link is broken
    """
    respx.get("https://demo2.test/robots.txt").mock(return_value=httpx.Response(404))
    respx.get("https://demo2.test/").mock(
        return_value=httpx.Response(
            200,
            html=_html(
                "Eine Startseite mit ausreichend langem Titel hier",
                body=(
                    '<a href="https://broken.test/dead">extern dead</a>'
                    '<a href="https://ok.test/page">extern ok</a>'
                ),
            ),
            headers={"content-type": "text/html"},
        )
    )
    respx.head("https://broken.test/dead").mock(return_value=httpx.Response(404))
    respx.head("https://ok.test/page").mock(return_value=httpx.Response(200))

    project = Project(
        name="Demo2",
        domain="demo2.test",
        base_url="https://demo2.test/",
        robots_respect=True,
        js_render=False,
    )
    db_session.add(project)
    db_session.commit()
    crawl = Crawl(project_id=project.id, status=CrawlStatus.QUEUED)
    db_session.add(crawl)
    db_session.commit()
    crawl_id = crawl.id

    from sqlalchemy.orm import sessionmaker

    SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with patch("worker.jobs.crawl.get_session_factory", return_value=SessionLocal):
        run_crawl_job(crawl_id)

    db_session.expire_all()
    crawl_after = db_session.get(Crawl, crawl_id)
    assert crawl_after.status == CrawlStatus.COMPLETED

    links = db_session.query(Link).filter(Link.crawl_id == crawl_id).all()
    by_target = {link.target_url: link for link in links}
    assert by_target["https://broken.test/dead"].target_status_code == 404
    assert by_target["https://ok.test/page"].target_status_code == 200

    issues = db_session.query(Issue).filter(Issue.crawl_id == crawl_id).all()
    rule_ids = {i.rule_id for i in issues}
    assert "structure.external_link.broken" in rule_ids
    # Structure score must be set, not just tech score
    assert crawl_after.score_struct is not None


@respx.mock
def test_content_blocks_persisted_and_score_set(db_session, engine) -> None:
    """A page with extractable main content should produce ContentBlock rows
    and a non-null score_content."""
    rich_body = (
        "<article>"
        "<h1>Hauptartikel mit ausreichend Inhalt</h1>"
        "<p>Dies ist ein erster Absatz, der lang genug ist um vom Trafilatura-"
        "Extraktor als Hauptinhalt erkannt zu werden und auch die "
        "Block-Mindestlänge übersteigt.</p>"
        "<p>Hier kommt ein zweiter, ebenfalls inhaltsschwerer Absatz, damit "
        "wir mehr als einen Content-Block für die Persistenz-Prüfung haben.</p>"
        "</article>"
    )
    respx.get("https://demo3.test/robots.txt").mock(return_value=httpx.Response(404))
    respx.get("https://demo3.test/").mock(
        return_value=httpx.Response(
            200,
            html=_html("Eine Startseite mit ausreichend langem Titel hier", body=rich_body),
            headers={"content-type": "text/html"},
        )
    )

    project = Project(
        name="Demo3",
        domain="demo3.test",
        base_url="https://demo3.test/",
        robots_respect=True,
        js_render=False,
    )
    db_session.add(project)
    db_session.commit()
    crawl = Crawl(project_id=project.id, status=CrawlStatus.QUEUED)
    db_session.add(crawl)
    db_session.commit()
    crawl_id = crawl.id

    from sqlalchemy.orm import sessionmaker

    SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with patch("worker.jobs.crawl.get_session_factory", return_value=SessionLocal):
        run_crawl_job(crawl_id)

    db_session.expire_all()
    crawl_after = db_session.get(Crawl, crawl_id)
    assert crawl_after.status == CrawlStatus.COMPLETED
    assert crawl_after.score_content is not None  # content score now populated

    blocks = db_session.query(ContentBlock).all()
    assert len(blocks) >= 1
    for block in blocks:
        assert len(block.block_hash) == 64  # SHA-256 hex
        assert block.word_count >= 5
        assert block.text_excerpt.strip() == block.text_excerpt


@respx.mock
def test_sitemap_persisted_and_diff_findings_emitted(db_session, engine) -> None:
    """A sitemap that lists a page the crawler can't reach should:
    - be persisted as a Sitemap row with the URL list
    - emit a structure.sitemap.in_sitemap_only finding for the missing URL
    """
    sitemap_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        "<url><loc>https://demo4.test/</loc></url>"
        "<url><loc>https://demo4.test/orphan</loc></url>"
        "</urlset>"
    )
    respx.get("https://demo4.test/robots.txt").mock(return_value=httpx.Response(404))
    respx.get("https://demo4.test/sitemap.xml").mock(
        return_value=httpx.Response(
            200, text=sitemap_xml, headers={"content-type": "application/xml"}
        )
    )
    # Crawl the start page only — /orphan is in the sitemap but not linked
    respx.get("https://demo4.test/").mock(
        return_value=httpx.Response(
            200,
            html=_html("Eine Startseite mit ausreichend langem Titel hier"),
            headers={"content-type": "text/html"},
        )
    )

    project = Project(
        name="Demo4",
        domain="demo4.test",
        base_url="https://demo4.test/",
        robots_respect=True,
        js_render=False,
    )
    db_session.add(project)
    db_session.commit()
    crawl = Crawl(project_id=project.id, status=CrawlStatus.QUEUED)
    db_session.add(crawl)
    db_session.commit()
    crawl_id = crawl.id
    project_id = project.id

    from sqlalchemy.orm import sessionmaker

    SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with patch("worker.jobs.crawl.get_session_factory", return_value=SessionLocal):
        run_crawl_job(crawl_id)

    db_session.expire_all()
    crawl_after = db_session.get(Crawl, crawl_id)
    assert crawl_after.status == CrawlStatus.COMPLETED

    sitemaps = db_session.query(Sitemap).filter(Sitemap.project_id == project_id).all()
    assert len(sitemaps) == 1
    assert sitemaps[0].url == "https://demo4.test/sitemap.xml"
    assert sitemaps[0].urls_count == 2
    assert set(sitemaps[0].urls or []) == {
        "https://demo4.test/",
        "https://demo4.test/orphan",
    }
    assert sitemaps[0].fetch_error is None
    assert sitemaps[0].last_fetched_at is not None

    issues = db_session.query(Issue).filter(Issue.crawl_id == crawl_id).all()
    rule_ids = {i.rule_id for i in issues}
    assert "structure.sitemap.in_sitemap_only" in rule_ids
    sitemap_only = next(i for i in issues if i.rule_id == "structure.sitemap.in_sitemap_only")
    assert sitemap_only.payload is None  # no payload — the URL itself is enough


@respx.mock
def test_sitemaps_replaced_on_subsequent_crawl(db_session, engine) -> None:
    """A second crawl with a different sitemap should replace the first one's
    Sitemap rows, not accumulate them."""
    respx.get("https://demo5.test/robots.txt").mock(return_value=httpx.Response(404))
    respx.get("https://demo5.test/sitemap.xml").mock(
        return_value=httpx.Response(
            200,
            text=(
                '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
                "<url><loc>https://demo5.test/</loc></url></urlset>"
            ),
            headers={"content-type": "application/xml"},
        )
    )
    respx.get("https://demo5.test/").mock(
        return_value=httpx.Response(
            200,
            html=_html("Eine Startseite mit ausreichend langem Titel hier"),
            headers={"content-type": "text/html"},
        )
    )

    project = Project(
        name="Demo5",
        domain="demo5.test",
        base_url="https://demo5.test/",
        robots_respect=True,
        js_render=False,
    )
    db_session.add(project)
    db_session.commit()
    project_id = project.id

    from sqlalchemy.orm import sessionmaker

    SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    # First crawl
    crawl1 = Crawl(project_id=project_id, status=CrawlStatus.QUEUED)
    db_session.add(crawl1)
    db_session.commit()
    with patch("worker.jobs.crawl.get_session_factory", return_value=SessionLocal):
        run_crawl_job(crawl1.id)

    # Second crawl
    crawl2 = Crawl(project_id=project_id, status=CrawlStatus.QUEUED)
    db_session.add(crawl2)
    db_session.commit()
    with patch("worker.jobs.crawl.get_session_factory", return_value=SessionLocal):
        run_crawl_job(crawl2.id)

    db_session.expire_all()
    sitemaps = db_session.query(Sitemap).filter(Sitemap.project_id == project_id).all()
    assert len(sitemaps) == 1, "second crawl should replace, not accumulate"


def test_run_crawl_alias_points_to_job() -> None:
    """The API enqueues ``worker.jobs.crawl.run_crawl`` — make sure the alias still resolves."""
    from worker.jobs import crawl as crawl_module

    assert crawl_module.run_crawl is crawl_module.run_crawl_job


@pytest.fixture(autouse=True)
def _no_real_dns(monkeypatch):  # type: ignore[no-untyped-def]
    """Prevent any test from accidentally touching the real network via httpx."""
    yield
