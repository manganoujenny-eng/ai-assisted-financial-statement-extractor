"""'Read with AI' — the case's PDFs read by the model from page images.

POST /api/cases/<id>/extractions  {"engine": "vision"}

* only the analyst who owns the case starts it (like any extraction);
* it needs the model (ANTHROPIC_API_KEY): without it, a clear refusal;
* it needs at least one PDF in the case;
* the run is an ordinary extraction run (engine LLM_VISION): reviewed,
  corrected and validated exactly like the others, and kept next to them.
"""

from __future__ import annotations

import io
from decimal import Decimal

import pytest
from werkzeug.security import generate_password_hash

from app import create_app
from app.config import Config
from app.domain import entities as E
from app.domain.ports import StructuredItem, StructuringResult

from integration.test_api_end_to_end import FakeReader, FakeStructurer

PASSWORD = "correct-horse"


class FakeVision:
    engine = "LLM_VISION"

    def __init__(self, amounts):
        self.amounts = amounts
        self.read = []

    def structure_file(self, path):
        self.read.append(path)
        return StructuringResult(
            items=[StructuredItem(item_code=k, amount=str(v), year="N", source_page=1)
                   for k, v in self.amounts.items()],
            engine=self.engine, model="fake-vision", prompt_version="vision-v1",
            cost_usd=Decimal("0.40"),
        )


@pytest.fixture
def app(tmp_path, balanced_amounts):
    app = create_app(Config(storage="memory", upload_dir=tmp_path, auth_required=True))
    c = app.config["container"]
    c.extraction.readers = [FakeReader()]
    c.extraction.structurer = FakeStructurer({})  # the OCR found nothing
    c.vision = FakeVision(balanced_amounts)
    for username, full_name, role in [("helena", "Helena Ndongo", E.ROLE_ANALYST),
                                      ("eric", "Eric Fotso", E.ROLE_ANALYST),
                                      ("paul", "Paul Mbarga", E.ROLE_SUPERVISOR)]:
        c.users.add(E.User(username=username, full_name=full_name, role=role,
                           password_hash=generate_password_hash(PASSWORD)))
    return app


def _login(app, username):
    http = app.test_client()
    assert http.post("/api/auth/login",
                     json={"username": username, "password": PASSWORD}).status_code == 200
    return http


def _case_with_scan(http, name="scan.pdf"):
    case_id = http.post("/api/cases", json={"client": "SCAN SA", "fiscal_year": 2024}).get_json()["id"]
    http.post(f"/api/cases/{case_id}/documents",
              data={"file": (io.BytesIO(b"%PDF-1.7 scanned"), name)},
              content_type="multipart/form-data")
    return case_id


def test_the_ocr_fails_then_the_model_reads_the_pages(app):
    helena = _login(app, "helena")
    case_id = _case_with_scan(helena)
    failed = helena.post(f"/api/cases/{case_id}/extractions")
    assert failed.status_code == 422  # the OCR / rules found nothing

    run = helena.post(f"/api/cases/{case_id}/extractions", json={"engine": "vision"})
    assert run.status_code == 201
    body = run.get_json()
    assert body["engine"] == "LLM_VISION" and body["status"] == "EXTRACTED"
    assert body["model"] == "fake-vision" and Decimal(body["cost_usd"]) == Decimal("0.40")
    assert helena.get(f"/api/cases/{case_id}").get_json()["status"] == "EXTRACTED"
    assert len(app.config["container"].vision.read) == 1
    audit = app.config["container"].audit
    assert any(e.action == "EXTRACTED" and e.detail.get("engine") == "LLM_VISION"
               for e in audit.all())


def test_only_the_case_analyst_reads_with_ai(app):
    case_id = _case_with_scan(_login(app, "helena"))
    for username in ("eric", "paul"):
        refused = _login(app, username).post(f"/api/cases/{case_id}/extractions",
                                             json={"engine": "vision"})
        assert refused.status_code == 403, username


def test_without_the_model_it_says_why(app):
    app.config["container"].vision = None
    helena = _login(app, "helena")
    case_id = _case_with_scan(helena)
    refused = helena.post(f"/api/cases/{case_id}/extractions", json={"engine": "vision"})
    assert refused.status_code == 409 and "ANTHROPIC_API_KEY" in refused.get_json()["detail"]


def test_it_needs_a_pdf(app):
    helena = _login(app, "helena")
    case_id = _case_with_scan(helena, name="statement.xlsx")
    refused = helena.post(f"/api/cases/{case_id}/extractions", json={"engine": "vision"})
    assert refused.status_code == 409 and "PDF" in refused.get_json()["detail"]


def test_an_unknown_engine_is_refused(app):
    helena = _login(app, "helena")
    case_id = _case_with_scan(helena)
    assert helena.post(f"/api/cases/{case_id}/extractions",
                       json={"engine": "magic"}).status_code == 422
