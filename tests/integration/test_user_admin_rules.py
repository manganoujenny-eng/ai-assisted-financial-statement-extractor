"""Who manages whom.

A supervisor adds, edits, resets, deactivates and deletes ANALYSTS only.
Supervisor accounts are created in the database (create_supervisor.py) and
each supervisor manages their own account. Nobody changes a role on screen.
"""

from __future__ import annotations

import pytest
from werkzeug.security import generate_password_hash

from app import create_app
from app.config import Config
from app.domain import entities as E

PASSWORD = "correct-horse"


@pytest.fixture
def app(tmp_path):
    app = create_app(Config(storage="memory", upload_dir=tmp_path, auth_required=True))
    c = app.config["container"]
    for username, full_name, role in [
        ("paul", "Paul Mbarga", E.ROLE_SUPERVISOR),
        ("sara", "Sara Eyenga", E.ROLE_SUPERVISOR),
        ("helena", "Helena Ndongo", E.ROLE_ANALYST),
    ]:
        c.users.add(
            E.User(username=username, full_name=full_name, role=role,
                   password_hash=generate_password_hash(PASSWORD))
        )
    return app


def _login(app, username):
    http = app.test_client()
    assert http.post(
        "/api/auth/login", json={"username": username, "password": PASSWORD}
    ).status_code == 200
    return http


def _id(http, username):
    return next(u["id"] for u in http.get("/api/users").get_json() if u["username"] == username)


def test_a_supervisor_adds_analysts_but_not_supervisors(app):
    paul = _login(app, "paul")
    refused = paul.post("/api/users", json={
        "username": "boss", "full_name": "Big Boss", "role": "SUPERVISOR", "password": "12345678",
    })
    assert refused.status_code == 409
    assert "administrator" in refused.get_json()["detail"]

    added = paul.post("/api/users", json={
        "username": "eric", "full_name": "Eric Fotso", "password": "12345678",
    })
    assert added.status_code == 201 and added.get_json()["role"] == "ANALYST"


def test_a_supervisor_cannot_touch_another_supervisor(app):
    paul = _login(app, "paul")
    sara_id = _id(paul, "sara")
    for change in ({"active": False}, {"full_name": "X"}, {"password": "new-password-1"}):
        assert paul.patch(f"/api/users/{sara_id}", json=change).status_code == 409
    assert paul.delete(f"/api/users/{sara_id}").status_code == 409


def test_nobody_changes_a_role_on_screen(app):
    paul = _login(app, "paul")
    helena_id = _id(paul, "helena")
    assert paul.patch(f"/api/users/{helena_id}", json={"role": "SUPERVISOR"}).status_code == 409
    # Sending the current role is not a change.
    assert paul.patch(
        f"/api/users/{helena_id}", json={"role": "ANALYST", "full_name": "Helena N."}
    ).status_code == 200


def test_a_supervisor_manages_analysts(app):
    paul = _login(app, "paul")
    helena_id = _id(paul, "helena")
    assert paul.patch(f"/api/users/{helena_id}", json={"password": "reset-pass-1"}).status_code == 200
    assert paul.patch(f"/api/users/{helena_id}", json={"active": False}).status_code == 200
    assert paul.patch(f"/api/users/{helena_id}", json={"active": True}).status_code == 200


def test_an_analyst_with_cases_is_deactivated_not_deleted(app):
    helena = _login(app, "helena")
    helena.post("/api/cases", json={"client": "ACME", "fiscal_year": 2024})
    paul = _login(app, "paul")
    helena_id = _id(paul, "helena")
    refused = paul.delete(f"/api/users/{helena_id}")
    assert refused.status_code == 409 and "deactivate" in refused.get_json()["detail"]

    paul.post("/api/users", json={"username": "new", "full_name": "New One", "password": "12345678"})
    assert paul.delete(f"/api/users/{_id(paul, 'new')}").status_code == 204
    assert "new" not in [u["username"] for u in paul.get("/api/users").get_json()]


def test_everyone_manages_their_own_name_and_password(app):
    sara = _login(app, "sara")
    renamed = sara.patch("/api/auth/me", json={"full_name": "Sara Eyenga Mballa"})
    assert renamed.status_code == 200 and renamed.get_json()["full_name"] == "Sara Eyenga Mballa"
    assert sara.post("/api/auth/password", json={
        "current_password": PASSWORD, "new_password": "brand-new-1",
    }).status_code == 204
    # An analyst only, never someone else's account, from /users.
    helena = _login(app, "helena")
    assert helena.patch(f"/api/users/{_id(helena, 'sara')}", json={"full_name": "X"}).status_code == 403



def test_a_renamed_supervisor_keeps_the_cases_they_validated(app):
    import io

    from integration.test_api_end_to_end import FakeReader, FakeStructurer

    c = app.config["container"]
    c.extraction.readers = [FakeReader()]
    c.extraction.structurer = FakeStructurer({"BZ": "1"})
    helena = _login(app, "helena")
    paul = _login(app, "paul")
    sara = _login(app, "sara")

    def submitted(client, to):
        case_id = helena.post("/api/cases", json={"client": client, "fiscal_year": 2024}).get_json()["id"]
        helena.post(
            f"/api/cases/{case_id}/documents",
            data={"file": (io.BytesIO(b"%PDF-1.7 x"), "s.pdf")},
            content_type="multipart/form-data",
        )
        run_id = helena.post(f"/api/cases/{case_id}/extractions").get_json()["id"]
        assert helena.post(f"/api/cases/{case_id}/submission", json={"supervisor": to}).status_code == 200
        return case_id, run_id

    done_id, done_run = submitted("VALIDATED BEFORE", "Paul Mbarga")
    waiting_id, waiting_run = submitted("WAITING", "Paul Mbarga")
    assert paul.post(f"/api/extractions/{done_run}/validation",
                     json={"acknowledge_failed_checks": True}).status_code == 201

    # Paul renames himself; the records keep "Paul Mbarga".
    assert paul.patch("/api/auth/me", json={"full_name": "Paul Mbarga Ndi"}).status_code == 200

    listed = {x["client"]: x for x in sara.get("/api/cases").get_json()}
    assert listed["VALIDATED BEFORE"]["validated_by"] == "Paul Mbarga"     # the record
    assert listed["VALIDATED BEFORE"]["validator"] == "Paul Mbarga Ndi"    # who owns it now
    assert listed["WAITING"]["assigned_supervisor"] == "Paul Mbarga Ndi"

    # Still his: not Sara's to send back, validate or delete.
    assert sara.post(f"/api/cases/{done_id}/correction-request", json={"message": "x"}).status_code == 403
    assert sara.post(f"/api/extractions/{waiting_run}/validation", json={}).status_code == 403
    assert sara.get("/api/notifications").get_json() == []

    mine = {x["client"]: x["my_queue"] for x in paul.get("/api/my-cases").get_json()}
    assert mine == {"VALIDATED BEFORE": "VALIDATED_BY_ME", "WAITING": "AWAITING_VALIDATION"}
    [note] = paul.get("/api/notifications").get_json()
    assert note["client"] == "WAITING"

    history = paul.get(f"/api/cases/{done_id}/history").get_json()
    validated = next(h for h in history if h["action"] == "VALIDATED")
    assert validated["author"] == "Paul Mbarga" and validated["supervisor_now"] == "Paul Mbarga Ndi"
    assert paul.post(f"/api/extractions/{waiting_run}/validation",
                     json={"acknowledge_failed_checks": True}).status_code == 201