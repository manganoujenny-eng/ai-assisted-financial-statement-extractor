"""Only the person responsible for a case acts on it.

* the analyst who owns the case prepares it, drafts the AI commentary again
  and approves it — no other analyst, and no supervisor;
* the supervisor it was submitted to validates it; once validated, the
  analysis is run by that supervisor or by the owner — nobody else;
* everyone signed in may READ a case; acting is what is restricted.
"""

from __future__ import annotations

import io

import pytest
from werkzeug.security import generate_password_hash

from app import create_app
from app.config import Config
from app.domain import entities as E

from integration.test_api_end_to_end import FakeReader, FakeStructurer
from integration.test_intergration_api import FakeWriter

PASSWORD = "correct-horse"


@pytest.fixture
def app(tmp_path, balanced_amounts):
    app = create_app(Config(storage="memory", upload_dir=tmp_path, auth_required=True))
    c = app.config["container"]
    c.extraction.readers = [FakeReader()]
    c.extraction.structurer = FakeStructurer(balanced_amounts)
    c.insight.writer = FakeWriter()
    for username, full_name, role in [
        ("ada", "Ada Admin", E.ROLE_ADMIN),
        ("paul", "Paul Mbarga", E.ROLE_SUPERVISOR),
        ("sara", "Sara Eyenga", E.ROLE_SUPERVISOR),
        ("helena", "Helena Ndongo", E.ROLE_ANALYST),
        ("eric", "Eric Fotso", E.ROLE_ANALYST),
    ]:
        c.users.add(E.User(username=username, full_name=full_name, role=role,
                           password_hash=generate_password_hash(PASSWORD)))
    return app


def _login(app, username):
    http = app.test_client()
    assert http.post("/api/auth/login",
                     json={"username": username, "password": PASSWORD}).status_code == 200
    return http


def _validated_case(app):
    """Helena's case, submitted to Paul and validated by him."""
    helena = _login(app, "helena")
    case_id = helena.post("/api/cases", json={"client": "ACME", "fiscal_year": 2024}).get_json()["id"]
    helena.post(f"/api/cases/{case_id}/documents",
                data={"file": (io.BytesIO(b"%PDF-1.7 r1"), "statement.pdf")},
                content_type="multipart/form-data")
    run_id = helena.post(f"/api/cases/{case_id}/extractions").get_json()["id"]
    assert helena.post(f"/api/cases/{case_id}/submission",
                       json={"supervisor": "Paul Mbarga"}).status_code == 200
    paul = _login(app, "paul")
    dataset_id = paul.post(f"/api/extractions/{run_id}/validation",
                           json={"acknowledge_failed_checks": True}).get_json()["id"]
    return case_id, dataset_id


def test_only_the_validator_or_the_owner_runs_the_analysis(app):
    case_id, dataset_id = _validated_case(app)
    for username in ("sara", "eric", "ada"):
        refused = _login(app, username).post(f"/api/datasets/{dataset_id}/analysis")
        assert refused.status_code == 403, username
    assert _login(app, "paul").post(f"/api/datasets/{dataset_id}/analysis").status_code == 200
    assert _login(app, "helena").post(f"/api/datasets/{dataset_id}/analysis").status_code == 200


def test_only_the_owner_drafts_again_and_approves_the_ai_commentary(app):
    case_id, dataset_id = _validated_case(app)
    draft = _login(app, "paul").post(f"/api/datasets/{dataset_id}/analysis").get_json()["ai_analysis"]

    for username in ("eric", "paul", "sara", "ada"):
        http = _login(app, username)
        assert http.post(f"/api/cases/{case_id}/ai-analysis", json={}).status_code == 403, username
        assert http.post(f"/api/ai-analyses/{draft['id']}/approval",
                         json={"sections": draft["sections"]}).status_code == 403, username

    helena = _login(app, "helena")
    approved = helena.post(f"/api/ai-analyses/{draft['id']}/approval",
                           json={"sections": draft["sections"]})
    assert approved.status_code == 200
    assert approved.get_json()["approved_by"] == "Helena Ndongo"


def test_the_dashboard_says_who_may_act_on_the_commentary(app):
    case_id, dataset_id = _validated_case(app)
    _login(app, "paul").post(f"/api/datasets/{dataset_id}/analysis")
    may = {u: _login(app, u).get(f"/api/cases/{case_id}/analysis").get_json()["can_comment"]
           for u in ("helena", "eric", "paul")}
    assert may == {"helena": True, "eric": False, "paul": False}

