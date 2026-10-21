"""Exercise 20 — the evaluation routes store every campaign and read it back."""

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
    for username, full_name, role in [("paul", "Paul Mbarga", E.ROLE_SUPERVISOR),
                                      ("helena", "Helena Ndongo", E.ROLE_ANALYST)]:
        c.users.add(E.User(username=username, full_name=full_name, role=role,
                           password_hash=generate_password_hash(PASSWORD)))
    return app


def _login(app, username):
    http = app.test_client()
    assert http.post("/api/auth/login",
                     json={"username": username, "password": PASSWORD}).status_code == 200
    return http


def test_a_sensitivity_campaign_is_stored_and_read_back(app, balanced_amounts):
    http = _login(app, "helena")
    posted = http.post("/api/evaluations", json={
        "ground_truth": {k: str(v) for k, v in balanced_amounts.items()}, "note": "check"})
    assert posted.status_code == 201
    campaign_id = posted.get_json()["id"]

    listed = http.get("/api/evaluations").get_json()["campaigns"]
    assert [c["id"] for c in listed] == [campaign_id]
    assert listed[0]["author"] == "Helena Ndongo"  # the signed-in user, not the body
    assert "cells" not in listed[0]  # headline only in the list

    full = http.get(f"/api/evaluations/{campaign_id}").get_json()
    assert full["kind"] == "SENSITIVITY" and full["note"] == "check"
    assert full["inputs"]["ground_truth"]["BK"] == "6746235.00"
    assert full["summary"]["interception_rate"] == posted.get_json()["interception_rate"]


def test_an_unknown_campaign_is_a_404(app):
    assert _login(app, "helena").get("/api/evaluations/nope").status_code == 404


def test_a_wrong_kind_filter_is_refused(app):
    assert _login(app, "helena").get("/api/evaluations?kind=OTHER").status_code == 422


def test_only_a_supervisor_runs_the_corpus_campaign(app, tmp_path, monkeypatch):
    monkeypatch.setenv("CORPUS_DIR", str(tmp_path / "empty-corpus"))
    (tmp_path / "empty-corpus").mkdir()
    assert _login(app, "helena").post("/api/evaluations/corpus").status_code == 403
    answer = _login(app, "paul").post("/api/evaluations/corpus", json={"note": "empty"})
    assert answer.status_code == 201
    body = answer.get_json()
    assert body["kind"] == "CORPUS" and body["author"] == "Paul Mbarga"
    assert body["headline"]["packages"] == 0


def test_a_missing_corpus_folder_is_a_404(app, tmp_path, monkeypatch):
    monkeypatch.setenv("CORPUS_DIR", str(tmp_path / "nowhere"))
    assert _login(app, "paul").post("/api/evaluations/corpus").status_code == 404