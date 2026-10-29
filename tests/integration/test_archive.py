"""The archive: every deletion can be undone by the administrator.

When someone deletes a case, a document, an account, a corpus file or
package, or a campaign, it disappears for them as before — but a complete
copy goes to the archive. The administrator (and the super administrator)
sees the archive, restores an entry exactly as it was (same identifiers,
same history), or deletes it for good. Restoring and purging are audited.
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
USERS = [
    ("ada", "Ada Admin", E.ROLE_ADMIN),
    ("paul", "Paul Mbarga", E.ROLE_SUPERVISOR),
    ("sara", "Sara Eyenga", E.ROLE_SUPERVISOR),
    ("helena", "Helena Ndongo", E.ROLE_ANALYST),
    ("eric", "Eric Fotso", E.ROLE_ANALYST),
]


def _build(config, balanced_amounts):
    app = create_app(config)
    c = app.config["container"]
    c.extraction.readers = [FakeReader()]
    c.extraction.structurer = FakeStructurer(balanced_amounts)
    for username, full_name, role in USERS:
        c.users.add(E.User(username=username, full_name=full_name, role=role,
                           password_hash=generate_password_hash(PASSWORD)))
    return app


@pytest.fixture
def app(tmp_path, monkeypatch, balanced_amounts):
    monkeypatch.setenv("CORPUS_DIR", str(tmp_path / "corpus"))
    return _build(Config(storage="memory", upload_dir=tmp_path / "up", auth_required=True,
                         archive_dir=tmp_path / "archive"), balanced_amounts)


@pytest.fixture
def sql_app(tmp_path, monkeypatch, balanced_amounts):
    monkeypatch.setenv("CORPUS_DIR", str(tmp_path / "corpus"))
    return _build(Config(storage="sql", database_url=f"sqlite:///{tmp_path / 'a.db'}",
                         upload_dir=tmp_path / "up", auth_required=True,
                         archive_dir=tmp_path / "archive"), balanced_amounts)


def _login(app, username):
    http = app.test_client()
    assert http.post("/api/auth/login",
                     json={"username": username, "password": PASSWORD}).status_code == 200
    return http


def _extracted_case(http, client="ACME SARL"):
    case_id = http.post("/api/cases", json={"client": client, "fiscal_year": 2024}).get_json()["id"]
    doc = http.post(f"/api/cases/{case_id}/documents",
                    data={"file": (io.BytesIO(b"%PDF-1.7 " + client.encode()), "statement.pdf")},
                    content_type="multipart/form-data").get_json()
    run_id = http.post(f"/api/cases/{case_id}/extractions").get_json()["id"]
    return case_id, doc["id"], run_id


def _entries(admin, kind=None):
    return admin.get("/api/admin/archive" + (f"?kind={kind}" if kind else "")).get_json()["entries"]


# --- cases -------------------------------------------------------------------
@pytest.mark.parametrize("which", ["app", "sql_app"])
def test_a_deleted_case_is_archived_and_restored_whole(which, request):
    app = request.getfixturevalue(which)
    helena = _login(app, "helena")
    case_id, doc_id, run_id = _extracted_case(helena)
    fields_before = len(helena.get(f"/api/extractions/{run_id}/fields").get_json()["fields"])

    assert helena.delete(f"/api/cases/{case_id}", json={}).status_code == 204
    assert helena.get(f"/api/cases/{case_id}").status_code == 404   # gone for the user

    ada = _login(app, "ada")
    [entry] = _entries(ada, "CASE")
    assert entry["entity_id"] == case_id and entry["deleted_by"] == "Helena Ndongo"
    assert "ACME SARL" in entry["label"] and "payload" not in entry
    assert entry["detail"]["documents"] == 1 and entry["detail"]["runs"] == 1

    assert ada.post(f"/api/admin/archive/{entry['id']}/restore").status_code == 200
    case = helena.get(f"/api/cases/{case_id}").get_json()
    assert case["status"] == "EXTRACTED" and case["analyst"] == "Helena Ndongo"
    assert [d["id"] for d in case["documents"]] == [doc_id]
    assert len(helena.get(f"/api/extractions/{run_id}/fields").get_json()["fields"]) == fields_before
    assert _entries(ada) == []
    actions = [e["action"] for e in ada.get("/api/admin/audit").get_json()["entries"]]
    assert "RESTORED" in actions


def test_a_restored_case_keeps_its_validation_and_ai_commentary(app):
    helena = _login(app, "helena")
    case_id, _doc, run_id = _extracted_case(helena)
    helena.post(f"/api/cases/{case_id}/submission", json={"supervisor": "Paul Mbarga"})
    paul = _login(app, "paul")
    dataset_id = paul.post(f"/api/extractions/{run_id}/validation",
                           json={"acknowledge_failed_checks": True}).get_json()["id"]
    paul.post(f"/api/datasets/{dataset_id}/analysis")
    assert paul.delete(f"/api/cases/{case_id}", json={}).status_code == 204

    ada = _login(app, "ada")
    [entry] = _entries(ada, "CASE")
    assert entry["detail"]["datasets"] == 1
    ada.post(f"/api/admin/archive/{entry['id']}/restore")
    dashboard = paul.get(f"/api/cases/{case_id}/analysis").get_json()
    assert dashboard["dataset"]["id"] == dataset_id and dashboard["case"]["status"] == "ANALYSED"


# --- documents ---------------------------------------------------------------
def test_a_deleted_document_comes_back_to_its_case(app):
    helena = _login(app, "helena")
    case_id, doc_id, run_id = _extracted_case(helena)
    assert helena.delete(f"/api/documents/{doc_id}").status_code == 200
    assert helena.get(f"/api/cases/{case_id}").get_json()["status"] == "CREATED"

    ada = _login(app, "ada")
    [entry] = _entries(ada, "DOCUMENT")
    assert entry["detail"]["file_name"] == "statement.pdf"
    ada.post(f"/api/admin/archive/{entry['id']}/restore")

    case = helena.get(f"/api/cases/{case_id}").get_json()
    assert [d["id"] for d in case["documents"]] == [doc_id]
    assert case["status"] == "EXTRACTED"  # it was CREATED only because the document left
    run = helena.get(f"/api/extractions/{run_id}").get_json()
    assert doc_id in run["document_ids"]


def test_a_document_of_a_deleted_case_waits_for_its_case(app):
    helena = _login(app, "helena")
    case_id, doc_id, _run = _extracted_case(helena)
    helena.post(f"/api/cases/{case_id}/documents",
                data={"file": (io.BytesIO(b"%PDF-1.7 second"), "notes.pdf")},
                content_type="multipart/form-data")
    helena.delete(f"/api/documents/{doc_id}")
    helena.delete(f"/api/cases/{case_id}", json={})
    ada = _login(app, "ada")
    [document] = _entries(ada, "DOCUMENT")
    refused = ada.post(f"/api/admin/archive/{document['id']}/restore")
    assert refused.status_code == 409 and "restore the case first" in refused.get_json()["detail"]
    [case] = _entries(ada, "CASE")
    ada.post(f"/api/admin/archive/{case['id']}/restore")
    assert ada.post(f"/api/admin/archive/{document['id']}/restore").status_code == 200
    assert len(helena.get(f"/api/cases/{case_id}").get_json()["documents"]) == 2


# --- accounts ----------------------------------------------------------------
def test_a_deleted_account_is_restored_with_its_password(app):
    paul = _login(app, "paul")
    eric_id = next(u["id"] for u in paul.get("/api/users").get_json() if u["username"] == "eric")
    assert paul.delete(f"/api/users/{eric_id}").status_code == 204

    ada = _login(app, "ada")
    [entry] = _entries(ada, "USER")
    assert entry["label"] == "Eric Fotso" and entry["detail"]["role"] == "ANALYST"
    assert "password_hash" not in str(entry)
    ada.post(f"/api/admin/archive/{entry['id']}/restore")
    _login(app, "eric")  # signs in again with the same password


def test_restoring_refuses_what_would_clash(app):
    paul = _login(app, "paul")
    eric_id = next(u["id"] for u in paul.get("/api/users").get_json() if u["username"] == "eric")
    paul.delete(f"/api/users/{eric_id}")
    paul.post("/api/users", json={"username": "eric", "full_name": "Eric Other",
                                  "role": "ANALYST", "password": PASSWORD})
    ada = _login(app, "ada")
    [entry] = _entries(ada, "USER")
    refused = ada.post(f"/api/admin/archive/{entry['id']}/restore")
    assert refused.status_code == 409 and "eric" in refused.get_json()["detail"]
    assert len(_entries(ada)) == 1  # still in the archive


# --- corpus and campaigns ----------------------------------------------------
def test_corpus_files_and_packages_go_to_the_archive(app, tmp_path):
    ada = _login(app, "ada")
    ada.post("/api/admin/corpus/packages", json={"name": "RP009"})
    ada.post("/api/admin/corpus/RP009/files",
             data={"files": (io.BytesIO(b"%PDF-1.7 corpus"), "statement.pdf")},
             content_type="multipart/form-data")
    assert ada.delete("/api/admin/corpus/RP009/files/statement.pdf").status_code == 200
    assert not (tmp_path / "corpus" / "RP009" / "statement.pdf").exists()
    assert ada.delete("/api/admin/corpus/RP009").status_code == 204

    package, file = _entries(ada, "CORPUS_PACKAGE")[0], _entries(ada, "CORPUS_FILE")[0]
    assert ada.post(f"/api/admin/archive/{package['id']}/restore").status_code == 200
    assert ada.post(f"/api/admin/archive/{file['id']}/restore").status_code == 200
    restored = tmp_path / "corpus" / "RP009" / "statement.pdf"
    assert restored.read_bytes() == b"%PDF-1.7 corpus"


def test_a_deleted_campaign_is_restored(app):
    ada = _login(app, "ada")
    campaign = E.EvaluationCampaign(kind=E.CAMPAIGN_SENSITIVITY, summary={"cells": []}, note="trial")
    app.config["container"].evaluations.add(campaign)
    ada.delete(f"/api/admin/campaigns/{campaign.id}")
    [entry] = _entries(ada, "CAMPAIGN")
    assert entry["label"].endswith("trial")
    ada.post(f"/api/admin/archive/{entry['id']}/restore")
    assert ada.get(f"/api/evaluations/{campaign.id}").get_json()["note"] == "trial"


# --- deleting for good, and who may -------------------------------------------
def test_deleting_for_good(app, tmp_path):
    ada = _login(app, "ada")
    ada.post("/api/admin/corpus/packages", json={"name": "RP009"})
    ada.post("/api/admin/corpus/RP009/files",
             data={"files": (io.BytesIO(b"%PDF-1.7 corpus"), "statement.pdf")},
             content_type="multipart/form-data")
    ada.delete("/api/admin/corpus/RP009/files/statement.pdf")
    [entry] = _entries(ada)
    assert list((tmp_path / "archive").rglob("statement.pdf"))
    assert ada.delete(f"/api/admin/archive/{entry['id']}").status_code == 204
    assert _entries(ada) == []
    assert not list((tmp_path / "archive").rglob("statement.pdf"))
    assert ada.post(f"/api/admin/archive/{entry['id']}/restore").status_code == 404
    actions = [e["action"] for e in ada.get("/api/admin/audit").get_json()["entries"]]
    assert "PURGED" in actions


def test_only_the_administrators_see_the_archive(app):
    for username in ("helena", "paul"):
        assert _login(app, username).get("/api/admin/archive").status_code == 403
    assert _login(app, "ada").get("/api/admin/archive").status_code == 200
