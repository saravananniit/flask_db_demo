# Flask Live Tasks Demo: Complete Code Explanation

This file explains **every file**, **in the order Python runs them**, and shows **one flow diagram** of how a click in the browser travels through the code and comes back as a live update.

---

## 1. What the app does (in one minute)

It is a task list web page. You can add a task, click its colored badge to move it `todo → doing → done`, and delete it with ×.

The special part: open the page in **two browser tabs**. When you change something in tab 1, tab 2 updates by itself. That is the "real-time" feature.

Three technologies work together:

| Piece | Job |
|---|---|
| **Flask (Python)** | Receives requests, saves to the database, sends answers |
| **SQLite database** (`instance/tasks.db`) | Stores the tasks permanently |
| **Server-Sent Events (SSE)** | A connection the browser keeps open so the server can push news ("a task changed") |

---

## 2. Folder map

```
flask_realtime_demo/
├── wsgi.py                  ← entry point for production servers
├── requirements.txt         ← list of packages to install
├── pytest.ini               ← (you add this) makes pytest find the app
├── app/                     ← the application package
│   ├── __init__.py          ← create_app(): builds and wires everything  ★ most important
│   ├── config.py            ← settings (dev / production / testing)
│   ├── db.py                ← database connection helpers
│   ├── events.py            ← Broadcaster: the "news announcer"
│   ├── errors.py            ← turns errors into JSON answers
│   ├── api.py               ← /api/... URLs (the data and the live stream)
│   ├── web.py               ← / (the page) and /healthz
│   ├── templates/
│   │   └── index.html       ← the HTML page
│   └── static/
│       ├── app.js           ← browser code (talks to the API)
│       └── style.css        ← looks
└── tests/
    ├── conftest.py          ← test setup
    └── test_api.py          ← the tests
```

The folder `app/` is a **Python package** because it contains `__init__.py`. That is why the command is `flask --app app run`: "run the package called `app`".

---

## 3. Words you need first

| Word | Simple meaning |
|---|---|
| **Route** | A URL the server answers, for example `/api/tasks` |
| **Blueprint** | A named group of routes. Here: `api` group and `web` group |
| **App factory** | A function (`create_app`) that builds the Flask app, instead of building it at the top of a file |
| **Request / response** | The browser asks, the server answers |
| **`g`** | A scratch notebook Flask gives each request. Anything you put in `g` lives only until that request ends |
| **`current_app`** | "The app that is handling this request." Used inside blueprints where you cannot import `app` directly |
| **App context** | A "Flask is active now" bubble. Things like `g` and `current_app` only work inside it. Flask creates one automatically for every request |
| **JSON** | Text format for data: `{"title": "buy milk"}`. Python dicts and lists become JSON automatically |
| **Queue** | A line of messages. One side puts messages in, the other takes them out in order |

---

## 4. What runs when you type `uv run flask --app app run --debug`

This is the **startup order**. Nothing handles any browser request yet.

1. The `flask` command imports the package `app`. Python therefore runs **`app/__init__.py` from top to bottom**.
2. The imports at the top of `__init__.py` run, which loads `api.py`, `db.py`, `web.py`, `config.py`, `errors.py`, `events.py`. At this point those files only **define** things (functions, classes, blueprints). Nothing is executed yet.
3. Flask sees a function named `create_app` and **calls it**. All the setup happens inside it (section 5.1).
4. `create_app` returns the finished app. The development server starts listening on http://127.0.0.1:5000.

Then it waits. Every browser visit triggers the **request flow** (section 6).

---

## 5. File by file

### 5.1 `app/__init__.py`: the factory (read this first)

```python
def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__, instance_relative_config=True)
```
Creates the Flask app. `__name__` tells Flask where the package lives (so it finds `templates/` and `static/`). `instance_relative_config=True` means "the `instance/` folder is where local files like the database go."

```python
    env = os.environ.get("APP_ENV", "development")
    app.config.from_object(CONFIGS[env])
    app.config.from_prefixed_env()
    if test_config:
        app.config.update(test_config)
```
Settings are loaded in **layers**, later layers win:

1. `APP_ENV` picks a class from `config.py` (default `development`).
2. `from_prefixed_env()` reads environment variables that start with `FLASK_`. So `FLASK_SECRET_KEY=abc` sets `SECRET_KEY`, and `FLASK_DATABASE=...` sets `DATABASE`.
3. `test_config` (only used by tests) overrides everything.

```python
    if env == "production" and app.config["SECRET_KEY"] == "dev":
        raise RuntimeError("Set FLASK_SECRET_KEY before running in production")
```
Safety check: refuse to start in production with the placeholder secret.

```python
    os.makedirs(app.instance_path, exist_ok=True)
    if not app.config["DATABASE"]:
        app.config["DATABASE"] = os.path.join(app.instance_path, "tasks.db")
```
Creates the `instance/` folder if missing and decides where the database file is.

```python
    db.init_app(app)
    app.extensions["broadcaster"] = Broadcaster()
    with app.app_context():
        db.init_db()
```
- `db.init_app(app)` registers the database cleanup and the `init-db` command (see `db.py`).
- A single `Broadcaster` is created and stored in `app.extensions`, a shelf Flask provides for shared objects. Any code can fetch it later with `current_app.extensions["broadcaster"]`.
- `with app.app_context(): db.init_db()` creates the `task` table now if it does not exist. The `with` is needed because database helpers use `g` and `current_app`.

```python
    app.register_blueprint(web.bp)
    app.register_blueprint(api.bp)
    register_error_handlers(app)
```
Plugs in the two route groups and the error handlers. Before this line, Flask knows no URLs.

```python
    @app.before_request
    def start_request():
        g.request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:8]
        g.started = time.perf_counter()
```
Runs **before every request**. Gives the request a short id (or reuses one sent by the client) and notes the start time, both stored in `g`.

```python
    @app.after_request
    def finish_request(response):
        ms = (time.perf_counter() - g.get("started", time.perf_counter())) * 1000
        app.logger.info("%s %s %s %s %.1fms", ...)
        response.headers["X-Request-ID"] = ...
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("Content-Security-Policy", "default-src 'self'")
        return response
```
Runs **after every request**, with the response in hand. It:
- computes how many milliseconds the request took and writes a log line (visible in the terminal in debug mode),
- adds the request id header,
- adds three **security headers**. `Content-Security-Policy: default-src 'self'` tells the browser "only run scripts and styles that come from my own site". That is why the page's JavaScript is in `app.js` and not written inside the HTML.

Finally `return app` hands the finished app to Flask.

---

### 5.2 `app/config.py`: settings

Four small classes:

- `Config`: shared defaults. Notable lines:
  - `SECRET_KEY = "dev"`: used to sign cookies. Must be replaced in production.
  - `DATABASE = None`: "decide later" (the factory fills it in).
  - `MAX_CONTENT_LENGTH = 16 * 1024`: reject any request body larger than 16 KB (answer 413). Protects the server.
  - `SESSION_COOKIE_HTTPONLY` / `SAMESITE`: cookie safety settings.
  - `JSON_SORT_KEYS = False`: has **no effect** in Flask 3.1 (the setting was removed). JSON keys come out alphabetical. It is harmless and can be deleted.
- `DevelopmentConfig`: nothing extra.
- `ProductionConfig`: `SESSION_COOKIE_SECURE = True` (cookies only over HTTPS).
- `TestingConfig`: `TESTING = True` (errors surface in tests).

`CONFIGS` is a dictionary mapping a name to a class, so `CONFIGS["production"]` gives `ProductionConfig`.

---

### 5.3 `app/db.py`: database helpers

```python
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
    return g.db
```
"Give me the database connection for this request." The first call in a request opens a connection and stores it in `g`; later calls in the same request reuse it. `row_factory = sqlite3.Row` lets you read columns by name (`row["title"]`) instead of by position.

```python
def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()
```
Closes the connection when the request is finished. It is hooked up by `app.teardown_appcontext(close_db)`, so Flask calls it automatically.

```python
SCHEMA = """CREATE TABLE IF NOT EXISTS task (id ..., title ..., status ..., created ...)"""
def init_db():
    get_db().executescript(SCHEMA)
```
The table design: `id` (auto number), `title`, `status` (default `todo`), `created` (timestamp). `IF NOT EXISTS` makes it safe to run many times.

```python
@click.command("init-db")
@with_appcontext
def init_db_command(): ...
```
A custom terminal command: `flask --app app init-db`. `@with_appcontext` is required so `g` and `current_app` work.

`init_app(app)` ties it together: register the cleanup and add the command.

---

### 5.4 `app/events.py`: the Broadcaster (the "news announcer")

Think of a radio station. Each open browser tab is a **listener** with its own **mailbox (queue)**. When something changes, the station puts a copy of the news into every mailbox.

```python
class Broadcaster:
    def __init__(self):
        self._subscribers = set()      # all mailboxes
        self._lock = threading.Lock()  # prevents two threads changing the set at once
```

- `subscribe()`: creates a new `queue.Queue` (max 100 messages), adds it to the set, returns it. "A new listener joined."
- `unsubscribe(q)`: removes the mailbox. "Listener left."
- `publish(event, data)`: builds the message text in the format SSE requires:

  ```
  event: task_created
  data: {"id": 1, "title": "milk", ...}
  (blank line)
  ```
  then drops it into every mailbox with `put_nowait`. If a mailbox is full (a very slow client) the message is skipped for that client instead of freezing everyone.
- `subscriber_count`: how many listeners are connected.

Limit to remember: this lives **inside one Python process**. That is why the production command uses one gunicorn worker (`-w 1`) with threads.

---

### 5.5 `app/errors.py`: friendly errors

```python
class InvalidAPIUsage(Exception):
```
Your own error type. Anywhere in an API view you can write `raise InvalidAPIUsage("message", status_code=404)` to stop and return a JSON error. `to_dict()` turns it into `{"error": "message"}`.

`register_error_handlers(app)` installs three handlers:

1. **`InvalidAPIUsage`** → JSON `{"error": ...}` with its status code.
2. **`HTTPException`** (404 not found, 405 wrong method, 413 too big, 415 wrong content type, 400 bad JSON...) → if the URL starts with `/api/`, return JSON; otherwise return Flask's normal HTML error page. The URL check is needed because a 404 happens before Flask knows which blueprint was meant.
3. **`Exception`** (any unexpected crash) → log the full traceback, then answer a safe 500 message without leaking details.

---

### 5.6 `app/api.py`: the API (the heart of the logic)

```python
bp = Blueprint("api", __name__, url_prefix="/api")
```
A route group named `api`; every route inside automatically starts with `/api`.

**Helper functions** (names start with `_`, meaning "internal"):

- `_row_to_dict(row)`: converts a database row into a plain dictionary and adds a `url` for that task using `url_for("api.get_task", ...)`.
- `_validate_title(value)`: the title must be a string, not empty, at most 200 characters; trims spaces. Otherwise raises `InvalidAPIUsage` (400).
- `_fetch_or_404(task_id)`: loads a task or raises 404 "No such task".
- `_publish(event, data)`: gets the Broadcaster from `current_app.extensions` and announces the news.

**Routes:**

| Method + URL | What it does | Success answer |
|---|---|---|
| `GET /api/tasks` | List tasks. Optional `?status=done` filter, validated against `todo/doing/done` | 200 + list |
| `POST /api/tasks` | `request.get_json()` reads the body, validates title, `INSERT`, `commit`, reload the row, **publish `task_created`** | 201 + task + `Location` header |
| `GET /api/tasks/<id>` | One task | 200 + task |
| `PATCH /api/tasks/<id>` | Change `title` and/or `status` (only the fields sent), `UPDATE`, **publish `task_updated`** | 200 + task |
| `DELETE /api/tasks/<id>` | Delete, **publish `task_deleted`** | 204 (empty) |
| `GET /api/stream` | The live connection (below) | stays open |

`<int:task_id>` in a URL means "this part must be a whole number and is passed to the function as `task_id`".

Returning a dict or list from a view makes Flask send JSON automatically. `return task, 201, {"Location": ...}` is a tuple: body, status code, extra headers.

**The stream route**, step by step:

```python
broadcaster = current_app.extensions["broadcaster"]   # grab it NOW, while the request is active
def generate():
    q = broadcaster.subscribe()          # new mailbox for this tab
    try:
        yield "retry: 3000\n\n"          # tell the browser: if disconnected, retry after 3 s
        while True:
            try:
                yield q.get(timeout=15)  # wait up to 15 s for news, send it when it arrives
            except queue.Empty:
                yield ": keepalive\n\n"  # nothing happened: send a harmless ping
    finally:
        broadcaster.unsubscribe(q)       # runs when the tab closes
return Response(generate(), mimetype="text/event-stream", headers={...})
```
- `generate` is a **generator**: each `yield` sends a piece to the browser right away without ending the response. That is how the connection stays open.
- The 15-second ping stops proxies and browsers from closing an "idle" connection.
- `finally` guarantees the mailbox is removed when the tab disconnects, so nothing leaks.
- `text/event-stream` is the content type that tells the browser "this is an SSE stream". `Cache-Control: no-cache` and `X-Accel-Buffering: no` stop caches and nginx from holding the data back.

---

### 5.7 `app/web.py`: the page

```python
bp = Blueprint("web", __name__)
@bp.get("/")        → render_template("index.html")
@bp.get("/healthz") → {"status": "ok"}
```
`/` returns the HTML page. `/healthz` is a tiny "I am alive" URL that servers and load balancers check.

---

### 5.8 `app/templates/index.html`: the page structure

- `<link rel="stylesheet" href="{{ url_for('static', filename='style.css') }}">`: `{{ ... }}` is Jinja, evaluated on the server. `url_for('static', ...)` builds the URL `/static/style.css`.
- `<body data-api="{{ url_for('api.list_tasks') }}" data-stream="{{ url_for('api.stream') }}">`: stores the two API URLs on the body tag (`/api/tasks` and `/api/stream`) so JavaScript can read them. No URL is hard-coded in JavaScript.
- A `<span id="conn">` shows `live` / `offline`.
- A form (`#add-form`) with the title input and an Add button.
- An empty `<ul id="tasks">`: JavaScript fills it.
- `<script src=".../app.js">` loads the browser code from a file (not inline, because of the security policy).

---

### 5.9 `app/static/app.js`: the browser code

Top of file:
```js
const API = document.body.dataset.api;       // "/api/tasks"
const STREAM = document.body.dataset.stream; // "/api/stream"
const NEXT = { todo: "doing", doing: "done", done: "todo" };
```
`NEXT` says which status comes after which.

Functions:

- **`showError(msg)`**: shows or hides the red error line.
- **`call(url, options)`**: a small wrapper around `fetch`. If the server answers an error, it reads the JSON `{"error": ...}` and throws it as a JavaScript error, so `showError` can display it. For 204 (delete) it returns nothing.
- **`render(tasks)`**: empties the list and fills it with one `<li>` per task.
- **`renderTask(t)`**: builds one row: a **badge button** (click sends `PATCH` with the next status), the **title** (set with `textContent`, never `innerHTML`, so a title like `<script>` can never run as code), and a **× button** (click sends `DELETE`).
- **`refresh()`**: `GET /api/tasks`, then `render` the result.

Event wiring:

- **Form submit**: stops the normal page reload, sends `POST /api/tasks` with the title as JSON, clears the input on success.
- **`new EventSource(STREAM)`**: opens the live connection to `/api/stream`.
  - `onopen`: show "live" and `refresh()`.
  - `onerror`: show "reconnecting…" (the browser retries by itself).
  - For each of `task_created`, `task_updated`, `task_deleted`: call `refresh()`.
- The last line `refresh()` loads the list when the page first opens.

Important idea: the browser does **not** update the list itself after you click. It sends the change to the server and then waits for the server's news to come back through the stream, then reloads the list. That is why all tabs, including the one you clicked in, stay perfectly in sync.

---

### 5.10 `app/static/style.css`

Only appearance: colors as variables at the top (with a dark mode block), the layout card, the colored status badges (grey `todo`, orange `doing`, green `done`), and the strike-through for finished tasks. No logic.

---

### 5.11 `wsgi.py`

```python
from app import create_app
app = create_app()
```
Production servers (gunicorn, waitress) need a ready-made app object. `gunicorn wsgi:app` means "in file `wsgi.py`, use the variable `app`". It is **not** used by `flask --app app run`, which calls the factory itself.

### 5.12 `requirements.txt`

Packages to install: Flask, gunicorn (production server, Linux/macOS), pytest (tests).

### 5.13 `tests/conftest.py`

Test **fixtures**, reusable setup pieces that pytest passes into tests by name:

- `app`: builds a fresh app with `TESTING=True` and a **temporary database** (`tmp_path`), so tests never touch your real data.
- `client`: a fake browser (`app.test_client()`) that can call URLs without starting a server.
- `runner`: runs terminal commands such as `init-db` inside tests.

### 5.14 `tests/test_api.py`: what each test proves

| Test | Proves |
|---|---|
| `test_index_and_health` | `/` returns 200 and `/healthz` returns `{"status":"ok"}` |
| `test_security_headers_and_request_id` | Request id echoed back; security headers present |
| `test_create_list_update_delete` | The full lifecycle works (201, list, filter by status, 204, then 404) |
| `test_validation_errors_are_json` | Empty or too-long title, bad status, bad filter all give 400 JSON |
| `test_non_json_and_bad_json` | Wrong content type gives 415; malformed JSON gives 400; both as JSON |
| `test_unknown_api_route_is_json_404_but_html_elsewhere` | `/api/nope` is a JSON 404, `/nope` is a normal HTML 404 |
| `test_body_size_limit` | A body over 16 KB gives 413 |
| `test_events_are_published` | Create, update, delete publish the three events in order |
| `test_init_db_cli` | The `init-db` command prints "Database ready" |

### 5.15 `pytest.ini` (you add this)

```ini
[pytest]
pythonpath = .
testpaths = tests
```
Tells pytest to add the project folder to Python's search path so `from app import create_app` works.

---

## 6. The flow diagram: from your click to every tab updating

Scenario: you type "buy milk" and press **Add** in Tab 1, while Tab 2 is also open.

```
 SETUP (happens once when each tab opens)
 ─────────────────────────────────────────────────────────────────────────────
  Tab 1 / Tab 2                         Flask server
  ┌──────────────────┐   GET /          ┌────────────────────────────────┐
  │ browser opens    │ ───────────────► │ web.index → index.html         │
  │ the page         │ ◄─────────────── │ (+ app.js, style.css)          │
  └────────┬─────────┘                  └────────────────────────────────┘
           │ app.js runs
           │ GET /api/tasks  ─────────────► api.list_tasks ─► DB ─► JSON ─► list drawn
           │ new EventSource("/api/stream")
           └───────────────────────────────► api.stream
                                              └─ broadcaster.subscribe()
                                                 gives THIS tab its own queue q
                                                 connection stays OPEN ◄────┐
                                                                            │
 YOU CLICK "ADD" IN TAB 1                                                   │
 ─────────────────────────────────────────────────────────────────────────  │
  ① app.js form submit                                                      │
     POST /api/tasks  {"title": "buy milk"}                                 │
              │                                                             │
              ▼                                                             │
  ② before_request ......... gives request an id, starts timer              │
              │                                                             │
  ③ api.create_task                                                         │
     ├─ request.get_json() ............ reads the body                      │
     ├─ _validate_title() ............. rules OK? else InvalidAPIUsage ─► JSON 400
     ├─ INSERT INTO task ... commit .... saved in instance/tasks.db         │
     ├─ _fetch_or_404(new id) .......... reload the row                     │
     └─ _publish("task_created", task)                                      │
              │                                                             │
              ▼                                                             │
  ④ Broadcaster.publish()                                                   │
     puts the message text into EVERY subscriber queue ───────────────┐     │
              │                                                       │     │
  ⑤ after_request ... log line + security headers                     │     │
     response 201 Created ──► back to Tab 1 (form clears)             │     │
                                                                      ▼     │
  ⑥ each open stream generator is waiting on  q.get(...)              │     │
     it wakes up and yields the message ────────────────────────────────────┘
              │   "event: task_created / data: {...}"
              ▼
  ⑦ Tab 1 AND Tab 2: EventSource receives "task_created"
              │
              ▼
  ⑧ app.js refresh()  ──  GET /api/tasks  ──►  DB  ──►  JSON list
              │
              ▼
  ⑨ render(): both tabs now show "buy milk"          ✔ live, no page reload
```

How to read it: steps ①–⑤ are one normal request/response. Steps ⑥–⑨ are the live part: the **already-open stream connections** receive the news and each tab reloads its own list.

Update (click the badge) and delete (click ×) follow exactly the same path, only with `PATCH` or `DELETE` in step ① and `task_updated` / `task_deleted` in step ④.

---

## 7. Cheat sheet: "which file do I open for...?"

| I want to... | Open |
|---|---|
| Change a setting, such as the size limit | `config.py` |
| Add a new URL or field | `api.py` (and `db.py` SCHEMA if a new column) |
| Change the page layout | `index.html`, `style.css` |
| Change browser behavior | `app.js` |
| Change how errors look | `errors.py` |
| Add something to every response | `after_request` in `__init__.py` |
| Change what is announced live | `_publish(...)` calls in `api.py`, `events.py` |
| Understand start-up | `__init__.py` → `create_app` |

## 8. Debug tips

- Watch the terminal: in debug mode every request prints a line like `9d985615 POST /api/tasks 201 3.2ms`.
- In the browser, press **F12 → Network** to see the requests, and the `stream` request staying "pending" (that is the open live connection).
- To see the raw live events: `curl -N http://127.0.0.1:5000/api/stream` in one terminal, then add a task in the browser.
- To reset the data: stop the app and delete `instance/tasks.db`.


Flask is a **backend (BE)** framework. It runs on the server, written in Python, and handles requests, business logic, the database and the data sent back to the browser.

In this demo:

| Part | Side | Files |
|---|---|---|
| Flask code | **Backend** | `__init__.py`, `api.py`, `db.py`, `events.py`, `errors.py`, `web.py`, `config.py` |
| HTML, JavaScript, CSS | **Frontend** | `index.html`, `app.js`, `style.css` |

Flask also delivers the frontend files to the browser: `web.py` serves the page and `/static/` serves the JS and CSS. Flask's template engine (Jinja) can build HTML on the server too. That makes Flask look like it does frontend work, but the page itself still runs and behaves in the browser.

Flask can serve the whole app by itself, as in this demo, or act only as a backend API. In the second case a separate frontend such as React, Vue or Streamlit calls Flask's `/api/...` URLs.