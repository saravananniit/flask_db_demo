"""JSON API blueprint: CRUD for tasks plus a live Server-Sent Events stream."""
import queue

from flask import Blueprint, Response, current_app, jsonify, request, url_for

from .db import get_db
from .errors import InvalidAPIUsage

bp = Blueprint("api", __name__, url_prefix="/api")

STATUSES = ("todo", "doing", "done")


def _row_to_dict(row) -> dict:
    return {
        "id": row["id"],
        "title": row["title"],
        "status": row["status"],
        "created": row["created"],
        "url": url_for("api.get_task", task_id=row["id"]),
    }


def _validate_title(value) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvalidAPIUsage("'title' must be a non-empty string")
    value = value.strip()
    if len(value) > 200:
        raise InvalidAPIUsage("'title' must be 200 characters or fewer")
    return value


def _fetch_or_404(task_id: int):
    row = get_db().execute("SELECT * FROM task WHERE id = ?", (task_id,)).fetchone()
    if row is None:
        raise InvalidAPIUsage("No such task", status_code=404)
    return row


def _publish(event: str, data: dict) -> None:
    current_app.extensions["broadcaster"].publish(event, data)


@bp.get("/tasks")
def list_tasks():
    status = request.args.get("status")
    if status is not None and status not in STATUSES:
        raise InvalidAPIUsage(f"'status' must be one of {', '.join(STATUSES)}")
    sql, args = "SELECT * FROM task", ()
    if status:
        sql, args = sql + " WHERE status = ?", (status,)
    rows = get_db().execute(sql + " ORDER BY id", args).fetchall()
    return [_row_to_dict(r) for r in rows]  # a list becomes JSON automatically


@bp.post("/tasks")
def create_task():
    body = request.get_json()  # 415 if not JSON, 400 if malformed
    if not isinstance(body, dict):
        raise InvalidAPIUsage("Body must be a JSON object")
    title = _validate_title(body.get("title"))
    db = get_db()
    cur = db.execute("INSERT INTO task (title) VALUES (?)", (title,))
    db.commit()
    task = _row_to_dict(_fetch_or_404(cur.lastrowid))
    _publish("task_created", task)
    return task, 201, {"Location": task["url"]}


@bp.get("/tasks/<int:task_id>")
def get_task(task_id):
    return _row_to_dict(_fetch_or_404(task_id))


@bp.patch("/tasks/<int:task_id>")
def update_task(task_id):
    body = request.get_json()
    if not isinstance(body, dict):
        raise InvalidAPIUsage("Body must be a JSON object")
    row = _fetch_or_404(task_id)
    title = _validate_title(body["title"]) if "title" in body else row["title"]
    status = body.get("status", row["status"])
    if status not in STATUSES:
        raise InvalidAPIUsage(f"'status' must be one of {', '.join(STATUSES)}")
    db = get_db()
    db.execute("UPDATE task SET title = ?, status = ? WHERE id = ?", (title, status, task_id))
    db.commit()
    task = _row_to_dict(_fetch_or_404(task_id))
    _publish("task_updated", task)
    return task


@bp.delete("/tasks/<int:task_id>")
def delete_task(task_id):
    _fetch_or_404(task_id)
    db = get_db()
    db.execute("DELETE FROM task WHERE id = ?", (task_id,))
    db.commit()
    _publish("task_deleted", {"id": task_id})
    return "", 204


@bp.get("/stream")
def stream():
    """Server-Sent Events: the browser's EventSource keeps this open."""
    broadcaster = current_app.extensions["broadcaster"]  # read request-bound data first

    def generate():
        q = broadcaster.subscribe()
        try:
            yield "retry: 3000\n\n"
            while True:
                try:
                    yield q.get(timeout=15)
                except queue.Empty:
                    yield ": keepalive\n\n"  # keeps proxies from closing the connection
        finally:
            broadcaster.unsubscribe(q)

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
