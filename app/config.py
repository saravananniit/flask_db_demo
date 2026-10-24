"""Configuration classes. Pick one with the APP_ENV environment variable.

Anything can be overridden per deployment with FLASK_-prefixed environment
variables (loaded by app.config.from_prefixed_env()), e.g.:

    export FLASK_SECRET_KEY=...
    export FLASK_DATABASE=/var/data/tasks.db
"""


class Config:
    SECRET_KEY = "dev"  # replaced in production, see create_app()
    DATABASE = None  # defaults to <instance folder>/tasks.db
    MAX_CONTENT_LENGTH = 16 * 1024  # reject request bodies over 16 KB (413)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    JSON_SORT_KEYS = False


class DevelopmentConfig(Config):
    pass


class ProductionConfig(Config):
    SESSION_COOKIE_SECURE = True  # cookies only over HTTPS


class TestingConfig(Config):
    TESTING = True


CONFIGS = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
}
