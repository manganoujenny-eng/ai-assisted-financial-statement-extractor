"""Sign-in, roles and user administration (item 5).

How identity works once this is on (``AUTH_REQUIRED``, default on):

* ``POST /api/auth/login`` checks the password and stores the user's id in
  Flask's signed session cookie. Every other ``/api`` call without a valid
  session gets 401 — except ``/api/health`` and the login itself.
* Every name the system records — a case's analyst, ``corrected_by``,
  ``validated_by``, ``approved_by``, audit authors — comes from the signed-in
  user (``actor()``), never from what the browser sends. A request cannot
  claim to be someone else.
* Only a SUPERVISOR may validate a submitted case, send a case back with a
  correction request, manage analysts and open the cross-analyst dashboard
  (``require_supervisor()``). A supervisor deletes ANALYSED cases only
  (enforced in CaseService).
* Only an ANALYST prepares a case — create, edit, upload and delete
  documents, extract, correct, key items, submit (``require_analyst()``) —
  and only on their own cases (``require_case_owner()``).
* The ADMINISTRATOR runs the system (``require_admin()``): every account
  except other administrators, the audit log, the database (read-only),
  the evaluation corpus and campaigns. An administrator neither prepares
  nor validates a case.

With ``AUTH_REQUIRED=false`` (the test suite, a quick local demo) the old
behaviour stays: names come from the request body and nothing is enforced.
"""

from __future__ import annotations

from datetime import timedelta

from flask import Blueprint, current_app, g, jsonify, request, session
from werkzeug.exceptions import Forbidden, Unauthorized

from ..domain import entities as E

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")
users_bp = Blueprint("users", __name__, url_prefix="/api/users")

#: Reachable without signing in.
PUBLIC_ENDPOINTS = {"api.health", "auth.login", "auth.me"}

SESSION_LIFETIME = timedelta(hours=12)


def _container():
    return current_app.config["container"]


def auth_required() -> bool:
    return bool(_container().config.auth_required)


def current_user() -> E.User | None:
    """The signed-in, still-active user, or None."""
    if "current_user" not in g:
        user = None
        user_id = session.get("user_id")
        if user_id:
            user = _container().users.get(user_id)
            if user is not None and not user.active:
                user = None
        g.current_user = user
    return g.current_user


def require_login() -> None:
    """before_request hook for every /api blueprint."""
    if not auth_required() or request.method == "OPTIONS":
        return
    if request.endpoint in PUBLIC_ENDPOINTS:
        return
    if current_user() is None:
        raise Unauthorized("sign in first")


def require_supervisor() -> None:
    if not auth_required():
        return
    user = current_user()
    if user is None:
        raise Unauthorized("sign in first")
    if not user.is_supervisor:
        raise Forbidden("only a supervisor can do this")


def require_analyst(action: str = "do this") -> None:
    """Preparing a case is the analyst's work: creating it, uploading and
    deleting documents, extracting, correcting, keying items, submitting.
    A supervisor reviews, validates or sends back — never prepares; the
    administrator does neither."""
    if not auth_required():
        return
    user = current_user()
    if user is None:
        raise Unauthorized("sign in first")
    if not user.is_analyst:
        raise Forbidden(f"only an analyst can {action}")


def require_admin() -> None:
    """The administration area: accounts, audit log, database, campaigns."""
    if not auth_required():
        return
    user = current_user()
    if user is None:
        raise Unauthorized("sign in first")
    if not user.is_admin:
        raise Forbidden("only the administrator can do this")


def require_user_manager() -> None:
    """The Users page: a supervisor (analysts) or the administrator
    (supervisors and analysts). UserService decides who may touch whom."""
    if not auth_required():
        return
    user = current_user()
    if user is None:
        raise Unauthorized("sign in first")
    if not (user.is_supervisor or user.is_admin):
        raise Forbidden("only a supervisor or the administrator can manage users")


def require_case_owner(case: E.AnalysisCase) -> None:
    """Only the analyst a case belongs to may change it.

    A case with no analyst recorded (created before item 4) can be taken
    up by any analyst. Names are compared without case or extra spaces,
    the same way the dashboards group them.
    """
    if not auth_required():
        return
    user = current_user()
    if user is None:
        raise Unauthorized("sign in first")
    owner = " ".join((case.analyst or "").split()).casefold()
    if owner and owner != " ".join(user.full_name.split()).casefold():
        raise Forbidden(f"this case belongs to {case.analyst}")


def actor(claimed: str | None = None, default: str = "analyst") -> str:
    """The name to record for this action.

    Signed in: always the user's own full name, whatever the body claims.
    Auth off: the name the request supplied (old behaviour), else default.
    """
    if auth_required():
        user = current_user()
        if user is None:
            raise Unauthorized("sign in first")
        return user.full_name
    return (str(claimed).strip() if claimed else "") or default


def actor_role(claimed: str | None = None) -> str:
    """'supervisor', 'analyst' or 'admin' — the role string CaseService's
    delete guard expects. Signed in: the user's real role. Auth off: as
    claimed."""
    if auth_required():
        user = current_user()
        if user is None:
            raise Unauthorized("sign in first")
        if user.is_admin:
            return "admin"
        return "supervisor" if user.is_supervisor else "analyst"
    return (str(claimed).strip().lower() if claimed else "") or "analyst"


def user_json(user: E.User) -> dict:
    # Never the password hash.
    return {
        "id": user.id,
        "username": user.username,
        "full_name": user.full_name,
        "role": user.role,
        "active": user.active,
        "created_at": user.created_at.isoformat(),
    }


# --- sign in / out --------------------------------------------------------
@auth_bp.post("/login")
def login():
    payload = request.get_json(silent=True) or {}
    user = _container().user_service.authenticate(
        str(payload.get("username") or ""), str(payload.get("password") or "")
    )
    session.clear()
    session.permanent = True
    session["user_id"] = user.id
    return jsonify(user_json(user))


@auth_bp.post("/logout")
def logout():
    user = current_user() if auth_required() else None
    if user is not None:
        _container().audit.record(
            E.AuditEntry(entity="User", entity_id=user.id, action="LOGOUT", author=user.full_name)
        )
    session.clear()
    return "", 204


@auth_bp.get("/me")
def me():
    """Who is signed in. 401 when nobody is, so the page shows the login.

    With AUTH_REQUIRED=false this answers a stand-in supervisor, so the
    frontend shows every screen during a local demo.
    """
    if not auth_required():
        return jsonify(
            {
                "id": None,
                "username": "local",
                "full_name": "Local user",
                "role": E.ROLE_SUPERVISOR,
                "active": True,
                "auth_required": False,
            }
        )
    user = current_user()
    if user is None:
        raise Unauthorized("sign in first")
    return jsonify({**user_json(user), "auth_required": True})


@auth_bp.patch("/me")
def update_me():
    """My account: change my own full name (any signed-in user)."""
    user = current_user()
    if user is None:
        raise Unauthorized("sign in first")
    payload = request.get_json(silent=True) or {}
    _container().user_service.update_own_profile(user, str(payload.get("full_name") or ""))
    return jsonify({**user_json(user), "auth_required": True})


@auth_bp.post("/password")
def change_password():
    user = current_user()
    if user is None:
        raise Unauthorized("sign in first")
    payload = request.get_json(silent=True) or {}
    _container().user_service.change_own_password(
        user, str(payload.get("current_password") or ""), str(payload.get("new_password") or "")
    )
    return "", 204


# --- user administration (supervisor or administrator) --------------------
def _manager() -> E.User:
    """The signed-in manager, or a stand-in administrator with sign-in off."""
    return current_user() or E.User(
        username="local", full_name="Local user", role=E.ROLE_ADMIN, password_hash="-", id="local"
    )


@users_bp.get("")
def list_users():
    """Every user, for the Users page. Analysts get the list too, but only
    names and roles (to show who is who); the page itself is for
    supervisors and the administrator."""
    return jsonify([user_json(u) for u in _container().users.list()])


@users_bp.post("")
def create_user():
    """A supervisor adds an analyst; an administrator adds an analyst or a
    supervisor; the super administrator also adds administrators. Nobody
    adds the super administrator here (create_superadmin.py)."""
    require_user_manager()
    payload = request.get_json(silent=True) or {}
    user = _container().user_service.create(
        username=str(payload.get("username") or ""),
        full_name=str(payload.get("full_name") or ""),
        role=str(payload.get("role") or E.ROLE_ANALYST),
        password=str(payload.get("password") or ""),
        author=actor(default="administrator"),
        allow_supervisor=_manager().is_admin,
        allow_admin=_manager().is_superadmin,
    )
    return jsonify(user_json(user)), 201


@users_bp.patch("/<user_id>")
def update_user(user_id: str):
    require_user_manager()
    c = _container()
    user = c.users.get(user_id)
    if user is None:
        raise KeyError(user_id)
    payload = request.get_json(silent=True) or {}
    author = _manager()
    c.user_service.update(
        user,
        author=author,
        full_name=payload.get("full_name"),
        role=payload.get("role"),
        active=payload.get("active") if isinstance(payload.get("active"), bool) else None,
        password=payload.get("password") or None,
    )
    return jsonify(user_json(user))


@users_bp.delete("/<user_id>")
def delete_user(user_id: str):
    """Delete an analyst who owns no case (supervisor or administrator), or
    a supervisor who is not the last active one (administrator only)."""
    require_user_manager()
    c = _container()
    user = c.users.get(user_id)
    if user is None:
        raise KeyError(user_id)
    c.user_service.delete(user, _manager())
    return "", 204