"""Tests for the report service + ``/report.html`` endpoint."""

from __future__ import annotations

import pytest

from backend.app.models.crawl import Crawl, CrawlStatus
from backend.app.models.issue import Issue, IssueCategory, IssueSeverity
from backend.app.models.page import Page
from backend.app.models.project import Project
from backend.app.services.reports import build_context, render_html


@pytest.fixture
def seeded_crawl(db_session) -> dict:
    """One project, one completed crawl, two pages, a handful of issues
    spanning all three categories and severities."""
    project = Project(
        name="ReportDemo",
        domain="report.example",
        base_url="https://report.example/",
        robots_respect=True,
        js_render=False,
    )
    db_session.add(project)
    db_session.commit()

    crawl = Crawl(
        project_id=project.id,
        status=CrawlStatus.COMPLETED,
        pages_crawled=2,
        score_tech=72.5,
        score_struct=85.0,
        score_content=55.0,
        score_overall=70.83,
    )
    db_session.add(crawl)
    db_session.commit()

    home = Page(
        crawl_id=crawl.id,
        url="https://report.example/",
        status_code=200,
        title="Startseite",
        h1="Heading",
        depth=0,
        is_indexable=True,
    )
    about = Page(
        crawl_id=crawl.id,
        url="https://report.example/about",
        status_code=200,
        title="Über uns",
        depth=1,
        is_indexable=True,
    )
    db_session.add_all([home, about])
    db_session.commit()

    db_session.add_all(
        [
            Issue(
                crawl_id=crawl.id,
                page_id=home.id,
                rule_id="meta.title.missing",
                category=IssueCategory.TECH_META,
                severity=IssueSeverity.CRITICAL,
                payload={},
            ),
            Issue(
                crawl_id=crawl.id,
                page_id=about.id,
                rule_id="content.image.alt_missing",
                category=IssueCategory.TECH_META,
                severity=IssueSeverity.IMPORTANT,
                payload={"count": 3},
            ),
            Issue(
                crawl_id=crawl.id,
                page_id=home.id,
                rule_id="structure.depth.deep",
                category=IssueCategory.STRUCTURE,
                severity=IssueSeverity.TIP,
                payload={"depth": 3},
            ),
            Issue(
                crawl_id=crawl.id,
                page_id=about.id,
                rule_id="content.thin",
                category=IssueCategory.CONTENT,
                severity=IssueSeverity.IMPORTANT,
                payload={"word_count": 30},
            ),
        ]
    )
    db_session.commit()

    return {
        "project_id": project.id,
        "crawl_id": crawl.id,
        "project": project,
        "crawl": crawl,
    }


# ---- service layer -------------------------------------------------------


def test_build_context_groups_findings_by_category(db_session, seeded_crawl) -> None:
    ctx = build_context(db_session, seeded_crawl["project"], seeded_crawl["crawl"])

    assert ctx.pages_count == 2
    assert ctx.by_severity[IssueSeverity.CRITICAL] == 1
    assert ctx.by_severity[IssueSeverity.IMPORTANT] == 2
    assert ctx.by_severity[IssueSeverity.TIP] == 1

    by_cat = {c.category: c for c in ctx.categories}
    assert by_cat[IssueCategory.TECH_META].total_findings == 2
    assert by_cat[IssueCategory.STRUCTURE].total_findings == 1
    assert by_cat[IssueCategory.CONTENT].total_findings == 1


def test_build_context_orders_rules_by_severity_then_count(db_session, seeded_crawl) -> None:
    ctx = build_context(db_session, seeded_crawl["project"], seeded_crawl["crawl"])
    tech = next(c for c in ctx.categories if c.category == IssueCategory.TECH_META)
    severities = [r.severity for r in tech.rules_with_findings]
    # critical must come before important
    assert severities[0] == IssueSeverity.CRITICAL
    assert IssueSeverity.IMPORTANT in severities[1:]


def test_build_context_lists_passing_rules(db_session, seeded_crawl) -> None:
    ctx = build_context(db_session, seeded_crawl["project"], seeded_crawl["crawl"])
    tech = next(c for c in ctx.categories if c.category == IssueCategory.TECH_META)
    # The seed only triggered 2 tech rules — rest should be in "passing"
    assert len(tech.rules_passing) > 0
    assert "meta.title.missing" not in tech.rules_passing  # this one was triggered


def test_build_context_caps_examples_per_rule(db_session) -> None:
    project = Project(
        name="Many",
        domain="many.example",
        base_url="https://many.example/",
        robots_respect=True,
        js_render=False,
    )
    db_session.add(project)
    db_session.commit()
    crawl = Crawl(project_id=project.id, status=CrawlStatus.COMPLETED, pages_crawled=10)
    db_session.add(crawl)
    db_session.commit()

    pages = []
    for i in range(10):
        p = Page(
            crawl_id=crawl.id,
            url=f"https://many.example/p{i}",
            status_code=200,
            title="x",
            depth=1,
        )
        pages.append(p)
    db_session.add_all(pages)
    db_session.commit()

    db_session.add_all(
        [
            Issue(
                crawl_id=crawl.id,
                page_id=p.id,
                rule_id="meta.title.missing",
                category=IssueCategory.TECH_META,
                severity=IssueSeverity.CRITICAL,
                payload={},
            )
            for p in pages
        ]
    )
    db_session.commit()

    ctx = build_context(db_session, project, crawl, examples_per_rule=5)
    tech = next(c for c in ctx.categories if c.category == IssueCategory.TECH_META)
    rule = next(r for r in tech.rules_with_findings if r.rule_id == "meta.title.missing")
    assert rule.count == 10
    assert len(rule.examples) == 5


def test_render_html_includes_core_pieces(db_session, seeded_crawl) -> None:
    ctx = build_context(db_session, seeded_crawl["project"], seeded_crawl["crawl"])
    html = render_html(ctx)

    # Header
    assert "ReportDemo" in html
    assert "https://report.example/" in html
    # Severity ribbon
    assert "Sehr wichtig" in html
    assert "Tipp" in html
    # Category sections
    assert "Technik &amp; Meta" in html or "Technik & Meta" in html
    assert "Struktur" in html
    assert "Inhalt" in html
    # Specific rule appears
    assert "meta.title.missing" in html
    # A specific example URL is rendered
    assert "https://report.example/about" in html
    # Score formatting
    assert "70%" in html or "70.83" in html or "71%" in html  # overall


def test_render_html_handles_zero_findings(db_session) -> None:
    project = Project(
        name="Clean",
        domain="clean.example",
        base_url="https://clean.example/",
        robots_respect=True,
        js_render=False,
    )
    db_session.add(project)
    db_session.commit()
    crawl = Crawl(
        project_id=project.id,
        status=CrawlStatus.COMPLETED,
        pages_crawled=1,
        score_tech=100.0,
        score_struct=100.0,
        score_content=100.0,
        score_overall=100.0,
    )
    db_session.add(crawl)
    db_session.commit()

    ctx = build_context(db_session, project, crawl)
    html = render_html(ctx)
    # Empty-state messages from the template
    assert "Keine Findings" in html
    assert "100%" in html


# ---- HTTP endpoint -------------------------------------------------------


def test_report_endpoint_returns_html(client, auth_headers, seeded_crawl) -> None:
    resp = client.get(
        f"/api/projects/{seeded_crawl['project_id']}/crawls/{seeded_crawl['crawl_id']}/report.html",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    body = resp.text
    assert "<!doctype html>" in body.lower()
    assert "ReportDemo" in body
    assert "meta.title.missing" in body


def test_report_endpoint_404_for_wrong_project(client, auth_headers, seeded_crawl) -> None:
    resp = client.get(
        f"/api/projects/9999/crawls/{seeded_crawl['crawl_id']}/report.html",
        headers=auth_headers,
    )
    assert resp.status_code == 404


def test_report_endpoint_404_for_crawl_in_different_project(
    client, auth_headers, seeded_crawl, db_session
) -> None:
    other = Project(
        name="Other",
        domain="other.example",
        base_url="https://other.example/",
        robots_respect=True,
        js_render=False,
    )
    db_session.add(other)
    db_session.commit()
    resp = client.get(
        f"/api/projects/{other.id}/crawls/{seeded_crawl['crawl_id']}/report.html",
        headers=auth_headers,
    )
    assert resp.status_code == 404


def test_report_endpoint_requires_auth(client, seeded_crawl) -> None:
    resp = client.get(
        f"/api/projects/{seeded_crawl['project_id']}/crawls/{seeded_crawl['crawl_id']}/report.html"
    )
    assert resp.status_code in (401, 403)
