# Flask for Real-Time Projects: Practical Guide

Based on the Flask 3.1.x documentation (https://flask.palletsprojects.com/en/stable/), with a tested demo app (`flask_realtime_demo/`) that implements every pattern below.

**How to use this guide:** read sections 1 to 9 once, then open the demo and follow the code alongside section 12. Each section ends with the docs page to read next.

> "Real-time projects" here means two things: (a) production-style Flask apps (APIs, dashboards, internal tools) and (b) live-updating features such as notifications and progress feeds. The Flask docs cover (a) in depth; for (b) they give you streaming responses, background tasks and async. Section 9 explains where Flask stops and what to add.

---

## 1. What Flask is (and is not)

- A lightweight **WSGI** framework built on Werkzeug (routing, requests), Jinja (templates) and Click (CLI).
- "Micro" means it makes few decisions for you: no ORM, no auth, no form validation built in. You add **extensions** when you need them.
- WSGI means **one worker handles one request at a time**. This shapes every real-time decision later (section 9).

Docs: *Welcome to Flask*, *Design Decisions in Flask*.

## 2. Setup

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install "Flask>=3.1,<3.2" pytest gunicorn
```

Minimal app (`hello.py`):

```python
from flask import Flask

app = Flask(__name__)

@app.route("/")
def hello_world():
    return "<p>Hello, World!</p>"
```

```bash
flask --app hello run --debug      # debugger + auto-reload, development only
```

- Never name your file `flask.py`.
- A file called `app.py` or `wsgi.py` is auto-discovered, so `--app` is optional.
- `--debug` is the recommended way to turn debug mode on. Setting `DEBUG` in code can behave inconsistently.
- **Never run debug mode or the dev server in production.** The debugger can execute arbitrary Python from the browser.

Docs: *Installation*, *Quickstart*.

## 3. Project structure that scales: application factory + blueprints

Real projects should not use a single global `app`. Use a **factory function** and split features into **blueprints**.

```
flask_realtime_demo/
├── app/
│   ├── __init__.py      # create_app() factory
│   ├── config.py        # Dev / Prod / Test config classes
│   ├── db.py            # database access + CLI command
│   ├── api.py           # JSON API blueprint
│   ├── web.py           # HTML pages blueprint
│   ├── errors.py        # error handlers
│   ├── events.py        # live-update broadcaster
│   ├── templates/
│   └── static/
├── tests/
├── wsgi.py              # production entry point
└── requirements.txt
```

Why a factory: you can create many app instances with different configs, which makes **testing** easy and avoids work at import time. Flask auto-detects a function named `create_app` or `make_app`.

```python
def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(CONFIGS[os.environ.get("APP_ENV", "development")])
    app.config.from_prefixed_env()           # FLASK_SECRET_KEY etc.
    if test_config:
        app.config.update(test_config)

    db.init_app(app)                         # extensions: create unbound, then init_app
    app.register_blueprint(web.bp)
    app.register_blueprint(api.bp)           # url_prefix="/api" set on the blueprint
    return app
```

Blueprints:

```python
bp = Blueprint("api", __name__, url_prefix="/api")

@bp.get("/tasks")
def list_tasks(): ...
```

- Endpoint names are prefixed with the blueprint name: `url_for("api.list_tasks")`.
- Inside a blueprint, `url_for(".list_tasks")` is a relative reference.
- Inside a factory you cannot use `app` at import time. Use `current_app` during a request.
- Gotcha: a blueprint **cannot** handle 404/405 for URLs that do not match any route, because it does not "own" that URL space. Handle those at app level (section 6).

Docs: *Application Factories*, *Modular Applications with Blueprints*, *Tutorial: Project Layout*.

## 4. Configuration

Layered approach used by the demo:

1. Defaults in a class (`Config`, `DevelopmentConfig`, `ProductionConfig`, `TestingConfig`) loaded with `from_object()`.
2. Environment variables with the `FLASK_` prefix via `from_prefixed_env()`. Values are parsed as JSON, so `FLASK_MAIL_ENABLED=false` becomes a real boolean. Nested keys use double underscores.
3. Test overrides passed into `create_app()`.

Settings worth knowing for real projects:

| Key | Why it matters |
|---|---|
| `SECRET_KEY` | Signs the session cookie. Must be long and random: `python -c "import secrets; print(secrets.token_hex())"`. Never commit it. |
| `SECRET_KEY_FALLBACKS` (3.1) | List of old keys so you can rotate without logging everyone out. |
| `MAX_CONTENT_LENGTH` | Rejects oversized bodies with 413. Unset by default. Set it. |
| `MAX_FORM_MEMORY_SIZE`, `MAX_FORM_PARTS` (3.1) | Limits for multipart forms (500 kB and 1000 by default). |
| `SESSION_COOKIE_SECURE / HTTPONLY / SAMESITE` | Set `Secure` in production, `HttpOnly` stays on, use `SameSite=Lax`. |
| `PERMANENT_SESSION_LIFETIME` | Session expiry when `session.permanent` is true. |
| `TRUSTED_HOSTS` (3.1) | Restrict allowed `Host` header values. |
| `TESTING` | Exceptions propagate to the test client. |

The demo fails fast if production starts with the default key:

```python
if env == "production" and app.config["SECRET_KEY"] == "dev":
    raise RuntimeError("Set FLASK_SECRET_KEY before running in production")
```

**Instance folder:** `app.instance_path` is for deployment-specific, non-versioned files (database, local config). The demo stores its SQLite file there.

Docs: *Configuration Handling*.

## 5. Requests, responses and JSON APIs

Routing basics:

```python
@app.get("/user/<int:user_id>")       # converters: string, int, float, path, uuid
def show_user(user_id): ...

@app.post("/tasks")
def create(): ...
```

- Routes answer `GET` by default; use `@app.get/post/patch/delete` or `methods=[...]`.
- `/projects/` (trailing slash) redirects from `/projects`; `/about` (no slash) 404s on `/about/`. Pick one style per URL.
- Always build URLs with `url_for()`; never hard-code them.

Request data:

| Need | Use |
|---|---|
| Query string | `request.args.get("key", default)` |
| Form fields | `request.form["name"]` (missing key gives automatic 400) |
| JSON body | `request.get_json()` (415 if wrong content type, 400 if malformed) |
| Files | `request.files["f"]` and always `secure_filename()` on the name |
| Cookies | `request.cookies.get("k")` |

Return values are converted to responses automatically:

- `str` becomes HTML; **`dict` or `list` becomes JSON**; a tuple sets status and headers; a generator becomes a **streaming** response.

```python
@bp.post("/tasks")
def create_task():
    body = request.get_json()
    ...
    return task, 201, {"Location": task["url"]}
```

Docs: *Quickstart* (Routing, Accessing Request Data, About Responses, APIs with JSON), *JavaScript, fetch, and JSON*.

## 6. Error handling (APIs must return JSON errors)

```python
@app.errorhandler(InvalidAPIUsage)           # your own exception class
def handle_invalid_usage(e):
    return jsonify(e.to_dict()), e.status_code

@app.errorhandler(HTTPException)             # 404, 405, 415, 413 ...
def handle_http_exception(e):
    if request.path.startswith("/api/"):
        return jsonify(error=e.name, description=e.description), e.code
    return e                                 # normal HTML page elsewhere
```

Rules to remember:

- A handler does **not** set the status code for you. Return `(response, code)`.
- Flask picks the most specific handler by class hierarchy. A blanket `Exception` handler catches everything, so pass `HTTPException` through unchanged.
- In production, an unhandled exception becomes a 500 and is logged. In debug mode the debugger takes over.
- Use **Sentry** (`pip install "sentry-sdk[flask]"`) for aggregated error reports instead of email alerts.

Docs: *Handling Application Errors*, *Debugging Application Errors*.

## 7. Database access

The docs show the `g` pattern: open one connection per request, close it when the app context tears down.

```python
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
    return g.db

def init_app(app):
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)     # flask --app app init-db
```

- Use **parameterized queries** (`?`) always.
- For real projects, use **Flask-SQLAlchemy** (and Flask-Migrate for schema changes) with PostgreSQL. Create the extension object unbound (`db = SQLAlchemy()`) and call `db.init_app(app)` in the factory.
- CLI commands that touch the database need an application context: decorate with `flask.cli.with_appcontext` when using `app.cli.add_command`.

Docs: *Using SQLite 3 with Flask*, *SQLAlchemy in Flask*, *The Application Context*, *Command Line Interface*.

## 8. Templates, static files and front-end JavaScript

- Jinja **auto-escapes** variables in `.html` templates. Do not use `|safe` or `Markup` on user data.
- Always **quote attributes** that contain Jinja expressions: `<input value="{{ value }}">`.
- Pass data to JavaScript with `{{ data|tojson }}`, and URLs with `{{ url_for(...)|tojson }}`, or via `data-` attributes as the demo does.
- In JS, build DOM with `textContent` rather than `innerHTML` for user data.
- Use template inheritance (`{% extends "layout.html" %}`) for shared layout.
- JSON calls from the browser must send `Content-Type: application/json`, or Flask answers 415.

Docs: *Templates*, *Template Inheritance*, *JavaScript, fetch, and JSON*, *Single-Page Applications*.

## 9. Real-time features: what Flask gives you and where it stops

Because WSGI ties one worker to one request, pick the tool by the job:

| Need | Approach | Flask docs support |
|---|---|---|
| Send a big or slow response progressively (CSV export, log tail) | **Streaming response**: return a generator | Yes: *Streaming Contents* |
| Push live events server to browser (notifications, progress, dashboards) | **Server-Sent Events** over a streaming response (the demo does this) | Built from the streaming pattern |
| Long job (report, email, ML, file processing) | **Task queue** (Celery) and poll a result endpoint | Yes: *Background Tasks with Celery* |
| Several slow I/O calls inside one request | **`async def` views** (`pip install "flask[async]"`) | Yes: *Using async and await* |
| Many concurrent long-lived connections, WebSockets | **Quart** (ASGI) or gevent | Docs recommend Quart for this case |

### 9.1 Streaming responses

```python
@app.route("/large.csv")
def generate_large_csv():
    def generate():
        for row in iter_all_rows():
            yield f"{','.join(row)}\n"
    return generate(), {"Content-Type": "text/csv"}
```

- Headers cannot change after streaming starts. Set them before returning.
- The `request` is gone when the generator runs. Read what you need first, or wrap with `stream_with_context()`.
- Do not modify the `session` inside the generator.
- Some WSGI middleware (profilers) breaks streaming.

### 9.2 Server-Sent Events (the demo's approach)

SSE is a one-way stream from server to browser over plain HTTP. The browser's `EventSource` reconnects automatically.

Server (`app/api.py`):

```python
@bp.get("/stream")
def stream():
    broadcaster = current_app.extensions["broadcaster"]
    def generate():
        q = broadcaster.subscribe()
        try:
            yield "retry: 3000\n\n"
            while True:
                try:
                    yield q.get(timeout=15)
                except queue.Empty:
                    yield ": keepalive\n\n"
        finally:
            broadcaster.unsubscribe(q)
    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
```

Browser (`app/static/app.js`):

```js
const source = new EventSource(STREAM_URL);
source.addEventListener("task_created", refresh);
```

**Important limits of this design:**

- **Each open SSE connection occupies one worker thread.** Run gunicorn with threads (`-k gthread --threads N`) and size N for your expected concurrent viewers. For thousands of connections, use Quart or a dedicated push service.
- The demo's broadcaster is **in-process**. With several worker processes or servers, an event published in one is not seen by clients connected to another. Use **Redis pub/sub** (or similar) as the shared bus before scaling out.
- The keepalive comment line stops proxies from closing idle connections; `X-Accel-Buffering: no` stops nginx from buffering the stream.
- WebSockets (two-way) are not part of the Flask docs. Community options exist (for example Flask-SocketIO); evaluate them against Quart.

### 9.3 Background jobs with Celery

```python
def celery_init_app(app: Flask) -> Celery:
    class FlaskTask(Task):
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)
    celery_app = Celery(app.name, task_cls=FlaskTask)
    celery_app.config_from_object(app.config["CELERY"])
    celery_app.set_default()
    app.extensions["celery"] = celery_app
    return celery_app

@shared_task(ignore_result=False)       # shared_task works with the factory pattern
def add_together(a: int, b: int) -> int:
    return a + b

@app.post("/add")
def start_add():
    result = add_together.delay(a, b)
    return {"result_id": result.id}      # return immediately

@app.get("/result/<id>")
def task_result(id):
    r = AsyncResult(id)
    return {"ready": r.ready(), "successful": r.successful(),
            "value": r.result if r.ready() else None}
```

- Pass **ids, not objects** to tasks (arguments must be serializable).
- Run with `celery -A make_celery worker --loglevel INFO`; schedule with `celery beat`.
- Combine with SSE: the worker publishes "progress" events to Redis, and the SSE endpoint forwards them to the browser.

### 9.4 async views

```python
@app.route("/get-data")
async def get_data():
    a, b = await asyncio.gather(fetch_a(), fetch_b())
    return jsonify(a=a, b=b)
```

- Helps for **concurrent I/O inside one request**. It does not raise the number of requests the server handles at once, and it does not speed up CPU-bound work.
- You cannot leave `asyncio.create_task` background work running after the view returns. Use a task queue.
- Older extensions may not support async views.

Docs: *Streaming Contents*, *Background Tasks with Celery*, *Using async and await*, *Async with Gevent*.

## 10. Security checklist (from the docs)

- Auto-escaping on; quote attributes; avoid `|safe` / `Markup` on user data.
- **CSRF:** Flask does not protect you. Use SameSite cookies and a form library or extension that issues tokens (Flask-WTF) for state-changing form posts.
- **Security headers** (the demo's `after_request` sets three): `Content-Security-Policy` (`default-src 'self'`, which is why JS lives in a static file), `X-Content-Type-Options: nosniff`, `X-Frame-Options: SAMEORIGIN`. Add `Strict-Transport-Security` behind HTTPS. Flask-Talisman can manage these.
- Cookies: `Secure`, `HttpOnly`, `SameSite=Lax`; shorten `PERMANENT_SESSION_LIFETIME` to limit replay.
- Resource limits: `MAX_CONTENT_LENGTH`, `MAX_FORM_MEMORY_SIZE`, `MAX_FORM_PARTS`, plus timeouts at the WSGI server and reverse proxy.
- `TRUSTED_HOSTS` to restrict the `Host` header.
- Uploads: never trust `filename`; use `secure_filename()`; never serve uploaded HTML inline (use `Content-Disposition: attachment`).
- Never commit `SECRET_KEY`; rotate with `SECRET_KEY_FALLBACKS`.

Docs: *Security Considerations*, *Uploading Files*.

## 11. Testing with pytest

```python
@pytest.fixture()
def app(tmp_path):
    return create_app({"TESTING": True, "DATABASE": str(tmp_path / "test.db")})

@pytest.fixture()
def client(app):
    return app.test_client()

def test_create(client):
    res = client.post("/api/tasks", json={"title": "x"})
    assert res.status_code == 201
    assert res.json["status"] == "todo"
```

- `client.post(..., json=...)` sets the content type; `response.json` parses the reply.
- `follow_redirects=True` follows redirects; `with client:` keeps session/context available after a request; `client.session_transaction()` seeds the session.
- `app.test_cli_runner()` tests CLI commands; `app.app_context()` / `app.test_request_context()` test code that needs a context.
- Test your own logic, not the libraries. For SSE, test the broadcaster/event publishing directly (the demo's `test_events_are_published`) instead of reading an endless stream.

Docs: *Testing Flask Applications*, *Tutorial: Test Coverage*.

## 12. The demo app: run it

A live task list. Open it in two browser tabs and changes appear in both immediately.

```bash
cd flask_realtime_demo
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

pytest -q                                   # 9 tests

flask --app app run --debug                 # development: http://127.0.0.1:5000
```

Production-style run (single worker with threads, because the broadcaster is in-process):

```bash
export APP_ENV=production
export FLASK_SECRET_KEY="$(python -c 'import secrets; print(secrets.token_hex())')"
gunicorn -k gthread -w 1 --threads 16 -b 0.0.0.0:8000 wsgi:app
```

Try the API:

```bash
curl -X POST localhost:5000/api/tasks -H 'Content-Type: application/json' -d '{"title":"ship it"}'
curl localhost:5000/api/tasks
curl -X PATCH localhost:5000/api/tasks/1 -H 'Content-Type: application/json' -d '{"status":"doing"}'
curl -N localhost:5000/api/stream           # watch live events while you change tasks elsewhere
```

| Pattern | Where in the demo |
|---|---|
| App factory, layered config, fail-fast secret check | `app/__init__.py`, `app/config.py` |
| Blueprints (`api`, `web`) | `app/api.py`, `app/web.py` |
| `g`-based DB access, CLI command | `app/db.py` |
| JSON errors for `/api/*`, HTML elsewhere | `app/errors.py` |
| Validation and status codes (201/204/400/404/413/415) | `app/api.py` |
| Request id, access log, security headers | `after_request` in `app/__init__.py` |
| SSE live updates and keepalive | `/api/stream` in `app/api.py`, `app/events.py` |
| Safe front end (CSP-friendly, `textContent`) | `app/static/app.js` |
| Health check for load balancers | `/healthz` in `app/web.py` |
| pytest fixtures and tests | `tests/` |

## 13. Deployment

- Use a **WSGI server**: Gunicorn (Linux/macOS), Waitress (also Windows), mod_wsgi, uWSGI, or gevent. Put **nginx** or Apache in front as a reverse proxy.
- Behind a proxy, tell Flask which forwarded headers to trust:

```python
from werkzeug.middleware.proxy_fix import ProxyFix
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
```

- Most hosting platforms (PythonAnywhere, Google App Engine and Cloud Run, AWS Elastic Beanstalk, Azure App Service) need that `ProxyFix` step.
- For SSE through nginx: disable buffering for the stream route and raise the read timeout.
- ASGI servers can host Flask through the `asgiref` `WsgiToAsgi` adapter if you need continuously running event loops.

Docs: *Deploying to Production*, *Tutorial: Deploy to Production*, *Tell Flask it is Behind a Proxy*.

## 14. Production readiness checklist

- [ ] App factory + blueprints; no work at import time
- [ ] `FLASK_SECRET_KEY` from environment/secret store; fallbacks configured for rotation
- [ ] Debug off; dev server not used
- [ ] Gunicorn (or similar) behind nginx; `ProxyFix` configured; `TRUSTED_HOSTS` set
- [ ] `MAX_CONTENT_LENGTH` and server timeouts set
- [ ] Secure/HttpOnly/SameSite cookies; CSRF protection on forms
- [ ] Security headers (CSP, nosniff, frame options, HSTS on HTTPS)
- [ ] JSON error handlers for the API; Sentry (or equivalent) for errors
- [ ] Request ids and structured access logs
- [ ] Real database (PostgreSQL) with migrations; connection handling in `teardown_appcontext`
- [ ] Health endpoint for the load balancer
- [ ] Long work in Celery, not in requests; Redis bus if running more than one worker
- [ ] pytest suite running in CI

## 15. Docs map (read in this order)

1. Quickstart → Tutorial (Flaskr blog, 11 short pages)
2. Application Factories → Blueprints → Configuration Handling
3. Handling Application Errors → Logging → Testing
4. Patterns: JavaScript/fetch/JSON, Streaming, Celery, File Uploads, Caching, View Decorators, Form Validation
5. Security Considerations → Deploying to Production
6. Using async and await → Async with Gevent

All pages are under https://flask.palletsprojects.com/en/stable/.

---

*Notes on sources:* Sections 1 to 8, 10, 11, 13 and the Celery, streaming and async parts of section 9 follow the Flask 3.1 docs pages named at the end of each section. The SSE implementation, the in-process broadcaster, the Redis/WebSocket/Flask-SocketIO remarks and the Flask-SQLAlchemy/Flask-Migrate/Flask-WTF suggestions are engineering recommendations beyond the docs, and are marked as such where they appear.
