"""Supervisor assignment, and My cases seen by a supervisor.

The analyst assigns each submission to one supervisor. Only that person is
notified, sees it under "Waiting for validation", and may validate it or
send it back. Once validated, only the supervisor who validated it may send
it back or delete it. A supervisor who is no longer active releases their
cases to every supervisor.
"""

from __future__ import annotations

import io

import pytest
from werkzeug.security import generate_password_hash

from app import create_app
from app.config import Config
from app.domain import entities as E

from integration.test_api_end_to_end import FakeReader, FakeStructurer

PASSWORD = "correct-horse"


@pytest.fixture
def app(tmp_path, balanced_amounts):
    app = create_app(Config(storage="memory", upload_dir=tmp_path, auth_required=True))
    c = app.config["container"]
    c.extraction.readers = [FakeReader()]
    c.extraction.structurer = FakeStructurer(balanced_amounts)  # BZ deliberately wrong
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


def _submitted_case(helena, client, supervisor="Paul Mbarga"):
    case_id = helena.post("/api/cases", json={"client": client, "fiscal_year": 2024}).get_json()["id"]
    helena.post(
        f"/api/cases/{case_id}/documents",
        data={"file": (io.BytesIO(b"%PDF-1.7 x"), "statement.pdf")},
        content_type="multipart/form-data",
    )
    run_id = helena.post(f"/api/cases/{case_id}/extractions").get_json()["id"]
    fields = helena.get(f"/api/extractions/{run_id}/fields").get_json()["fields"]
    bz = next(f for f in fields if f["item_code"] == "BZ")
    helena.patch(f"/api/fields/{bz['id']}", json={"amount": "11246235"})
    assert helena.post(
        f"/api/cases/{case_id}/submission", json={"supervisor": supervisor}
    ).status_code == 200
    return case_id, run_id


def test_supervisor_my_cases_lists_awaiting_and_validated_by_me(app):
    helena = _login(app, "helena")
    paul = _login(app, "paul")
    sara = _login(app, "sara")

    _submitted_case(helena, "WAITING FOR PAUL", "Paul Mbarga")
    _submitted_case(helena, "WAITING FOR SARA", "Sara Eyenga")
    _, run_paul = _submitted_case(helena, "BY PAUL", "Paul Mbarga")
    _, run_sara = _submitted_case(helena, "BY SARA", "Sara Eyenga")
    helena.post("/api/cases", json={"client": "IN PROGRESS", "fiscal_year": 2024})

    assert paul.post(f"/api/extractions/{run_paul}/validation", json={}).status_code == 201
    assert sara.post(f"/api/extractions/{run_sara}/validation", json={}).status_code == 201

    mine = {c["client"]: c["my_queue"] for c in paul.get("/api/my-cases").get_json()}
    assert mine == {"WAITING FOR PAUL": "AWAITING_VALIDATION", "BY PAUL": "VALIDATED_BY_ME"}

    hers = {c["client"]: c["my_queue"] for c in sara.get("/api/my-cases").get_json()}
    assert hers == {"WAITING FOR SARA": "AWAITING_VALIDATION", "BY SARA": "VALIDATED_BY_ME"}


def test_only_the_assigned_supervisor_is_notified_and_may_validate(app):
    helena = _login(app, "helena")
    paul = _login(app, "paul")
    sara = _login(app, "sara")
    case_id, run_id = _submitted_case(helena, "ACME", "Sara Eyenga")

    assert paul.get("/api/notifications").get_json() == []
    [note] = sara.get("/api/notifications").get_json()
    assert note["supervisor"] == "Sara Eyenga"

    refused = paul.post(f"/api/extractions/{run_id}/validation", json={})
    assert refused.status_code == 403
    assert "Sara Eyenga" in refused.get_json()["detail"]
    assert paul.post(
        f"/api/cases/{case_id}/correction-request", json={"message": "x"}
    ).status_code == 403

    listed = next(c for c in paul.get("/api/cases").get_json() if c["id"] == case_id)
    assert listed["assigned_supervisor"] == "Sara Eyenga"
    [submitted] = [h for h in paul.get(f"/api/cases/{case_id}/history").get_json()
                   if h["action"] == "SUBMITTED"]
    assert submitted["supervisor"] == "Sara Eyenga"

    assert sara.post(f"/api/extractions/{run_id}/validation", json={}).status_code == 201


def test_a_submission_must_name_an_active_supervisor(app):
    helena = _login(app, "helena")
    case_id = helena.post("/api/cases", json={"client": "X", "fiscal_year": 2024}).get_json()["id"]
    helena.post(
        f"/api/cases/{case_id}/documents",
        data={"file": (io.BytesIO(b"%PDF-1.7 x"), "statement.pdf")},
        content_type="multipart/form-data",
    )
    helena.post(f"/api/cases/{case_id}/extractions")
    assert helena.post(f"/api/cases/{case_id}/submission", json={}).status_code == 422
    assert helena.post(
        f"/api/cases/{case_id}/submission", json={"supervisor": "Helena Ndongo"}
    ).status_code == 422
    names = [s["full_name"] for s in helena.get("/api/supervisors").get_json()]
    assert names == ["Paul Mbarga", "Sara Eyenga"]


def test_only_the_validating_supervisor_sends_back_or_deletes(app):
    helena = _login(app, "helena")
    paul = _login(app, "paul")
    sara = _login(app, "sara")
    case_id, run_id = _submitted_case(helena, "ACME", "Paul Mbarga")
    assert paul.post(f"/api/extractions/{run_id}/validation", json={}).status_code == 201
    dataset_id = next(
        c for c in paul.get("/api/my-cases").get_json() if c["id"] == case_id
    )["dataset"]["id"]
    paul.post(f"/api/datasets/{dataset_id}/analysis")  # -> ANALYSED

    listed = next(c for c in sara.get("/api/cases").get_json() if c["id"] == case_id)
    assert listed["status"] == "ANALYSED" and listed["validated_by"] == "Paul Mbarga"

    assert sara.delete(f"/api/cases/{case_id}", json={"role": "supervisor"}).status_code == 403
    assert sara.post(
        f"/api/cases/{case_id}/correction-request", json={"message": "x"}
    ).status_code == 403
    assert paul.delete(f"/api/cases/{case_id}", json={"role": "supervisor"}).status_code == 204


def test_an_inactive_supervisor_releases_their_cases(app):
    helena = _login(app, "helena")
    paul = _login(app, "paul")
    sara = _login(app, "sara")
    _, run_id = _submitted_case(helena, "ACME", "Sara Eyenga")

    # Supervisors are managed in the database, not by each other.
    c = app.config["container"]
    sara_user = c.users.get_by_username("sara")
    sara_user.active = False
    c.users.save(sara_user)

    assert [n["client"] for n in paul.get("/api/notifications").get_json()] == ["ACME"]
    assert paul.post(f"/api/extractions/{run_id}/validation", json={}).status_code == 201


def test_analyst_my_cases_is_unchanged(app):
    helena = _login(app, "helena")
    _submitted_case(helena, "ONE")
    helena.post("/api/cases", json={"client": "TWO", "fiscal_year": 2024})
    cases = helena.get("/api/my-cases").get_json()
    assert sorted(c["client"] for c in cases) == ["ONE", "TWO"]
    assert all(c["my_queue"] is None for c in cases)


def test_supervisor_can_still_ask_for_one_analysts_cases(app):
    helena = _login(app, "helena")
    paul = _login(app, "paul")
    helena.post("/api/cases", json={"client": "H", "fiscal_year": 2024})
    picked = paul.get("/api/my-cases?analyst=Helena Ndongo").get_json()
    assert [c["client"] for c in picked] == ["H"]