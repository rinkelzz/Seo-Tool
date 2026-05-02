"""Tests for project CRUD endpoints."""


def test_auth_required(client) -> None:
    resp = client.get("/api/projects")
    assert resp.status_code == 401


def test_create_and_get_project(client, auth_headers) -> None:
    payload = {
        "name": "Lapalutschi",
        "domain": "lapalutschi.example",
        "base_url": "https://lapalutschi.example/",
    }
    resp = client.post("/api/projects", json=payload, headers=auth_headers)
    assert resp.status_code == 201, resp.text
    created = resp.json()
    assert created["id"] > 0
    assert created["name"] == "Lapalutschi"
    assert created["domain"] == "lapalutschi.example"
    assert created["robots_respect"] is True

    # GET single
    resp = client.get(f"/api/projects/{created['id']}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == created["id"]

    # LIST
    resp = client.get("/api/projects", headers=auth_headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_duplicate_domain_returns_409(client, auth_headers) -> None:
    payload = {
        "name": "A",
        "domain": "dup.example",
        "base_url": "https://dup.example/",
    }
    assert client.post("/api/projects", json=payload, headers=auth_headers).status_code == 201
    payload["name"] = "B"
    resp = client.post("/api/projects", json=payload, headers=auth_headers)
    assert resp.status_code == 409


def test_update_project(client, auth_headers) -> None:
    create = client.post(
        "/api/projects",
        json={"name": "Old", "domain": "edit.example", "base_url": "https://edit.example/"},
        headers=auth_headers,
    ).json()

    resp = client.patch(
        f"/api/projects/{create['id']}",
        json={"name": "New"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "New"


def test_delete_project(client, auth_headers) -> None:
    create = client.post(
        "/api/projects",
        json={"name": "Gone", "domain": "delete.example", "base_url": "https://delete.example/"},
        headers=auth_headers,
    ).json()

    resp = client.delete(f"/api/projects/{create['id']}", headers=auth_headers)
    assert resp.status_code == 204

    resp = client.get(f"/api/projects/{create['id']}", headers=auth_headers)
    assert resp.status_code == 404


def test_get_missing_project_returns_404(client, auth_headers) -> None:
    resp = client.get("/api/projects/9999", headers=auth_headers)
    assert resp.status_code == 404
