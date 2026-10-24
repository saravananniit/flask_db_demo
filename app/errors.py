"""Error handling: JSON for /api/*, normal HTML pages elsewhere."""
from flask import jsonify, request
from werkzeug.exceptions import HTTPException


class InvalidAPIUsage(Exception):
    """Raise from any API view to return a JSON error with a status code."""

    status_code = 400

    def __init__(self, message, status_code=None, payload=None):
        super().__init__(message)
        self.message = message
        if status_code is not None:
            self.status_code = status_code
        self.payload = payload

    def to_dict(self):
        rv = dict(self.payload or ())
        rv["error"] = self.message
        return rv


def register_error_handlers(app) -> None:
    @app.errorhandler(InvalidAPIUsage)
    def handle_invalid_usage(e):
        return jsonify(e.to_dict()), e.status_code

    @app.errorhandler(HTTPException)
    def handle_http_exception(e):
        # Routing errors (404/405) happen before any blueprint is chosen, so
        # the app-level handler has to branch on the URL prefix.
        if request.path.startswith("/api/"):
            return jsonify(error=e.name, description=e.description), e.code
        return e

    @app.errorhandler(Exception)
    def handle_unexpected(e):
        app.logger.exception("Unhandled exception")
        if request.path.startswith("/api/"):
            return jsonify(error="Internal Server Error"), 500
        return "Something went wrong.", 500
