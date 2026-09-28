"""Flask blueprints."""

from __future__ import annotations


def register_blueprints(app) -> None:
    from .routes import bp

    app.register_blueprint(bp)
