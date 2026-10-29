"""Supervisors discuss a case between themselves.

Only the supervisor a case is assigned to acts on it (validate, send
back...). Another supervisor who has an opinion on it opens the case and
writes in its discussion; the assigned supervisor sees it (bell, My cases)
and replies. The discussion is always about that one case.

* the case must have a supervisor (submitted, or validated): that is who
  the others talk to;
* the assigned supervisor does not write first — nobody writes to
  themselves; they reply once another supervisor has written;
* the case's supervisor is the one it is assigned to NOW: the one it was
  last submitted to, or — once validated — the one who validated it (a
  case validated by A, reopened and submitted to B is B's case);
* every message shows its author; its author may edit it, or delete it
  for everyone (the others see "deleted by ..."); anyone may delete a
  message for themselves only (it disappears from their own view);
* the others see who is writing at the moment;
* analysts and administrators take no part;
* a new message shows in the bell and on My cases until the thread is
  opened; the thread goes to the archive with its case and comes back;
* every message, edit and deletion is in the audit log.
"""

from __future__ import annotations

import io

import pytest
from sqlalchemy import create_engine, inspect, text
from werkzeug.security import generate_password_hash

from app import create_app
from app.config import Config
from app.domain import entities as E
from app.infra.db.session import create_schema

from integration.test_api_end_to_end import FakeReader, FakeStructurer

PASSWORD = "correct-horse"
PEOPLE = [
    ("ada", "Ada Admin", E.ROLE_ADMIN),
    ("paul", "Paul Mbarga", E.ROLE_SUPERVISOR),
    ("sara", "Sara Eyenga", E.ROLE_SUPERVISOR),
    ("helena", "Helena Ndongo", E.ROLE_ANALYST),
]


def _build(config, balanced_amounts):
    app = create_app(config)
    c = app.config["container"]
    c.extraction.readers = [FakeReader()]
    c.extraction.structurer = FakeStructurer(balanced_amounts)
    for username, full_name, role in PEOPLE:
        c.users.add(E.User(username=username, full_name=full_name, role=role,
                           password_hash=generate_password_hash(PASSWORD)))
    return app


@pytest.fixture
def app(tmp_path, balanced_amounts):
    return _build(Config(storage="memory", upload_dir=tmp_path, auth_required=True,
                         archive_dir=tmp_path / "archive"), balanced_amounts)


def _login(app, username):
    http = app.test_client()
    assert http.post("/api/auth/login",
                     json={"username": username, "password": PASSWORD}).status_code == 200
    return http


def _case(app, submit=True):
    """A case of Helena's, submitted to Paul: Paul's case."""
    helena = _login(app, "helena")
    case_id = helena.post("/api/cases", json={"client": "ACME", "fiscal_year": 2024}).get_json()["id"]
    helena.post(f"/api/cases/{case_id}/documents",
                data={"file": (io.BytesIO(b"%PDF-1.7 talk"), "statement.pdf")},
                content_type="multipart/form-data")
    helena.post(f"/api/cases/{case_id}/extractions")
    if submit:
        helena.post(f"/api/cases/{case_id}/submission", json={"supervisor": "Paul Mbarga"})
    return case_id


def _say(http, case_id, message):
    return http.post(f"/api/cases/{case_id}/discussion", json={"message": message})


def _thread(http, case_id):
    return http.get(f"/api/cases/{case_id}/discussion").get_json()


# --- who writes, and when ------------------------------------------------------
def test_another_supervisor_writes_and_the_assigned_one_replies(app):
    case_id = _case(app)
    sara, paul = _login(app, "sara"), _login(app, "paul")
    posted = _say(sara, case_id, "BZ looks off by 235 — worth checking the scan.")
    assert posted.status_code == 201 and posted.get_json()["author"] == "Sara Eyenga"

    assert _say(paul, case_id, "Agreed, I will send it back.").status_code == 201
    assert _say(sara, case_id, "Thanks.").status_code == 201
    thread = _thread(paul, case_id)
    assert [(m["author"], m["message"], m["mine"]) for m in thread["messages"]] == [
        ("Sara Eyenga", "BZ looks off by 235 — worth checking the scan.", False),
        ("Paul Mbarga", "Agreed, I will send it back.", True),
        ("Sara Eyenga", "Thanks.", False),
    ]
    assert thread["assigned_to"] == "Paul Mbarga"


def test_the_assigned_supervisor_does_not_write_first(app):
    case_id = _case(app)
    paul, sara = _login(app, "paul"), _login(app, "sara")

    thread = _thread(paul, case_id)
    assert thread["messages"] == [] and thread["can_write"] is False
    assert thread["why_not"] == "WAIT_FOR_MESSAGE"
    refused = _say(paul, case_id, "Hello me.")
    assert refused.status_code == 409

    assert _thread(sara, case_id)["can_write"] is True
    _say(sara, case_id, "A point on DD.")
    assert _thread(paul, case_id)["can_write"] is True


def test_no_discussion_before_the_case_has_a_supervisor(app):
    case_id = _case(app, submit=False)
    sara = _login(app, "sara")
    thread = _thread(sara, case_id)
    assert thread["can_write"] is False and thread["why_not"] == "NO_SUPERVISOR"
    assert _say(sara, case_id, "Too early.").status_code == 409


def test_the_validator_keeps_the_discussion_after_validation(app):
    case_id = _case(app)
    paul, sara = _login(app, "paul"), _login(app, "sara")
    run_id = next(n["extraction_id"] for n in paul.get("/api/notifications").get_json()
                  if n["kind"] == "SUBMITTED" and n["case_id"] == case_id)
    assert paul.post(f"/api/extractions/{run_id}/validation",
                     json={"acknowledge_failed_checks": True}).status_code == 201
    assert paul.get(f"/api/cases/{case_id}").get_json()["status"] == "VALIDATED"
    assert _thread(sara, case_id)["assigned_to"] == "Paul Mbarga"
    assert _say(sara, case_id, "Nice work on this one.").status_code == 201


def _analyse_and_reopen(app, case_id, validator):
    """The case is validated by ``validator``, analysed, then reopened by
    its analyst: its old validation stays in the history."""
    http = _login(app, validator)
    run_id = next(n["extraction_id"] for n in http.get("/api/notifications").get_json()
                  if n["kind"] == "SUBMITTED" and n["case_id"] == case_id)
    dataset_id = http.post(f"/api/extractions/{run_id}/validation",
                           json={"acknowledge_failed_checks": True}).get_json()["id"]
    assert http.post(f"/api/datasets/{dataset_id}/analysis").status_code in (200, 201)
    helena = _login(app, "helena")
    assert helena.post(f"/api/cases/{case_id}/reopen", json={"reason": "fix DD"}).status_code == 200
    return helena


def test_a_reopened_case_belongs_to_the_supervisor_it_is_submitted_to_now(app):
    """Validated by Paul, reopened, submitted to Sara: Sara's case now."""
    case_id = _case(app)
    helena = _analyse_and_reopen(app, case_id, "paul")
    assert helena.post(f"/api/cases/{case_id}/submission",
                       json={"supervisor": "Sara Eyenga"}).status_code == 200
    sara, paul = _login(app, "sara"), _login(app, "paul")

    thread = _thread(sara, case_id)
    assert thread["assigned_to"] == "Sara Eyenga"
    assert thread["can_write"] is False and thread["why_not"] == "WAIT_FOR_MESSAGE"
    assert _say(sara, case_id, "Talking to myself.").status_code == 409

    assert _thread(paul, case_id)["can_write"] is True
    assert _say(paul, case_id, "I validated the first version: check DD.").status_code == 201
    assert _say(sara, case_id, "Thanks, I will.").status_code == 201


def test_only_supervisors_take_part(app):
    case_id = _case(app)
    for username in ("helena", "ada"):
        http = _login(app, username)
        assert http.get(f"/api/cases/{case_id}/discussion").status_code == 403, username
        assert _say(http, case_id, "hello").status_code == 403, username
        assert http.post(f"/api/cases/{case_id}/discussion/typing").status_code == 403, username


def test_a_message_is_not_empty_nor_endless(app):
    case_id = _case(app)
    sara = _login(app, "sara")
    assert _say(sara, case_id, "   ").status_code == 422
    assert _say(sara, case_id, "x" * 2001).status_code == 422


# --- edit, delete -------------------------------------------------------------
def test_the_author_edits_their_message(app):
    case_id = _case(app)
    sara, paul = _login(app, "sara"), _login(app, "paul")
    message_id = _say(sara, case_id, "Check BZ.").get_json()["id"]

    edited = sara.patch(f"/api/cases/{case_id}/discussion/{message_id}",
                        json={"message": "Check BZ and DZ."})
    assert edited.status_code == 200
    seen = _thread(paul, case_id)["messages"][0]
    assert seen["message"] == "Check BZ and DZ." and seen["edited_at"] is not None

    refused = paul.patch(f"/api/cases/{case_id}/discussion/{message_id}", json={"message": "no"})
    assert refused.status_code == 403
    assert sara.patch(f"/api/cases/{case_id}/discussion/{message_id}",
                      json={"message": "  "}).status_code == 422


def test_a_deleted_message_shows_as_deleted(app):
    case_id = _case(app)
    sara, paul = _login(app, "sara"), _login(app, "paul")
    message_id = _say(sara, case_id, "Ignore DD.").get_json()["id"]

    assert paul.delete(f"/api/cases/{case_id}/discussion/{message_id}").status_code == 403
    assert sara.delete(f"/api/cases/{case_id}/discussion/{message_id}").status_code == 204

    seen = _thread(paul, case_id)["messages"]
    assert len(seen) == 1
    assert seen[0]["deleted"] is True and seen[0]["message"] is None
    assert seen[0]["author"] == "Sara Eyenga"
    # Nothing left to edit; deleting twice changes nothing.
    assert sara.patch(f"/api/cases/{case_id}/discussion/{message_id}",
                      json={"message": "back"}).status_code == 409
    assert sara.delete(f"/api/cases/{case_id}/discussion/{message_id}").status_code == 409
    assert paul.patch(f"/api/cases/{case_id}/discussion/nope",
                      json={"message": "x"}).status_code == 404


def test_delete_for_me_hides_a_message_from_me_only(app):
    case_id = _case(app)
    sara, paul = _login(app, "sara"), _login(app, "paul")
    first = _say(sara, case_id, "First.").get_json()["id"]
    _say(sara, case_id, "Second.")

    # Anyone may delete any message for themselves, even someone else's.
    assert paul.delete(f"/api/cases/{case_id}/discussion/{first}?for=me").status_code == 204
    assert [m["message"] for m in _thread(paul, case_id)["messages"]] == ["Second."]
    assert [m["message"] for m in _thread(sara, case_id)["messages"]] == ["First.", "Second."]
    # Hidden twice: nothing more happens.
    assert paul.delete(f"/api/cases/{case_id}/discussion/{first}?for=me").status_code == 204


def test_the_deleted_notice_can_be_removed_for_me(app):
    case_id = _case(app)
    sara, paul = _login(app, "sara"), _login(app, "paul")
    message_id = _say(sara, case_id, "Oops.").get_json()["id"]
    sara.delete(f"/api/cases/{case_id}/discussion/{message_id}")  # for everyone
    assert _thread(paul, case_id)["messages"][0]["deleted"] is True
    assert paul.delete(f"/api/cases/{case_id}/discussion/{message_id}?for=me").status_code == 204
    assert _thread(paul, case_id)["messages"] == []
    assert len(_thread(sara, case_id)["messages"]) == 1  # still there for Sara


def test_a_message_deleted_for_me_is_no_longer_announced_to_me(app):
    case_id = _case(app)
    sara, paul = _login(app, "sara"), _login(app, "paul")
    message_id = _say(sara, case_id, "Never mind.").get_json()["id"]
    paul.delete(f"/api/cases/{case_id}/discussion/{message_id}?for=me")
    assert not [n for n in paul.get("/api/notifications").get_json() if n["kind"] == "DISCUSSION"]
    mine = [e for e in paul.get("/api/my-cases").get_json() if e["id"] == case_id][0]
    assert mine["discussion"] == {"messages": 0, "unread": 0}


def test_delete_for_me_needs_a_message_of_this_case(app):
    case_id = _case(app)
    paul = _login(app, "paul")
    assert paul.delete(f"/api/cases/{case_id}/discussion/nope?for=me").status_code == 404
    assert paul.delete(f"/api/cases/{case_id}/discussion/x?for=nobody").status_code == 422


# --- who is writing ------------------------------------------------------------
def test_the_others_see_who_is_writing(app):
    case_id = _case(app)
    sara, paul = _login(app, "sara"), _login(app, "paul")
    assert sara.post(f"/api/cases/{case_id}/discussion/typing").status_code == 204
    assert _thread(paul, case_id)["typing"] == ["Sara Eyenga"]
    assert _thread(sara, case_id)["typing"] == []  # not to herself


def test_writing_stops_showing_after_a_few_seconds(app):
    case_id = _case(app)
    sara, paul = _login(app, "sara"), _login(app, "paul")
    board = app.config["container"].discussion
    sara.post(f"/api/cases/{case_id}/discussion/typing")
    board.clock = lambda: board.now() + 60  # a minute later
    assert _thread(paul, case_id)["typing"] == []


# --- notifications, My cases --------------------------------------------------
def test_a_new_message_is_notified_until_the_thread_is_opened(app):
    case_id = _case(app)
    sara, paul = _login(app, "sara"), _login(app, "paul")
    _say(sara, case_id, "Look at DD please.")

    discussion = [n for n in paul.get("/api/notifications").get_json() if n["kind"] == "DISCUSSION"]
    assert len(discussion) == 1
    assert discussion[0]["author"] == "Sara Eyenga" and discussion[0]["count"] == 1
    assert not [n for n in sara.get("/api/notifications").get_json() if n["kind"] == "DISCUSSION"]

    mine = [e for e in paul.get("/api/my-cases").get_json() if e["id"] == case_id][0]
    assert mine["discussion"] == {"messages": 1, "unread": 1}

    _thread(paul, case_id)  # opened: read
    assert not [n for n in paul.get("/api/notifications").get_json() if n["kind"] == "DISCUSSION"]
    mine = [e for e in paul.get("/api/my-cases").get_json() if e["id"] == case_id][0]
    assert mine["discussion"] == {"messages": 1, "unread": 0}


def test_a_deleted_message_is_no_longer_announced(app):
    case_id = _case(app)
    sara, paul = _login(app, "sara"), _login(app, "paul")
    message_id = _say(sara, case_id, "Oops, wrong case.").get_json()["id"]
    sara.delete(f"/api/cases/{case_id}/discussion/{message_id}")
    assert not [n for n in paul.get("/api/notifications").get_json() if n["kind"] == "DISCUSSION"]


# --- archive, audit -------------------------------------------------------------
def test_the_thread_is_archived_and_restored_with_its_case(app):
    case_id = _case(app)
    _say(_login(app, "sara"), case_id, "Keep me.")
    paul = _login(app, "paul")
    paul.post(f"/api/cases/{case_id}/correction-request", json={"message": "redo"})
    assert _login(app, "helena").delete(f"/api/cases/{case_id}", json={}).status_code == 204
    assert paul.get(f"/api/cases/{case_id}/discussion").status_code == 404

    ada = _login(app, "ada")
    entry = ada.get("/api/admin/archive?kind=CASE").get_json()["entries"][0]
    assert entry["detail"]["messages"] == 1
    ada.post(f"/api/admin/archive/{entry['id']}/restore")
    messages = _thread(paul, case_id)["messages"]
    assert [m["message"] for m in messages] == ["Keep me."]


def test_every_message_edit_and_deletion_is_audited(app):
    case_id = _case(app)
    sara = _login(app, "sara")
    message_id = _say(sara, case_id, "Audited.").get_json()["id"]
    sara.patch(f"/api/cases/{case_id}/discussion/{message_id}", json={"message": "Audited twice."})
    sara.delete(f"/api/cases/{case_id}/discussion/{message_id}")
    ada = _login(app, "ada")
    for action in ("DISCUSSION_MESSAGE", "DISCUSSION_EDITED", "DISCUSSION_DELETED"):
        entries = ada.get(f"/api/admin/audit?action={action}").get_json()["entries"]
        assert entries and entries[0]["author"] == "Sara Eyenga", action
        assert entries[0]["entity_id"] == case_id, action


# --- on a real database -------------------------------------------------------
def test_the_discussion_on_a_real_database(tmp_path, balanced_amounts):
    app = _build(Config(storage="sql", database_url=f"sqlite:///{tmp_path / 'd.db'}",
                        upload_dir=tmp_path / "up", auth_required=True,
                        archive_dir=tmp_path / "archive"), balanced_amounts)
    case_id = _case(app)
    sara, paul = _login(app, "sara"), _login(app, "paul")
    first = _say(sara, case_id, "On SQL.").get_json()["id"]
    second = _say(sara, case_id, "Second thought.").get_json()["id"]
    assert [n["kind"] for n in paul.get("/api/notifications").get_json()].count("DISCUSSION") == 1
    sara.patch(f"/api/cases/{case_id}/discussion/{first}", json={"message": "On SQL, edited."})
    sara.delete(f"/api/cases/{case_id}/discussion/{second}")
    messages = _thread(paul, case_id)["messages"]
    assert [(m["message"], m["deleted"], m["edited_at"] is not None) for m in messages] == [
        ("On SQL, edited.", False, True), (None, True, False)]
    assert [n["kind"] for n in paul.get("/api/notifications").get_json()].count("DISCUSSION") == 0
    paul.delete(f"/api/cases/{case_id}/discussion/{first}?for=me")
    assert [m["deleted"] for m in _thread(paul, case_id)["messages"]] == [True]
    assert len(_thread(sara, case_id)["messages"]) == 2


def test_an_existing_discussion_table_gets_the_new_columns(tmp_path):
    """The table was created on 27 Oct without edited_at / deleted_at, and
    create_all never alters a table: create_schema adds them, keeping the
    messages."""
    engine = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with engine.begin() as db:
        db.execute(text("CREATE TABLE case_comment (id VARCHAR(36) PRIMARY KEY, "
                        "case_id VARCHAR(36) NOT NULL, author VARCHAR(100) NOT NULL, "
                        "message TEXT NOT NULL, created_at DATETIME)"))
        db.execute(text("INSERT INTO case_comment VALUES ('m1', 'c1', 'Sara', 'kept', '2026-10-27 10:00:00')"))
    create_schema(engine)
    create_schema(engine)  # twice: nothing to do the second time
    columns = {c["name"] for c in inspect(engine).get_columns("case_comment")}
    assert {"edited_at", "deleted_at"} <= columns
    with engine.connect() as db:
        assert db.execute(text("SELECT message FROM case_comment")).scalar() == "kept"