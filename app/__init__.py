"""Application factory."""
import os
import time
import uuid

from flask import Flask, g, request

from . import api, db, web
from .config import CONFIGS
from .errors import register_error_handlers
from .events import Broadcaster


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__, instance_relative_config=True)

    # 1. Load configuration: defaults -> env-selected class -> env vars -> tests
    env = os.environ.get("APP_ENV", "development")
    app.config.from_object(CONFIGS[env])
    app.config.from_prefixed_env()  # FLASK_SECRET_KEY, FLASK_DATABASE, ...
    if test_config:
        app.config.update(test_config)

    if env == "production" and app.config["SECRET_KEY"] == "dev":
        raise RuntimeError("Set FLASK_SECRET_KEY before running in production")

    os.makedirs(app.instance_path, exist_ok=True)
    if not app.config["DATABASE"]:
        app.config["DATABASE"] = os.path.join(app.instance_path, "tasks.db")

    # 2. Extensions / shared objects (created unbound, then attached)
    db.init_app(app)
    app.extensions["broadcaster"] = Broadcaster()
    with app.app_context():
        db.init_db()

    # 3. Blueprints and error handlers
    app.register_blueprint(web.bp)
    app.register_blueprint(api.bp)
    register_error_handlers(app)

    # 4. Cross-cutting request hooks: request id, access log, security headers
    @app.before_request
    def start_request():
        g.request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:8]
        g.started = time.perf_counter()

    @app.after_request
    def finish_request(response):
        ms = (time.perf_counter() - g.get("started", time.perf_counter())) * 1000
        app.logger.info(
            "%s %s %s %s %.1fms", g.get("request_id"), request.method,
            request.path, response.status_code, ms,
        )
        response.headers["X-Request-ID"] = g.get("request_id", "-")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("Content-Security-Policy", "default-src 'self'")
        return response

    return app
