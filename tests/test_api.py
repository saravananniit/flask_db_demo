def test_index_and_health(client):
    assert client.get("/").status_code == 200
    assert client.get("/healthz").json == {"status": "ok"}


def test_security_headers_and_request_id(client):
    res = client.get("/healthz", headers={"X-Request-ID": "abc123"})
    assert res.headers["X-Request-ID"] == "abc123"
    assert res.headers["X-Content-Type-Options"] == "nosniff"
    assert "default-src 'self'" in res.headers["Content-Security-Policy"]


def test_create_list_update_delete(client):
    res = client.post("/api/tasks", json={"title": "  write guide  "})
    assert res.status_code == 201
    task = res.json
    assert task["title"] == "write guide"
    assert task["status"] == "todo"
    assert res.headers["Location"].endswith(f"/api/tasks/{task['id']}")

    assert [t["id"] for t in client.get("/api/tasks").json] == [task["id"]]

    res = client.patch(f"/api/tasks/{task['id']}", json={"status": "done"})
    assert res.json["status"] == "done"
    assert client.get("/api/tasks?status=todo").json == []
    assert len(client.get("/api/tasks?status=done").json) == 1

    assert client.delete(f"/api/tasks/{task['id']}").status_code == 204
    assert client.get(f"/api/tasks/{task['id']}").status_code == 404


def test_validation_errors_are_json(client):
    res = client.post("/api/tasks", json={"title": ""})
    assert res.status_code == 400
    assert "title" in res.json["error"]

    res = client.post("/api/tasks", json={"title": "x" * 201})
    assert res.status_code == 400

    task = client.post("/api/tasks", json={"title": "ok"}).json
    res = client.patch(f"/api/tasks/{task['id']}", json={"status": "nope"})
    assert res.status_code == 400

    assert client.get("/api/tasks?status=nope").status_code == 400


def test_non_json_and_bad_json(client):
    res = client.post("/api/tasks", data="title=x")
    assert res.status_code == 415
    assert res.is_json  # error is JSON because the path starts with /api/

    res = client.post("/api/tasks", data="{bad", content_type="application/json")
    assert res.status_code == 400
    assert res.is_json


def test_unknown_api_route_is_json_404_but_html_elsewhere(client):
    res = client.get("/api/nope")
    assert res.status_code == 404 and res.is_json
    res = client.get("/nope")
    assert res.status_code == 404 and not res.is_json


def test_body_size_limit(client):
    res = client.post("/api/tasks", json={"title": "x", "pad": "y" * 20000})
    assert res.status_code == 413


def test_events_are_published(app, client):
    q = app.extensions["broadcaster"].subscribe()
    task = client.post("/api/tasks", json={"title": "live"}).json
    client.patch(f"/api/tasks/{task['id']}", json={"status": "doing"})
    client.delete(f"/api/tasks/{task['id']}")
    events = [q.get_nowait().splitlines()[0] for _ in range(3)]
    assert events == [
        "event: task_created",
        "event: task_updated",
        "event: task_deleted",
    ]


def test_init_db_cli(runner):
    result = runner.invoke(args="init-db")
    assert "Database ready" in result.output
