"""Tests for the GET /api/projects/dashboard endpoint."""

from __future__ import annotations

from backend.app.models.crawl import Crawl, CrawlStatus
from backend.app.models.project import Project


def _add_completed_crawl(db_session, project: Project, *, score_overall: float) -> Crawl:
    crawl = Crawl(
        project_id=project.id,
        status=CrawlStatus.COMPLETED,
        pages_crawled=1,
        score_overall=score_overall,
        score_tech=score_overall,
        score_struct=score_overall,
        score_content=score_overall,
    )
    db_session.add(crawl)
    db_session.commit()
    return crawl


def test_dashboard_empty_when_no_projects(client, auth_headers) -> None:
    resp = client.get("/api/projects/dashboard", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() == []


def test_dashboard_project_without_crawls(client, auth_headers, db_session) -> None:
    project = Project(
        name="Empty",
        domain="empty.example",
        base_url="https://empty.example/",
        robots_respect=True,
        js_render=False,
    )
    db_session.add(project)
    db_session.commit()

    resp = client.get("/api/projects/dashboard", headers=auth_headers)
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 1
    assert items[0]["project"]["name"] == "Empty"
    assert items[0]["latest_crawl"] is None
    assert items[0]["previous_crawl"] is None


def test_dashboard_returns_latest_and_previous(client, auth_headers, db_session) -> None:
    project = Project(
        name="Trend",
        domain="trend.example",
        base_url="https://trend.example/",
        robots_respect=True,
        js_render=False,
    )
    db_session.add(project)
    db_session.commit()

    _add_completed_crawl(db_session, project, score_overall=70.0)
    _add_completed_crawl(db_session, project, score_overall=80.0)
    latest = _add_completed_crawl(db_session, project, score_overall=85.0)

    resp = client.get("/api/projects/dashboard", headers=auth_headers)
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 1
    entry = items[0]
    assert entry["latest_crawl"]["id"] == latest.id
    assert entry["latest_crawl"]["score_overall"] == 85.0
    # previous = the one before that, not the oldest
    assert entry["previous_crawl"]["score_overall"] == 80.0


def test_dashboard_skips_non_completed_crawls(client, auth_headers, db_session) -> None:
    """Only completed crawls have meaningful scores — running/failed ones
    must not show up as 'latest'."""
    project = Project(
        name="Mixed",
        domain="mixed.example",
        base_url="https://mixed.example/",
        robots_respect=True,
        js_render=False,
    )
    db_session.add(project)
    db_session.commit()

    completed = _add_completed_crawl(db_session, project, score_overall=70.0)
    db_session.add(Crawl(project_id=project.id, status=CrawlStatus.RUNNING))
    db_session.add(Crawl(project_id=project.id, status=CrawlStatus.FAILED))
    db_session.commit()

    resp = client.get("/api/projects/dashboard", headers=auth_headers)
    items = resp.json()
    assert items[0]["latest_crawl"]["id"] == completed.id
    assert items[0]["previous_crawl"] is None


def test_dashboard_each_project_only_sees_its_own_crawls(client, auth_headers, db_session) -> None:
    p1 = Project(
        name="P1",
        domain="p1.example",
        base_url="https://p1.example/",
        robots_respect=True,
        js_render=False,
    )
    p2 = Project(
        name="P2",
        domain="p2.example",
        base_url="https://p2.example/",
        robots_respect=True,
        js_render=False,
    )
    db_session.add_all([p1, p2])
    db_session.commit()

    _add_completed_crawl(db_session, p1, score_overall=60.0)
    _add_completed_crawl(db_session, p2, score_overall=90.0)

    resp = client.get("/api/projects/dashboard", headers=auth_headers)
    items = {entry["project"]["name"]: entry for entry in resp.json()}
    assert items["P1"]["latest_crawl"]["score_overall"] == 60.0
    assert items["P2"]["latest_crawl"]["score_overall"] == 90.0
    assert items["P1"]["previous_crawl"] is None
    assert items["P2"]["previous_crawl"] is None


def test_dashboard_requires_auth(client) -> None:
    resp = client.get("/api/projects/dashboard")
    assert resp.status_code in (401, 403)
