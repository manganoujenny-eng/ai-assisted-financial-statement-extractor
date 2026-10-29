"""The super administrator.

* exactly one, created once with ``backend/create_superadmin.py`` —
  never from the screens;
* manages the ADMINISTRATORS on the Users page (add, rename, reset,
  deactivate, reactivate, delete), plus everything an administrator does;
* an ordinary administrator still manages supervisors and analysts, but
  not another administrator;
* nobody manages the super administrator from the screens.
"""

from __future__ import annotations

import pytest
from werkzeug.security import generate_password_hash

from app import create_app
from app.config import Config
from app.domain import entities as E

PASSWORD = "correct-horse"


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("CORPUS_DIR", str(tmp_path / "corpus"))
    app = create_app(Config(storage="memory", upload_dir=tmp_path, auth_required=True))
    c = app.config["container"]
    c.user_service.create("root", "Rita Root", E.ROLE_SUPERADMIN, PASSWORD,
                          author="create_superadmin.py", allow_superadmin=True)
    for username, full_name, role in [
        ("ada", "Ada Admin", E.ROLE_ADMIN),
        ("bob", "Bob Admin", E.ROLE_ADMIN),
        ("paul", "Paul Mbarga", E.ROLE_SUPERVISOR),
        ("sara", "Sara Eyenga", E.ROLE_SUPERVISOR),
        ("helena", "Helena Ndongo", E.ROLE_ANALYST),
    ]:
        c.users.add(E.User(username=username, full_name=full_name, role=role,
                           password_hash=generate_password_hash(PASSWORD)))
    return app


def _login(app, username):
    http = app.test_client()
    assert http.post("/api/auth/login",
                     json={"username": username, "password": PASSWORD}).status_code == 200
    return http


def _id(http, username):
    return next(u["id"] for u in http.get("/api/users").get_json() if u["username"] == username)


def test_there_is_only_ever_one_super_administrator(app):
    service = app.config["container"].user_service
    with pytest.raises(E.DomainError, match="already"):
        service.create("root2", "Second Root", E.ROLE_SUPERADMIN, PASSWORD,
                       author="create_superadmin.py", allow_superadmin=True)


def test_nobody_creates_a_super_administrator_from_the_screens(app):
    for username in ("root", "ada"):
        refused = _login(app, username).post("/api/users", json={
            "username": "x", "full_name": "X Y", "role": "SUPERADMIN", "password": PASSWORD})
        assert refused.status_code == 409, username


def test_the_super_administrator_adds_and_manages_administrators(app):
    root = _login(app, "root")
    created = root.post("/api/users", json={
        "username": "carl", "full_name": "Carl Admin", "role": "ADMIN", "password": PASSWORD})
    assert created.status_code == 201 and created.get_json()["role"] == "ADMIN"

    ada = _id(root, "ada")
    assert root.patch(f"/api/users/{ada}", json={"full_name": "Ada Lovelace"}).status_code == 200
    assert root.patch(f"/api/users/{ada}", json={"password": "another-pass"}).status_code == 200
    assert root.patch(f"/api/users/{ada}", json={"active": False}).status_code == 200
    assert root.patch(f"/api/users/{ada}", json={"active": True}).status_code == 200
    assert root.delete(f"/api/users/{_id(root, 'carl')}").status_code == 204
    # ... and supervisors, like any administrator
    assert root.post("/api/users", json={"username": "tom", "full_name": "Tom Sup",
                                         "role": "SUPERVISOR", "password": PASSWORD}).status_code == 201


def test_an_administrator_does_not_manage_another_administrator(app):
    ada = _login(app, "ada")
    bob = _id(ada, "bob")
    assert ada.post("/api/users", json={"username": "carl", "full_name": "Carl Admin",
                                        "role": "ADMIN", "password": PASSWORD}).status_code == 409
    assert ada.patch(f"/api/users/{bob}", json={"active": False}).status_code == 409
    assert ada.delete(f"/api/users/{bob}").status_code == 409
    # supervisors and analysts: still theirs
    assert ada.patch(f"/api/users/{_id(ada, 'sara')}", json={"active": False}).status_code == 200


def test_nobody_manages_the_super_administrator_from_the_screens(app):
    root_id = _id(_login(app, "root"), "root")
    ada = _login(app, "ada")
    assert ada.patch(f"/api/users/{root_id}", json={"active": False}).status_code == 409
    assert ada.delete(f"/api/users/{root_id}").status_code == 409
    root = _login(app, "root")
    assert root.delete(f"/api/users/{root_id}").status_code == 409  # not even themselves
    # their own name and password: My account, like everyone
    assert root.patch("/api/auth/me", json={"full_name": "Rita R. Root"}).status_code == 200


def test_the_super_administrator_runs_the_system_but_never_a_case(app):
    root = _login(app, "root")
    assert root.get("/api/admin/overview").status_code == 200
    assert root.get("/api/admin/audit").status_code == 200
    assert root.post("/api/cases", json={"client": "X", "fiscal_year": 2024}).status_code == 403
    me = root.get("/api/auth/me").get_json()
    assert me["role"] == "SUPERADMIN"
    kinds = root.get("/api/admin/audit").get_json()["facets"]["author_kinds"]
    assert kinds.get("Rita Root") == "SUPERADMIN"
