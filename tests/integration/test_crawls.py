"""Tests for the crawl-trigger endpoint.

We don't want the test to actually push to Redis, so we monkeypatch the queue.
"""

from unittest.mock import MagicMock


def test_trigger_crawl_creates_queued_record(client, auth_headers, monkeypatch) -> None:
    # Replace the RQ queue so no Redis connection is opened.
    fake_queue = MagicMock()
    monkeypatch.setattr(
        "backend.app.api.crawls.get_crawl_queue",
        lambda: fake_queue,
    )

    project = client.post(
        "/api/projects",
        json={"name": "X", "domain": "crawl.example", "base_url": "https://crawl.example/"},
        headers=auth_headers,
    ).json()

    resp = client.post(f"/api/projects/{project['id']}/crawls", headers=auth_headers)
    assert resp.status_code == 201, resp.text
    crawl = resp.json()
    assert crawl["status"] == "queued"
    assert crawl["pages_crawled"] == 0

    fake_queue.enqueue.assert_called_once()
    call_args = fake_queue.enqueue.call_args
    assert call_args.args[0] == "worker.jobs.crawl.run_crawl"
    assert call_args.args[1] == crawl["id"]


def test_trigger_crawl_for_missing_project_returns_404(client, auth_headers) -> None:
    resp = client.post("/api/projects/9999/crawls", headers=auth_headers)
    assert resp.status_code == 404


def test_list_crawls_empty(client, auth_headers) -> None:
    project = client.post(
        "/api/projects",
        json={"name": "Y", "domain": "list.example", "base_url": "https://list.example/"},
        headers=auth_headers,
    ).json()

    resp = client.get(f"/api/projects/{project['id']}/crawls", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() == []
