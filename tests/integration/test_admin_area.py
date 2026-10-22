"""The administrator: runs the system, never prepares nor validates a case.

* manages supervisors AND analysts (a supervisor manages analysts only);
* nobody manages an administrator from the screens (create_admin.py);
* reads the audit log, the overview and the database (read-only);
* manages the evaluation corpus;
* is refused every analyst and supervisor action on cases.
"""

from __future__ import annotations

import io

import pytest
from werkzeug.security import generate_password_hash

from app import create_app
from app.config import Config
from app.domain import entities as E

PASSWORD = "correct-horse"


def _users(app):
    c = app.config["container"]
    for username, full_name, role in [
        ("ada", "Ada Admin", E.ROLE_ADMIN),
        ("paul", "Paul Mbarga", E.ROLE_SUPERVISOR),
        ("sara", "Sara Eyenga", E.ROLE_SUPERVISOR),
        ("helena", "Helena Ndongo", E.ROLE_ANALYST),
    ]:
        c.users.add(E.User(username=username, full_name=full_name, role=role,
                           password_hash=generate_password_hash(PASSWORD)))
    return app


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("CORPUS_DIR", str(tmp_path / "corpus"))
    return _users(create_app(Config(storage="memory", upload_dir=tmp_path, auth_required=True)))


@pytest.fixture
def sql_app(tmp_path, monkeypatch):
    monkeypatch.setenv("CORPUS_DIR", str(tmp_path / "corpus"))
    config = Config(storage="sql", database_url=f"sqlite:///{tmp_path / 'admin.db'}",
                    upload_dir=tmp_path, auth_required=True)
    return _users(create_app(config))


def _login(app, username):
    http = app.test_client()
    assert http.post("/api/auth/login",
                     json={"username": username, "password": PASSWORD}).status_code == 200
    return http


def _id(http, username):
    return next(u["id"] for u in http.get("/api/users").get_json() if u["username"] == username)


# --- accounts ---------------------------------------------------------------
def test_the_administrator_adds_a_supervisor(app):
    ada = _login(app, "ada")
    added = ada.post("/api/users", json={"username": "marc", "full_name": "Marc Tchana",
                                         "role": "SUPERVISOR", "password": "12345678"})
    assert added.status_code == 201 and added.get_json()["role"] == "SUPERVISOR"


def test_nobody_adds_an_administrator_from_the_screens(app):
    refused = _login(app, "ada").post("/api/users", json={
        "username": "eve", "full_name": "Eve", "role": "ADMIN", "password": "12345678"})
    assert refused.status_code == 409
    assert "create_admin.py" in refused.get_json()["detail"]


def test_the_administrator_resets_deactivates_and_deletes_a_supervisor(app):
    ada = _login(app, "ada")
    sara = _id(ada, "sara")
    assert ada.patch(f"/api/users/{sara}", json={"password": "new-password-1"}).status_code == 200
    assert ada.patch(f"/api/users/{sara}", json={"active": False}).get_json()["active"] is False
    assert ada.delete(f"/api/users/{sara}").status_code == 204
    assert all(u["username"] != "sara" for u in ada.get("/api/users").get_json())


def test_the_last_active_supervisor_stays(app):
    ada = _login(app, "ada")
    assert ada.delete(f"/api/users/{_id(ada, 'sara')}").status_code == 204
    refused = ada.delete(f"/api/users/{_id(ada, 'paul')}")
    assert refused.status_code == 409 and "last active supervisor" in refused.get_json()["detail"]


def test_a_supervisor_still_cannot_touch_a_supervisor(app):
    paul = _login(app, "paul")
    assert paul.patch(f"/api/users/{_id(paul, 'sara')}", json={"active": False}).status_code == 409
    assert paul.delete(f"/api/users/{_id(paul, 'sara')}").status_code == 409


def test_nobody_changes_an_administrator_account(app):
    paul = _login(app, "paul")
    assert paul.patch(f"/api/users/{_id(paul, 'ada')}", json={"active": False}).status_code == 409
    ada = _login(app, "ada")
    assert ada.delete(f"/api/users/{_id(ada, 'ada')}").status_code == 409


def test_an_analyst_cannot_manage_users(app):
    helena = _login(app, "helena")
    assert helena.post("/api/users", json={"username": "x", "full_name": "X",
                                           "password": "12345678"}).status_code == 403


# --- no case work -----------------------------------------------------------
def test_the_administrator_neither_prepares_nor_validates(app):
    ada = _login(app, "ada")
    assert ada.post("/api/cases", json={"client": "ACME", "fiscal_year": 2024}).status_code == 403
    assert ada.get("/api/supervisor/overview").status_code == 403
    helena = _login(app, "helena")
    case_id = helena.post("/api/cases", json={"client": "ACME", "fiscal_year": 2024}).get_json()["id"]
    assert ada.delete(f"/api/cases/{case_id}", json={}).status_code == 403


def test_the_admin_area_is_for_the_administrator_only(app):
    for username in ("paul", "helena"):
        http = _login(app, username)
        assert http.get("/api/admin/overview").status_code == 403
        assert http.get("/api/admin/audit").status_code == 403


# --- overview and audit -----------------------------------------------------
def test_the_overview_counts_and_never_shows_a_secret(app):
    body = _login(app, "ada").get("/api/admin/overview").get_json()
    assert body["users"]["by_role"] == {"ADMIN": 1, "SUPERVISOR": 2, "ANALYST": 1}
    assert body["settings"]["anthropic_api_key"] in ("set", "not set")
    assert "secret_key" not in body["settings"]


def test_the_audit_log_filters_by_person_action_and_text(app):
    ada = _login(app, "ada")
    helena = _login(app, "helena")
    helena.post("/api/cases", json={"client": "ACME SARL", "fiscal_year": 2024})

    every = ada.get("/api/admin/audit").get_json()
    assert every["total"] >= 3  # two logins and the new case
    assert "LOGIN" in every["facets"]["actions"]

    logins = ada.get("/api/admin/audit?action=LOGIN&author=Helena Ndongo").get_json()
    assert logins["total"] == 1 and logins["entries"][0]["author"] == "Helena Ndongo"

    paged = ada.get("/api/admin/audit?per_page=1&page=2").get_json()
    assert len(paged["entries"]) == 1 and paged["page"] == 2


def test_the_audit_log_by_date_and_as_csv(app):
    ada = _login(app, "ada")
    assert ada.get("/api/admin/audit?from=2000-01-01&to=2000-01-02").get_json()["total"] == 0
    assert ada.get("/api/admin/audit?from=yesterday").status_code == 422
    csv_answer = ada.get("/api/admin/audit.csv")
    assert csv_answer.status_code == 200
    assert csv_answer.data.decode("utf-8-sig").splitlines()[0].startswith("at;author;action")


# --- corpus -----------------------------------------------------------------
def test_the_corpus_is_managed_from_the_screens(app):
    ada = _login(app, "ada")
    assert ada.post("/api/admin/corpus/packages", json={"name": "RP002"}).status_code == 201
    assert ada.post("/api/admin/corpus/packages", json={"name": "../evil"}).status_code == 422

    sent = ada.post(
        "/api/admin/corpus/RP002/files",
        data={"files": [(io.BytesIO(b"%PDF-1.4"), "statement.pdf"),
                        (io.BytesIO(b"xlsx"), "annotation_RP002.xlsx")]},
        content_type="multipart/form-data",
    )
    assert sent.status_code == 201
    package = sent.get_json()
    assert package["ready"] is True and package["saved"] == ["statement.pdf", "annotation_RP002.xlsx"]

    again = ada.post("/api/admin/corpus/RP002/files",
                     data={"files": [(io.BytesIO(b"x"), "statement.pdf")]},
                     content_type="multipart/form-data")
    assert again.status_code == 409  # never overwritten
    wrong = ada.post("/api/admin/corpus/RP002/files",
                     data={"files": [(io.BytesIO(b"x"), "notes.docx")]},
                     content_type="multipart/form-data")
    assert wrong.status_code == 422

    assert ada.delete("/api/admin/corpus/RP002").status_code == 409  # not empty
    ada.delete("/api/admin/corpus/RP002/files/statement.pdf")
    left = ada.delete("/api/admin/corpus/RP002/files/annotation_RP002.xlsx").get_json()
    assert left["files"] == [] and left["problem"] == "NO_ANNOTATION"
    assert ada.delete("/api/admin/corpus/RP002").status_code == 204

    actions = [e["action"] for e in ada.get("/api/admin/audit?entity=Corpus").get_json()["entries"]]
    assert actions.count("CORPUS_FILE_ADDED") == 2 and "CORPUS_PACKAGE_DELETED" in actions


# --- database browser -------------------------------------------------------
def test_with_memory_storage_there_is_no_database_to_browse(app):
    body = _login(app, "ada").get("/api/admin/tables").get_json()
    assert body == {"available": False, "tables": []}


def test_the_tables_are_read_only_and_hide_the_passwords(sql_app):
    ada = _login(sql_app, "ada")
    tables = {t["name"]: t for t in ada.get("/api/admin/tables").get_json()["tables"]}
    assert tables["app_user"]["rows"] == 4
    assert "password_hash" not in tables["app_user"]["columns"]

    users = ada.get("/api/admin/tables/app_user?q=mbarga").get_json()
    assert users["total"] == 1 and "password_hash" not in users["columns"]
    assert ada.get("/api/admin/tables/nothing").status_code == 404
    # Read-only: there is no route that writes.
    assert ada.post("/api/admin/tables/app_user", json={}).status_code == 405




# --- audit authors and sensitivity tests --------------------------------
def test_the_audit_says_who_each_author_is(app):
    ada = _login(app, "ada")
    app.test_client().post("/api/auth/login", json={"username": "nobody", "password": "x"})
    kinds = ada.get("/api/admin/audit").get_json()["facets"]["author_kinds"]
    assert kinds["Ada Admin"] == "ADMIN"
    assert kinds["nobody"] == "OTHER"  # a refused sign-in: a typed username


def test_a_sensitivity_test_on_a_package(app, tmp_path):
    from openpyxl import Workbook

    from conftest import BALANCED

    ada = _login(app, "ada")
    ada.post("/api/admin/corpus/packages", json={"name": "RP001"})
    wb = Workbook()
    ws = wb.active
    ws.title = "Annotation"
    ws.append(["code", "Value"])
    for code, value in BALANCED.items():
        ws.append([code, value])
    wb.save(tmp_path / "corpus" / "RP001" / "annotation_RP001.xlsx")

    answer = ada.post("/api/admin/corpus/RP001/sensitivity", json={})
    assert answer.status_code == 201
    campaign = ada.get(f"/api/evaluations/{answer.get_json()['id']}").get_json()
    assert campaign["kind"] == "SENSITIVITY" and campaign["inputs"]["package"] == "RP001"
    assert campaign["summary"]["cells"] and campaign["summary"]["criticality"]["XB"]



# --- deleting a campaign ------------------------------------------------
def _stored_campaign(app):
    campaign = E.EvaluationCampaign(kind=E.CAMPAIGN_SENSITIVITY, summary={"cells": []}, note="trial")
    app.config["container"].evaluations.add(campaign)
    return campaign.id


def test_the_administrator_deletes_a_campaign(app):
    ada = _login(app, "ada")
    campaign_id = _stored_campaign(app)
    assert ada.delete(f"/api/admin/campaigns/{campaign_id}").status_code == 204
    assert ada.get(f"/api/evaluations/{campaign_id}").status_code == 404
    assert ada.delete(f"/api/admin/campaigns/{campaign_id}").status_code == 404
    entry = ada.get("/api/admin/audit?action=CAMPAIGN_DELETED").get_json()["entries"][0]
    assert entry["author"] == "Ada Admin" and entry["entity_id"] == campaign_id
    assert entry["detail"]["note"] == "trial"


def test_only_the_administrator_deletes_a_campaign(app):
    campaign_id = _stored_campaign(app)
    for username in ("paul", "helena"):
        http = _login(app, username)
        assert http.delete(f"/api/admin/campaigns/{campaign_id}").status_code == 403
    assert app.config["container"].evaluations.get(campaign_id) is not None