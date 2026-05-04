"""Tests for the sitemaps list endpoint and the resources field on PageDetail."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from backend.app.models.crawl import Crawl, CrawlStatus
from backend.app.models.page import Page
from backend.app.models.project import Project
from backend.app.models.resource import Resource, ResourceType
from backend.app.models.sitemap import Sitemap


@pytest.fixture
def project_with_sitemaps(db_session) -> dict:
    project = Project(
        name="SmDemo",
        domain="sm.example",
        base_url="https://sm.example/",
        robots_respect=True,
        js_render=False,
    )
    db_session.add(project)
    db_session.commit()

    db_session.add_all(
        [
            Sitemap(
                project_id=project.id,
                url="https://sm.example/sitemap.xml",
                last_fetched_at=datetime.now(tz=timezone.utc),
                urls_count=42,
                urls=["https://sm.example/", "https://sm.example/about"],
                fetch_error=None,
            ),
            Sitemap(
                project_id=project.id,
                url="https://sm.example/sitemap-broken.xml.gz",
                urls_count=0,
                fetch_error="HTTP 404",
            ),
        ]
    )
    db_session.commit()
    return {"project_id": project.id}


def test_list_sitemaps_returns_all(client, auth_headers, project_with_sitemaps) -> None:
    pid = project_with_sitemaps["project_id"]
    resp = client.get(f"/api/projects/{pid}/sitemaps", headers=auth_headers)
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 2
    by_url = {s["url"]: s for s in items}
    assert by_url["https://sm.example/sitemap.xml"]["urls_count"] == 42
    assert by_url["https://sm.example/sitemap.xml"]["fetch_error"] is None
    assert by_url["https://sm.example/sitemap-broken.xml.gz"]["fetch_error"] == "HTTP 404"


def test_list_sitemaps_404_for_unknown_project(client, auth_headers) -> None:
    resp = client.get("/api/projects/9999/sitemaps", headers=auth_headers)
    assert resp.status_code == 404


def test_list_sitemaps_requires_auth(client, project_with_sitemaps) -> None:
    pid = project_with_sitemaps["project_id"]
    resp = client.get(f"/api/projects/{pid}/sitemaps")
    assert resp.status_code in (401, 403)


# ---- resources on page detail -------------------------------------------


def test_page_detail_includes_resources(client, auth_headers, db_session) -> None:
    project = Project(
        name="ResDemo",
        domain="res.example",
        base_url="https://res.example/",
        robots_respect=True,
        js_render=False,
    )
    db_session.add(project)
    db_session.commit()
    crawl = Crawl(project_id=project.id, status=CrawlStatus.COMPLETED, pages_crawled=1)
    db_session.add(crawl)
    db_session.commit()
    page = Page(
        crawl_id=crawl.id,
        url="https://res.example/",
        status_code=200,
        depth=0,
    )
    db_session.add(page)
    db_session.commit()

    db_session.add_all(
        [
            Resource(
                crawl_id=crawl.id,
                source_page_id=page.id,
                url="https://cdn.example/main.css",
                resource_type=ResourceType.STYLESHEET,
                is_internal=False,
                is_mixed_content=False,
                status_code=200,
            ),
            Resource(
                crawl_id=crawl.id,
                source_page_id=page.id,
                url="http://insecure.example/legacy.js",
                resource_type=ResourceType.SCRIPT,
                is_internal=False,
                is_mixed_content=True,
                status_code=200,
            ),
        ]
    )
    db_session.commit()

    resp = client.get(
        f"/api/projects/{project.id}/crawls/{crawl.id}/pages/{page.id}",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "resources" in data
    assert len(data["resources"]) == 2
    types = {r["resource_type"] for r in data["resources"]}
    assert types == {"stylesheet", "script"}
    mixed = next(r for r in data["resources"] if r["is_mixed_content"])
    assert mixed["url"] == "http://insecure.example/legacy.js"
