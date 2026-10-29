"""Administration → Overview: the AI commentary row.

Every "draft again", and every re-validation of a reopened case, writes a
NEW commentary; the older one stays in the database (history) but can no
longer be approved: only the latest commentary of a case's current result
counts. So the overview says:

* ``pending``: commentaries really waiting for an analyst — the latest one
  of each case's current result, still a draft;
* ``replaced``: older drafts nobody will approve any more;
* ``calls``: how many times the model was called (each commentary is one
  call), and ``cost_usd`` the total of all those calls — not one call.
"""

from __future__ import annotations

import io
from decimal import Decimal

import pytest

from app import create_app
from app.config import Config

from integration.test_api_end_to_end import FakeReader, FakeStructurer
from integration.test_intergration_api import FakeWriter


@pytest.fixture
def app(tmp_path, balanced_amounts):
    app = create_app(Config(storage="memory", upload_dir=tmp_path))
    c = app.config["container"]
    c.extraction.readers = [FakeReader()]
    c.extraction.structurer = FakeStructurer(balanced_amounts)
    c.insight.writer = FakeWriter()  # each call costs 0.02 $
    return app


def _analysed_case(http, client="ACME"):
    case_id = http.post("/api/cases", json={"client": client, "fiscal_year": 2024,
                                            "analyst": "Helena"}).get_json()["id"]
    http.post(f"/api/cases/{case_id}/documents",
              data={"file": (io.BytesIO(b"%PDF-1.7 ai"), "statement.pdf")},
              content_type="multipart/form-data")
    run_id = http.post(f"/api/cases/{case_id}/extractions").get_json()["id"]
    http.post(f"/api/cases/{case_id}/submission", json={})
    dataset_id = http.post(f"/api/extractions/{run_id}/validation",
                           json={"supervisor": "Paul", "acknowledge_failed_checks": True}).get_json()["id"]
    analysed = http.post(f"/api/datasets/{dataset_id}/analysis").get_json()
    return case_id, analysed["ai_analysis"]


def _ai(http):
    return http.get("/api/admin/overview").get_json()["ai_analyses"]


def test_a_redrafted_commentary_is_not_pending_twice(app):
    http = app.test_client()
    case_id, _first = _analysed_case(http)
    http.post(f"/api/cases/{case_id}/ai-analysis", json={})  # draft again

    ai = _ai(http)
    assert ai["pending"] == 1      # only the latest draft waits for approval
    assert ai["replaced"] == 1     # the first one was replaced
    assert ai["calls"] == 2        # the model was called twice
    assert Decimal(ai["cost_usd"]) == Decimal("0.04")  # the sum, not one call


def test_an_approved_commentary_is_no_longer_pending(app):
    http = app.test_client()
    case_id, _ = _analysed_case(http)
    http.post(f"/api/cases/{case_id}/ai-analysis", json={})
    latest = http.get(f"/api/cases/{case_id}/analysis").get_json()["ai_analysis"]
    http.post(f"/api/ai-analyses/{latest['id']}/approval",
              json={"author": "Helena", "sections": latest["sections"]})

    ai = _ai(http)
    assert ai["pending"] == 0
    assert ai["by_status"]["APPROVED"] == 1
    assert ai["replaced"] == 1


def test_each_case_counts_once(app):
    http = app.test_client()
    _analysed_case(http, "ONE")
    _analysed_case(http, "TWO")
    ai = _ai(http)
    assert ai["pending"] == 2 and ai["replaced"] == 0 and ai["calls"] == 2