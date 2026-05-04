"""Tests for the crawl-comparison service + endpoint and the CSV export."""

from __future__ import annotations

import csv
import io

import pytest

from backend.app.models.crawl import Crawl, CrawlStatus
from backend.app.models.issue import Issue, IssueCategory, IssueSeverity
from backend.app.models.page import Page
from backend.app.models.project import Project
from backend.app.services.comparison import build_comparison
from backend.app.services.reports import render_comparison_html


@pytest.fixture
def two_crawls(db_session) -> dict:
    """Two completed crawls of the same project, with overlapping issue sets
    so the diff has new/resolved/persistent buckets to populate."""
    project = Project(
        name="DiffDemo",
        domain="diff.example",
        base_url="https://diff.example/",
        robots_respect=True,
        js_render=False,
    )
    db_session.add(project)
    db_session.commit()

    crawl_a = Crawl(
        project_id=project.id,
        status=CrawlStatus.COMPLETED,
        pages_crawled=2,
        score_tech=70.0,
        score_struct=80.0,
        score_content=60.0,
        score_overall=70.0,
    )
    crawl_b = Crawl(
        project_id=project.id,
        status=CrawlStatus.COMPLETED,
        pages_crawled=3,
        score_tech=85.0,
        score_struct=80.0,
        score_content=75.0,
        score_overall=80.0,
    )
    db_session.add_all([crawl_a, crawl_b])
    db_session.commit()

    home_a = Page(
        crawl_id=crawl_a.id,
        url="https://diff.example/",
        status_code=200,
        depth=0,
    )
    about_a = Page(
        crawl_id=crawl_a.id,
        url="https://diff.example/about",
        status_code=200,
        depth=1,
    )
    home_b = Page(
        crawl_id=crawl_b.id,
        url="https://diff.example/",
        status_code=200,
        depth=0,
    )
    about_b = Page(
        crawl_id=crawl_b.id,
        url="https://diff.example/about",
        status_code=200,
        depth=1,
    )
    contact_b = Page(
        crawl_id=crawl_b.id,
        url="https://diff.example/contact",
        status_code=200,
        depth=1,
    )
    db_session.add_all([home_a, about_a, home_b, about_b, contact_b])
    db_session.commit()

    # Crawl A: title missing on home, alt missing on about, structure depth on home
    db_session.add_all(
        [
            Issue(
                crawl_id=crawl_a.id,
                page_id=home_a.id,
                rule_id="meta.title.missing",
                category=IssueCategory.TECH_META,
                severity=IssueSeverity.CRITICAL,
                payload={},
            ),
            Issue(
                crawl_id=crawl_a.id,
                page_id=about_a.id,
                rule_id="content.image.alt_missing",
                category=IssueCategory.TECH_META,
                severity=IssueSeverity.IMPORTANT,
                payload={"count": 1},
            ),
            Issue(
                crawl_id=crawl_a.id,
                page_id=home_a.id,
                rule_id="structure.depth.deep",
                category=IssueCategory.STRUCTURE,
                severity=IssueSeverity.TIP,
                payload={"depth": 3},
            ),
        ]
    )
    # Crawl B:
    # - same alt-missing on /about → persistent
    # - new noindex tip on /contact → new
    # - title.missing GONE → resolved
    # - structure.depth.deep GONE → resolved
    db_session.add_all(
        [
            Issue(
                crawl_id=crawl_b.id,
                page_id=about_b.id,
                rule_id="content.image.alt_missing",
                category=IssueCategory.TECH_META,
                severity=IssueSeverity.IMPORTANT,
                payload={"count": 1},
            ),
            Issue(
                crawl_id=crawl_b.id,
                page_id=contact_b.id,
                rule_id="meta.robots.noindex",
                category=IssueCategory.TECH_META,
                severity=IssueSeverity.TIP,
                payload={"directives": ["noindex"]},
            ),
        ]
    )
    db_session.commit()

    return {
        "project_id": project.id,
        "project": project,
        "crawl_a": crawl_a,
        "crawl_b": crawl_b,
    }


# ---- comparison service --------------------------------------------------


def test_comparison_buckets_findings(db_session, two_crawls) -> None:
    ctx = build_comparison(
        db_session, two_crawls["project"], two_crawls["crawl_a"], two_crawls["crawl_b"]
    )
    tech = next(c for c in ctx.categories if c.category == IssueCategory.TECH_META)

    new_rules = {f.rule_id for f in tech.new}
    resolved_rules = {f.rule_id for f in tech.resolved}
    persistent_rules = {f.rule_id for f in tech.persistent}

    assert "meta.robots.noindex" in new_rules  # only in B
    assert "meta.title.missing" in resolved_rules  # only in A
    assert "content.image.alt_missing" in persistent_rules  # in both


def test_comparison_resolved_includes_other_categories(db_session, two_crawls) -> None:
    """structure.depth.deep was in A only — must show up in the structure
    bucket of resolved findings."""
    ctx = build_comparison(
        db_session, two_crawls["project"], two_crawls["crawl_a"], two_crawls["crawl_b"]
    )
    structure = next(c for c in ctx.categories if c.category == IssueCategory.STRUCTURE)
    resolved_rules = {f.rule_id for f in structure.resolved}
    assert "structure.depth.deep" in resolved_rules


def test_comparison_score_deltas(db_session, two_crawls) -> None:
    ctx = build_comparison(
        db_session, two_crawls["project"], two_crawls["crawl_a"], two_crawls["crawl_b"]
    )
    assert ctx.overall_delta == 10.0
    tech = next(c for c in ctx.categories if c.category == IssueCategory.TECH_META)
    assert tech.score_delta == 15.0


def test_comparison_pages_count(db_session, two_crawls) -> None:
    ctx = build_comparison(
        db_session, two_crawls["project"], two_crawls["crawl_a"], two_crawls["crawl_b"]
    )
    assert ctx.pages_a == 2
    assert ctx.pages_b == 3


def test_comparison_renders_html(db_session, two_crawls) -> None:
    ctx = build_comparison(
        db_session, two_crawls["project"], two_crawls["crawl_a"], two_crawls["crawl_b"]
    )
    html = render_comparison_html(ctx)
    assert "DiffDemo" in html
    # Score delta display
    assert "+10" in html  # overall delta
    # All three buckets headed
    assert "Neue Findings" in html
    assert "Behobene Findings" in html
    # Specific rule references
    assert "meta.title.missing" in html  # resolved bucket
    assert "meta.robots.noindex" in html  # new bucket
    assert "content.image.alt_missing" in html  # persistent


# ---- comparison endpoint -------------------------------------------------


def test_compare_endpoint_returns_html(client, auth_headers, two_crawls) -> None:
    pid = two_crawls["project_id"]
    a = two_crawls["crawl_a"].id
    b = two_crawls["crawl_b"].id
    resp = client.get(
        f"/api/projects/{pid}/crawls/{b}/compare/{a}.html",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    body = resp.text
    assert "<!doctype html>" in body.lower()
    assert "DiffDemo" in body


def test_compare_endpoint_orders_chronologically_regardless_of_url(
    client, auth_headers, two_crawls
) -> None:
    """Whether the user picks A→B or B→A in the URL, the comparison should
    always treat the older crawl as 'before'."""
    pid = two_crawls["project_id"]
    a = two_crawls["crawl_a"].id
    b = two_crawls["crawl_b"].id

    # Both directions
    r1 = client.get(f"/api/projects/{pid}/crawls/{a}/compare/{b}.html", headers=auth_headers)
    r2 = client.get(f"/api/projects/{pid}/crawls/{b}/compare/{a}.html", headers=auth_headers)
    assert r1.status_code == 200 and r2.status_code == 200
    # Same body — order normalised
    assert r1.text == r2.text


def test_compare_endpoint_400_for_self_comparison(client, auth_headers, two_crawls) -> None:
    pid = two_crawls["project_id"]
    a = two_crawls["crawl_a"].id
    resp = client.get(f"/api/projects/{pid}/crawls/{a}/compare/{a}.html", headers=auth_headers)
    assert resp.status_code == 400


def test_compare_endpoint_404_for_other_project_crawl(
    client, auth_headers, two_crawls, db_session
) -> None:
    other_project = Project(
        name="Other",
        domain="other.example",
        base_url="https://other.example/",
        robots_respect=True,
        js_render=False,
    )
    db_session.add(other_project)
    db_session.commit()
    other_crawl = Crawl(project_id=other_project.id, status=CrawlStatus.COMPLETED, pages_crawled=0)
    db_session.add(other_crawl)
    db_session.commit()

    pid = two_crawls["project_id"]
    a = two_crawls["crawl_a"].id
    resp = client.get(
        f"/api/projects/{pid}/crawls/{a}/compare/{other_crawl.id}.html",
        headers=auth_headers,
    )
    assert resp.status_code == 404


def test_compare_endpoint_requires_auth(client, two_crawls) -> None:
    pid = two_crawls["project_id"]
    a = two_crawls["crawl_a"].id
    b = two_crawls["crawl_b"].id
    resp = client.get(f"/api/projects/{pid}/crawls/{a}/compare/{b}.html")
    assert resp.status_code in (401, 403)


# ---- CSV export ----------------------------------------------------------


def test_csv_export_returns_csv_with_bom(client, auth_headers, two_crawls) -> None:
    pid = two_crawls["project_id"]
    cid = two_crawls["crawl_b"].id
    resp = client.get(f"/api/projects/{pid}/crawls/{cid}/issues.csv", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert resp.headers["content-disposition"].startswith("attachment")
    assert "issues-diff.example" in resp.headers["content-disposition"]

    content = resp.content
    # UTF-8 BOM up front so Excel auto-detects encoding for German umlauts
    assert content.startswith(b"\xef\xbb\xbf")

    decoded = content.decode("utf-8-sig")  # strip BOM transparently
    rows = list(csv.reader(io.StringIO(decoded)))
    header = rows[0]
    assert header == [
        "issue_id",
        "rule_id",
        "category",
        "severity",
        "page_url",
        "page_id",
        "payload",
        "created_at",
    ]
    # One body row per Crawl-B issue (2)
    assert len(rows) - 1 == 2
    body_rule_ids = {row[1] for row in rows[1:]}
    assert body_rule_ids == {"content.image.alt_missing", "meta.robots.noindex"}


def test_csv_export_payload_is_json(client, auth_headers, two_crawls) -> None:
    """Payload column must be JSON so non-ASCII content survives Excel."""
    import json

    pid = two_crawls["project_id"]
    cid = two_crawls["crawl_b"].id
    resp = client.get(f"/api/projects/{pid}/crawls/{cid}/issues.csv", headers=auth_headers)
    decoded = resp.content.decode("utf-8-sig")
    rows = list(csv.reader(io.StringIO(decoded)))
    by_rule = {row[1]: row for row in rows[1:]}
    payload_str = by_rule["content.image.alt_missing"][6]
    assert json.loads(payload_str) == {"count": 1}


def test_csv_export_404_for_unknown_crawl(client, auth_headers, two_crawls) -> None:
    pid = two_crawls["project_id"]
    resp = client.get(f"/api/projects/{pid}/crawls/9999/issues.csv", headers=auth_headers)
    assert resp.status_code == 404


def test_csv_export_requires_auth(client, two_crawls) -> None:
    pid = two_crawls["project_id"]
    cid = two_crawls["crawl_b"].id
    resp = client.get(f"/api/projects/{pid}/crawls/{cid}/issues.csv")
    assert resp.status_code in (401, 403)
