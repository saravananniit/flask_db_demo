"""HTML pages blueprint."""
from flask import Blueprint, render_template

bp = Blueprint("web", __name__)


@bp.get("/")
def index():
    return render_template("index.html")


@bp.get("/healthz")
def healthz():
    """Used by load balancers / container orchestrators."""
    return {"status": "ok"}
