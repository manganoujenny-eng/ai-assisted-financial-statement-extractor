"""sign-in, roles, user administration, supervisor overview.

These tests turn sign-in ON (Config(auth_required=True)); the rest of the
suite runs with it off (see conftest.py).
"""

from __future__ import annotations

import io

import pytest
from werkzeug.security import generate_password_hash

from app import create_app
from app.api.serialisation import document_display_name, document_type_label
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
        ("helena", "Helena Ndongo", E.ROLE_ANALYST),
        ("eric", "Eric Fotso", E.ROLE_ANALYST),
    ]:
        c.users.add(
            E.User(username=username, full_name=full_name, role=role,
                   password_hash=generate_password_hash(PASSWORD))
        )
    return app


def _login(app, username):
    http = app.test_client()
    response = http.post("/api/auth/login", json={"username": username, "password": PASSWORD})
    assert response.status_code == 200, response.get_json()
    return http


def _case_with_run(http, client="ACME SARL"):
    case_id = http.post("/api/cases", json={"client": client, "fiscal_year": 2024}).get_json()["id"]
    http.post(
        f"/api/cases/{case_id}/documents",
        data={"file": (io.BytesIO(b"%PDF-1.7 x"), "statement.pdf")},
        content_type="multipart/form-data",
    )
    run_id = http.post(f"/api/cases/{case_id}/extractions").get_json()["id"]
    return case_id, run_id


# --- sign-in ------------------------------------------------------------------
def test_everything_but_health_and_login_needs_a_session(app):
    http = app.test_client()
    assert http.get("/api/health").status_code == 200
    assert http.get("/api/cases").status_code == 401
    assert http.get("/api/auth/me").status_code == 401


def test_wrong_password_and_unknown_user_get_the_same_answer(app):
    http = app.test_client()
    wrong = http.post("/api/auth/login", json={"username": "helena", "password": "nope-nope"})
    unknown = http.post("/api/auth/login", json={"username": "ghost", "password": PASSWORD})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.get_json()["detail"] == unknown.get_json()["detail"]


def test_login_me_logout(app):
    http = _login(app, "HELENA")  # username is case-insensitive
    me = http.get("/api/auth/me").get_json()
    assert me["full_name"] == "Helena Ndongo" and me["role"] == "ANALYST"
    assert "password_hash" not in me
    assert http.post("/api/auth/logout").status_code == 204
    assert http.get("/api/cases").status_code == 401


def test_deactivated_user_is_signed_out_and_cannot_sign_in(app):
    helena = _login(app, "helena")
    paul = _login(app, "paul")
    helena_id = next(u["id"] for u in paul.get("/api/users").get_json() if u["username"] == "helena")
    assert paul.patch(f"/api/users/{helena_id}", json={"active": False}).status_code == 200
    assert helena.get("/api/cases").status_code == 401
    assert app.test_client().post(
        "/api/auth/login", json={"username": "helena", "password": PASSWORD}
    ).status_code == 401


# --- names come from the session, roles are enforced ---------------------------
def test_records_carry_the_signed_in_name_not_what_the_body_claims(app):
    helena = _login(app, "helena")
    case = helena.post(
        "/api/cases", json={"client": "X", "fiscal_year": 2024, "analyst": "Eric Fotso"}
    ).get_json()
    assert case["analyst"] == "Helena Ndongo"

    case_id, run_id = _case_with_run(helena)
    fields = helena.get(f"/api/extractions/{run_id}/fields").get_json()["fields"]
    bz = next(f for f in fields if f["item_code"] == "BZ")
    corrected = helena.patch(
        f"/api/fields/{bz['id']}", json={"amount": "11246235", "author": "Paul Mbarga"}
    ).get_json()["field"]
    assert corrected["corrected_by"] == "Helena Ndongo"


def test_only_a_supervisor_can_validate_and_validated_by_is_their_name(app):
    helena = _login(app, "helena")
    case_id, run_id = _case_with_run(helena)
    fields = helena.get(f"/api/extractions/{run_id}/fields").get_json()["fields"]
    bz = next(f for f in fields if f["item_code"] == "BZ")
    helena.patch(f"/api/fields/{bz['id']}", json={"amount": "11246235"})

    assert helena.post(f"/api/cases/{case_id}/submission").status_code == 200
    refused = helena.post(f"/api/extractions/{run_id}/validation", json={"supervisor": "Paul Mbarga"})
    assert refused.status_code == 403

    paul = _login(app, "paul")
    dataset = paul.post(f"/api/extractions/{run_id}/validation", json={"supervisor": "someone"}).get_json()
    assert dataset["validated_by"] == "Paul Mbarga"


def test_only_an_analyst_can_create_a_case(app):
    paul = _login(app, "paul")
    refused = paul.post(
        "/api/cases", json={"client": "Y", "fiscal_year": 2024, "analyst": "Eric Fotso"}
    )
    assert refused.status_code == 403
    assert refused.get_json()["detail"] == "only an analyst can create a case"
    assert paul.get("/api/cases").get_json() == []

    eric = _login(app, "eric")
    case = eric.post("/api/cases", json={"client": "Y", "fiscal_year": 2024}).get_json()
    assert case["analyst"] == "Eric Fotso"


def test_analyst_sees_only_own_cases_on_my_cases(app):
    helena = _login(app, "helena")
    eric = _login(app, "eric")
    helena.post("/api/cases", json={"client": "H", "fiscal_year": 2024})
    eric.post("/api/cases", json={"client": "E", "fiscal_year": 2024})
    mine = helena.get("/api/my-cases?analyst=Eric Fotso").get_json()  # cannot peek
    assert [c["client"] for c in mine] == ["H"]
    paul = _login(app, "paul")
    assert [c["client"] for c in paul.get("/api/my-cases?analyst=Eric Fotso").get_json()] == ["E"]


def test_analyst_cannot_delete_validated_work_supervisor_deletes_analysed_only(app):
    helena = _login(app, "helena")
    case_id, run_id = _case_with_run(helena)
    helena.post(f"/api/cases/{case_id}/submission")
    paul = _login(app, "paul")
    dataset_id = paul.post(
        f"/api/extractions/{run_id}/validation", json={"acknowledge_failed_checks": True}
    ).get_json()["id"]
    assert helena.delete(f"/api/cases/{case_id}", json={"role": "supervisor"}).status_code == 409
    # VALIDATED but not analysed yet: still not the supervisor's to delete.
    refused = paul.delete(f"/api/cases/{case_id}", json={})
    assert refused.status_code == 409 and "ANALYSED" in refused.get_json()["detail"]
    paul.post(f"/api/datasets/{dataset_id}/analysis")
    assert paul.get(f"/api/cases/{case_id}").get_json()["status"] == "ANALYSED"
    assert paul.delete(f"/api/cases/{case_id}", json={}).status_code == 204


def test_supervisor_cannot_delete_a_case_in_progress(app):
    helena = _login(app, "helena")
    case_id, _ = _case_with_run(helena)
    paul = _login(app, "paul")
    assert paul.delete(f"/api/cases/{case_id}", json={}).status_code == 409
    assert helena.delete(f"/api/cases/{case_id}", json={}).status_code == 204


def test_supervisor_does_not_prepare_cases(app):
    helena = _login(app, "helena")
    case_id, run_id = _case_with_run(helena)
    case = helena.get(f"/api/cases/{case_id}").get_json()
    document_id = case["documents"][0]["id"]
    fields = helena.get(f"/api/extractions/{run_id}/fields").get_json()["fields"]

    paul = _login(app, "paul")
    upload = paul.post(
        f"/api/cases/{case_id}/documents",
        data={"file": (io.BytesIO(b"%PDF-1.7 y"), "other.pdf")},
        content_type="multipart/form-data",
    )
    attempts = {
        "upload": upload,
        "extract": paul.post(f"/api/cases/{case_id}/extractions"),
        "delete document": paul.delete(f"/api/documents/{document_id}", json={}),
        "edit": paul.patch(f"/api/cases/{case_id}", json={"client": "Z"}),
        "correct": paul.patch(f"/api/fields/{fields[0]['id']}", json={"amount": "1"}),
        "add item": paul.post(
            f"/api/extractions/{run_id}/fields", json={"item_code": "XB", "amount": "1"}
        ),
        "submit": paul.post(f"/api/cases/{case_id}/submission"),
    }
    assert {name: r.status_code for name, r in attempts.items()} == {
        name: 403 for name in attempts
    }
    # ...but reads everything, to review it.
    assert paul.get(f"/api/extractions/{run_id}/fields").status_code == 200


def test_an_analyst_cannot_work_on_another_analysts_case(app):
    helena = _login(app, "helena")
    case_id, run_id = _case_with_run(helena)
    eric = _login(app, "eric")
    assert eric.post(f"/api/cases/{case_id}/extractions").status_code == 403
    assert eric.post(f"/api/cases/{case_id}/submission").status_code == 403
    assert eric.delete(f"/api/cases/{case_id}", json={}).status_code == 403


def test_correction_request_goes_to_the_analyst_then_back_to_the_supervisor(app):
    helena = _login(app, "helena")
    eric = _login(app, "eric")
    paul = _login(app, "paul")
    case_id, run_id = _case_with_run(helena)

    assert paul.get("/api/notifications").get_json() == []
    helena.post(f"/api/cases/{case_id}/submission", json={"note": "please check BZ"})
    [note] = paul.get("/api/notifications").get_json()
    assert (note["kind"], note["author"], note["message"]) == (
        "SUBMITTED", "Helena Ndongo", "please check BZ"
    )

    # Only the supervisor sends back, and only with a message.
    assert helena.post(
        f"/api/cases/{case_id}/correction-request", json={"message": "x"}
    ).status_code == 403
    assert paul.post(f"/api/cases/{case_id}/correction-request", json={}).status_code == 422
    sent = paul.post(
        f"/api/cases/{case_id}/correction-request", json={"message": "BZ is wrong"}
    )
    assert sent.get_json()["status"] == "UNDER_REVIEW"

    assert paul.get("/api/notifications").get_json() == []
    assert eric.get("/api/notifications").get_json() == []  # not his case
    [note] = helena.get("/api/notifications").get_json()
    assert (note["kind"], note["author"], note["message"]) == (
        "CORRECTION_REQUESTED", "Paul Mbarga", "BZ is wrong"
    )

    # The analyst corrects and submits again; the request disappears.
    bz = next(
        f for f in helena.get(f"/api/extractions/{run_id}/fields").get_json()["fields"]
        if f["item_code"] == "BZ"
    )
    assert helena.patch(f"/api/fields/{bz['id']}", json={"amount": "11246235"}).status_code == 200
    helena.post(f"/api/cases/{case_id}/submission")
    assert helena.get("/api/notifications").get_json() == []
    assert paul.post(f"/api/extractions/{run_id}/validation", json={}).status_code == 201

    actions = [h["action"] for h in paul.get(f"/api/cases/{case_id}/history").get_json()]
    assert actions == ["SUBMITTED", "CORRECTION_REQUESTED", "SUBMITTED", "VALIDATED"]


def test_supervisor_can_send_back_a_validated_case(app):
    helena = _login(app, "helena")
    paul = _login(app, "paul")
    case_id, run_id = _case_with_run(helena)
    helena.post(f"/api/cases/{case_id}/submission")
    paul.post(f"/api/extractions/{run_id}/validation", json={"acknowledge_failed_checks": True})
    sent = paul.post(f"/api/cases/{case_id}/correction-request", json={"message": "recheck"})
    assert sent.get_json()["status"] == "UNDER_REVIEW"
    # The fields are editable again for the analyst.
    field = helena.get(f"/api/extractions/{run_id}/fields").get_json()["fields"][0]
    assert helena.patch(f"/api/fields/{field['id']}", json={"amount": "5"}).status_code == 200


# --- user administration --------------------------------------------------------
def test_user_admin_is_supervisor_only_and_never_exposes_hashes(app):
    helena = _login(app, "helena")
    assert helena.post("/api/users", json={"username": "x"}).status_code == 403
    paul = _login(app, "paul")
    created = paul.post(
        "/api/users",
        json={"username": "awa", "full_name": "Awa Bello", "role": "ANALYST", "password": "longenough"},
    )
    assert created.status_code == 201
    assert "password_hash" not in created.get_json()
    assert all("password_hash" not in u for u in paul.get("/api/users").get_json())
    assert app.test_client().post(
        "/api/auth/login", json={"username": "awa", "password": "longenough"}
    ).status_code == 200


@pytest.mark.parametrize(
    "body",
    [
        {"username": "helena", "full_name": "Other", "role": "ANALYST", "password": "longenough"},
        {"username": "new", "full_name": "helena ndongo", "role": "ANALYST", "password": "longenough"},
        {"username": "new", "full_name": "New", "role": "ANALYST", "password": "short"},
        {"username": "new", "full_name": "New", "role": "BOSS", "password": "longenough"},
        {"username": "has space", "full_name": "New", "role": "ANALYST", "password": "longenough"},
    ],
)
def test_bad_new_users_are_refused(app, body):
    paul = _login(app, "paul")
    assert paul.post("/api/users", json=body).status_code in (409, 422)


def test_the_last_supervisor_cannot_be_removed_or_self_deactivated(app):
    paul = _login(app, "paul")
    paul_id = next(u["id"] for u in paul.get("/api/users").get_json() if u["username"] == "paul")
    assert paul.patch(f"/api/users/{paul_id}", json={"active": False}).status_code == 409
    assert paul.patch(f"/api/users/{paul_id}", json={"role": "ANALYST"}).status_code == 409


def test_renaming_a_user_moves_their_cases(app):
    helena = _login(app, "helena")
    helena.post("/api/cases", json={"client": "H", "fiscal_year": 2024})
    paul = _login(app, "paul")
    helena_id = next(u["id"] for u in paul.get("/api/users").get_json() if u["username"] == "helena")
    assert paul.patch(f"/api/users/{helena_id}", json={"full_name": "Helena N. Ndongo"}).status_code == 200
    mine = helena.get("/api/my-cases").get_json()
    assert [(c["client"], c["analyst"]) for c in mine] == [("H", "Helena N. Ndongo")]


def test_change_own_password(app):
    helena = _login(app, "helena")
    assert helena.post(
        "/api/auth/password", json={"current_password": "wrong", "new_password": "new-password"}
    ).status_code == 401
    assert helena.post(
        "/api/auth/password", json={"current_password": PASSWORD, "new_password": "new-password"}
    ).status_code == 204
    assert app.test_client().post(
        "/api/auth/login", json={"username": "helena", "password": "new-password"}
    ).status_code == 200


# --- supervisor overview -------------------------------------------------------
def test_supervisor_overview(app):
    helena = _login(app, "helena")
    eric = _login(app, "eric")
    paul = _login(app, "paul")

    # Helena: one case awaiting validation. Eric: one validated with failures.
    h1, _ = _case_with_run(helena, client="H1")
    helena.post(f"/api/cases/{h1}/submission")
    e1, eric_run = _case_with_run(eric, client="E1")
    eric.post(f"/api/cases/{e1}/submission")
    paul.post(f"/api/extractions/{eric_run}/validation", json={"acknowledge_failed_checks": True})

    assert helena.get("/api/supervisor/overview").status_code == 403
    overview = paul.get("/api/supervisor/overview").get_json()

    assert overview["totals"]["cases"] == 2
    assert overview["totals"]["awaiting_validation"] == 1
    assert overview["totals"]["validated_with_failures"] == 1
    assert overview["totals"]["analysts"] == 2
    assert [r["client"] for r in overview["queues"]["awaiting_validation"]] == ["H1"]
    assert overview["queues"]["validated_with_failures"][0]["validated_by"] == "Paul Mbarga"

    per = {a["analyst"]: a for a in overview["analysts"]}
    assert per["Helena Ndongo"]["in_progress"] == 1
    assert per["Eric Fotso"]["validated"] == 1
    assert per["Eric Fotso"]["fields_proposed"] > 0

    r1 = next(r for r in overview["ratios"] if r["code"] == "R1")
    assert r1["computed"] == 1 and r1["threshold"] == "1.0"
    assert any(ch["code"] == "CHK001" and ch["failed"] == 1 for ch in overview["checks"])


# --- document names (small update) ------------------------------------------
def test_document_display_name_and_type_label():
    name = "81966f42-b33b-4b9d-9054-bb6571d8c156__Compte_de_resultat_SOCATRANS_2023_scan.pdf"
    assert document_display_name(name) == "Compte_de_resultat_SOCATRANS_2023_scan"
    assert document_display_name("plain.xlsx") == "plain"

    def doc(doc_type, scanned):
        return E.SourceDocument(file_name="f", doc_type=doc_type, sha256="x", is_scanned=scanned)

    assert document_type_label(doc("PDF", True)) == "Scanned PDF"
    assert document_type_label(doc("PDF", False)) == "Native PDF"
    assert document_type_label(doc("PDF", None)) == "PDF"
    assert document_type_label(doc("XLSX", None)) == "Excel"