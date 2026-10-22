"""Flask blueprints."""

from __future__ import annotations


def register_blueprints(app) -> None:
    from .admin import admin_bp
    from .auth import auth_bp, require_login, users_bp
    from .routes import bp

    for blueprint in (bp, auth_bp, users_bp, admin_bp):
        app.register_blueprint(blueprint)

    # Item 5 — every /api call needs a signed-in user (see auth.py), except
    # /api/health and the login itself. On the app, not the blueprints: a
    # blueprint cannot gain a hook once registered, and the tests build
    # several apps from the same blueprints.
    app.before_request(require_login)