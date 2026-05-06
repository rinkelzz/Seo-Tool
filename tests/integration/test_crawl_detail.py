"""Tests for the new crawl-detail, summary, issues-list, pages-list, page-detail endpoints."""

from __future__ import annotations

import pytest

from backend.app.models.crawl import Crawl, CrawlStatus
from backend.app.models.image import Image
from backend.app.models.issue import Issue, IssueCategory, IssueSeverity
from backend.app.models.link import Link
from backend.app.models.page import Page
from backend.app.models.project import Project


@pytest.fixture
def seeded_crawl(db_session) -> dict:
    """Build a project with one completed crawl, two pages, a few issues + links."""
    project = Project(
        name="Demo",
        domain="demo.example",
        base_url="https://demo.example/",
        robots_respect=True,
        js_render=False,
    )
    db_session.add(project)
    db_session.commit()

    crawl = Crawl(
        project_id=project.id,
        status=CrawlStatus.COMPLETED,
        pages_crawled=2,
        score_tech=85.5,
        score_struct=70.0,
        score_content=100.0,
        score_overall=85.17,
    )
    db_session.add(crawl)
    db_session.commit()

    home = Page(
        crawl_id=crawl.id,
        url="https://demo.example/",
        status_code=200,
        response_time_ms=120,
        title="Startseite",
        meta_description="Beschreibung",
        h1="Hauptüberschrift",
        language="de",
        word_count=300,
        depth=0,
        is_indexable=True,
    )
    about = Page(
        crawl_id=crawl.id,
        url="https://demo.example/about",
        status_code=200,
        response_time_ms=200,
        title="Über uns",
        depth=1,
        is_indexable=True,
        canonical_url="https://demo.example/about",
        redirect_chain=["https://demo.example/about-old"],
    )
    db_session.add_all([home, about])
    db_session.commit()

    db_session.add_all(
        [
            Image(page_id=about.id, src="/x.png", alt=None, has_alt=False),
            Link(
                crawl_id=crawl.id,
                source_page_id=home.id,
                target_url="https://demo.example/about",
                anchor_text="About",
                is_internal=True,
                is_followed=True,
            ),
            Link(
                crawl_id=crawl.id,
                source_page_id=about.id,
                target_url="https://other.example/x",
                anchor_text="ext",
                is_internal=False,
                is_followed=True,
                target_status_code=404,
            ),
        ]
    )
    # Issues: 1 critical (tech), 1 important (tech), 2 tip (structure)
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
                payload={"count": 1},
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
                rule_id="structure.external_link.broken",
                category=IssueCategory.STRUCTURE,
                severity=IssueSeverity.IMPORTANT,
                payload={"target": "https://other.example/x", "status_code": 404},
            ),
        ]
    )
    db_session.commit()

    return {
        "project_id": project.id,
        "crawl_id": crawl.id,
        "home_id": home.id,
        "about_id": about.id,
    }


# --- crawl detail + summary ---


def test_get_crawl_returns_scores(client, auth_headers, seeded_crawl) -> None:
    resp = client.get(
        f"/api/projects/{seeded_crawl['project_id']}/crawls/{seeded_crawl['crawl_id']}",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "completed"
    assert data["score_overall"] == 85.17


def test_get_crawl_404_for_wrong_project(client, auth_headers, seeded_crawl) -> None:
    resp = client.get(f"/api/projects/9999/crawls/{seeded_crawl['crawl_id']}", headers=auth_headers)
    assert resp.status_code == 404


def test_get_summary_groups_by_category_and_severity(client, auth_headers, seeded_crawl) -> None:
    resp = client.get(
        f"/api/projects/{seeded_crawl['project_id']}/crawls/{seeded_crawl['crawl_id']}/summary",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 4
    assert data["by_category"]["tech_meta"] == 2
    assert data["by_category"]["structure"] == 2
    assert data["by_severity"]["critical"] == 1
    assert data["by_severity"]["important"] == 2
    assert data["by_severity"]["tip"] == 1
    assert len(data["by_rule"]) == 4


# --- issues list ---


def test_list_issues_paginated(client, auth_headers, seeded_crawl) -> None:
    resp = client.get(
        f"/api/projects/{seeded_crawl['project_id']}/crawls/{seeded_crawl['crawl_id']}/issues",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 4
    assert len(data["items"]) == 4
    assert data["limit"] == 50


def test_list_issues_filter_by_severity(client, auth_headers, seeded_crawl) -> None:
    resp = client.get(
        f"/api/projects/{seeded_crawl['project_id']}/crawls/{seeded_crawl['crawl_id']}/issues",
        headers=auth_headers,
        params={"severity": "critical"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["rule_id"] == "meta.title.missing"


def test_list_issues_filter_by_category(client, auth_headers, seeded_crawl) -> None:
    resp = client.get(
        f"/api/projects/{seeded_crawl['project_id']}/crawls/{seeded_crawl['crawl_id']}/issues",
        headers=auth_headers,
        params={"category": "structure"},
    )
    assert resp.status_code == 200
    assert resp.json()["total"] == 2


def test_list_issues_filter_by_page_id(client, auth_headers, seeded_crawl) -> None:
    resp = client.get(
        f"/api/projects/{seeded_crawl['project_id']}/crawls/{seeded_crawl['crawl_id']}/issues",
        headers=auth_headers,
        params={"page_id": seeded_crawl["about_id"]},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    rule_ids = {item["rule_id"] for item in data["items"]}
    assert rule_ids == {"content.image.alt_missing", "structure.external_link.broken"}


def test_list_issues_pagination(client, auth_headers, seeded_crawl) -> None:
    resp = client.get(
        f"/api/projects/{seeded_crawl['project_id']}/crawls/{seeded_crawl['crawl_id']}/issues",
        headers=auth_headers,
        params={"limit": 2, "offset": 0},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 4
    assert len(data["items"]) == 2
    assert data["limit"] == 2


def test_list_issues_q_substring_filter(client, auth_headers, seeded_crawl) -> None:
    """q is a case-insensitive substring match against rule_id."""
    resp = client.get(
        f"/api/projects/{seeded_crawl['project_id']}/crawls/{seeded_crawl['crawl_id']}/issues",
        headers=auth_headers,
        params={"q": "structure"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    rule_ids = {item["rule_id"] for item in data["items"]}
    assert rule_ids == {"structure.depth.deep", "structure.external_link.broken"}


def test_list_issues_q_is_case_insensitive(client, auth_headers, seeded_crawl) -> None:
    resp = client.get(
        f"/api/projects/{seeded_crawl['project_id']}/crawls/{seeded_crawl['crawl_id']}/issues",
        headers=auth_headers,
        params={"q": "TITLE"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["rule_id"] == "meta.title.missing"


def test_list_issues_q_no_match_returns_empty(client, auth_headers, seeded_crawl) -> None:
    resp = client.get(
        f"/api/projects/{seeded_crawl['project_id']}/crawls/{seeded_crawl['crawl_id']}/issues",
        headers=auth_headers,
        params={"q": "this-does-not-match-any-rule"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0
    assert data["items"] == []


def test_list_issues_q_combines_with_severity_filter(client, auth_headers, seeded_crawl) -> None:
    """q + severity should AND together (only structure rules with important
    severity, which is just the broken-external-link finding)."""
    resp = client.get(
        f"/api/projects/{seeded_crawl['project_id']}/crawls/{seeded_crawl['crawl_id']}/issues",
        headers=auth_headers,
        params={"q": "structure", "severity": "important"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["rule_id"] == "structure.external_link.broken"


# --- pages list ---


def test_list_pages_returns_all(client, auth_headers, seeded_crawl) -> None:
    resp = client.get(
        f"/api/projects/{seeded_crawl['project_id']}/crawls/{seeded_crawl['crawl_id']}/pages",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert {p["url"] for p in data["items"]} == {
        "https://demo.example/",
        "https://demo.example/about",
    }


def test_list_pages_filter_has_issues(client, auth_headers, seeded_crawl) -> None:
    # Both seeded pages have issues — filter has_issues=true should still return both
    resp = client.get(
        f"/api/projects/{seeded_crawl['project_id']}/crawls/{seeded_crawl['crawl_id']}/pages",
        headers=auth_headers,
        params={"has_issues": "true"},
    )
    assert resp.status_code == 200
    assert resp.json()["total"] == 2


# --- page detail ---


def test_get_page_returns_full_detail(client, auth_headers, seeded_crawl) -> None:
    resp = client.get(
        f"/api/projects/{seeded_crawl['project_id']}/crawls/{seeded_crawl['crawl_id']}/pages/{seeded_crawl['about_id']}",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["url"] == "https://demo.example/about"
    assert data["canonical_url"] == "https://demo.example/about"
    assert data["redirect_chain"] == ["https://demo.example/about-old"]
    assert len(data["images"]) == 1
    assert data["images"][0]["has_alt"] is False
    assert len(data["links"]) == 1
    assert data["links"][0]["target_status_code"] == 404
    issue_rule_ids = {i["rule_id"] for i in data["issues"]}
    assert issue_rule_ids == {"content.image.alt_missing", "structure.external_link.broken"}


def test_get_page_404_for_wrong_crawl(client, auth_headers, seeded_crawl) -> None:
    resp = client.get(
        f"/api/projects/{seeded_crawl['project_id']}/crawls/9999/pages/{seeded_crawl['about_id']}",
        headers=auth_headers,
    )
    assert resp.status_code == 404
