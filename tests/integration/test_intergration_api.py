"""Item 4 and the add-item feature, end to end through the HTTP API.

The model is a fake: these tests never call Anthropic. They prove the
wiring — figures go in, a draft is stored, nothing is shown as a conclusion
until a named analyst approves it.
"""

from __future__ import annotations

import io
from decimal import Decimal

import pytest

from app import create_app
from app.config import Config
from app.domain.ports import AnalysisDraft

from integration.test_api_end_to_end import FakeReader, FakeStructurer


class FakeWriter:
    def __init__(self):
        self.payloads = []

    def write(self, payload):
        self.payloads.append(payload)
        return AnalysisDraft(
            sections={
                "overview": "Draft overview.",
                "ratios": [{"code": r["code"], "commentary": f"{r['code']} draft."} for r in payload["ratios"]],
                "checks": "Checks draft.",
                "comparison": "No prior-period comparison is available.",
                "attention": ["Draft point"],
            },
            model="fake-model",
            prompt_version="analysis-v1",
            cost_usd=Decimal("0.02"),
        )


@pytest.fixture
def app_and_writer(tmp_path, balanced_amounts):
    app = create_app(Config(storage="memory", upload_dir=tmp_path))
    container = app.config["container"]
    container.extraction.readers = [FakeReader()]
    missing_xb = {k: v for k, v in balanced_amounts.items() if k != "XB"}
    container.extraction.structurer = FakeStructurer(missing_xb)
    writer = FakeWriter()
    container.insight.writer = writer
    return app, writer


def _extract(http, analyst="Helena"):
    case_id = http.post(
        "/api/cases", json={"client": "ACME SARL", "fiscal_year": 2024, "analyst": analyst}
    ).get_json()["id"]
    document_id = http.post(
        f"/api/cases/{case_id}/documents",
        data={"file": (io.BytesIO(b"%PDF-1.7 item4"), "statement.pdf")},
        content_type="multipart/form-data",
    ).get_json()["id"]
    run_id = http.post(f"/api/cases/{case_id}/extractions").get_json()["id"]
    return case_id, document_id, run_id


def _submit_and_validate(http, case_id, run_id, **body):
    """The analyst submits, then the supervisor validates (item 5 workflow)."""
    assert http.post(f"/api/cases/{case_id}/submission").status_code == 200
    return http.post(f"/api/extractions/{run_id}/validation", json=body)


def test_add_missing_item_then_validate_draft_and_approve(app_and_writer, balanced_amounts):
    app, writer = app_and_writer
    http = app.test_client()
    case_id, document_id, run_id = _extract(http)

    # FakeStructurer gets BZ wrong; fix it, then key in the missing XB.
    fields = http.get(f"/api/extractions/{run_id}/fields").get_json()["fields"]
    bz = next(f for f in fields if f["item_code"] == "BZ")
    http.patch(f"/api/fields/{bz['id']}", json={"amount": "11246235", "author": "Helena"})

    response = http.post(
        f"/api/extractions/{run_id}/fields",
        json={"item_code": "xb", "year": "N", "amount": str(balanced_amounts["XB"]),
              "author": "Helena", "document_id": document_id, "source_page": 1},
    )
    assert response.status_code == 201, response.get_json()
    body = response.get_json()
    assert body["field"]["status"] == "KEYED" and body["field"]["is_keyed"]
    assert body["field"]["proposed_amount"] is None
    assert all(c["passed"] for c in body["checks"] if c["severity"] == "BLOCKING")

    # Adding it twice is refused.
    again = http.post(
        f"/api/extractions/{run_id}/fields",
        json={"item_code": "XB", "year": "N", "amount": "1", "author": "Helena"},
    )
    assert again.status_code == 409

    # Validate, then the analyse step drafts the AI commentary automatically.
    dataset_id = _submit_and_validate(http, case_id, run_id, supervisor="franky").get_json()["id"]
    analysed = http.post(f"/api/datasets/{dataset_id}/analysis").get_json()
    draft = analysed["ai_analysis"]
    assert draft["status"] == "DRAFT"
    assert draft["sections"]["overview"] == "Draft overview."
    assert len(writer.payloads) == 1
    assert "ACME" not in str(writer.payloads[0])

    # Calling analyse again (or opening the dashboard) does not bill again.
    http.post(f"/api/datasets/{dataset_id}/analysis")
    dashboard = http.get(f"/api/cases/{case_id}/analysis").get_json()
    assert dashboard["ai_analysis"]["id"] == draft["id"]
    assert len(writer.payloads) == 1

    # My cases: the draft's text is not shown before approval (BR-13).
    mine = http.get("/api/my-cases?analyst=helena").get_json()
    assert [c["id"] for c in mine] == [case_id]
    assert mine[0]["ai_analysis"]["status"] == "DRAFT"
    assert mine[0]["ai_analysis"]["sections"] is None
    assert mine[0]["ratios"] and mine[0]["ratios"][0]["interpretation"]["text"]

    # Approval needs a name.
    assert http.post(
        f"/api/ai-analyses/{draft['id']}/approval", json={"sections": draft["sections"]}
    ).status_code == 409

    edited = dict(draft["sections"], overview="Approved overview.")
    approved = http.post(
        f"/api/ai-analyses/{draft['id']}/approval",
        json={"author": "Helena", "sections": edited},
    ).get_json()
    assert approved["status"] == "APPROVED"
    assert approved["approved_by"] == "Helena"
    assert approved["was_edited"] is True
    assert approved["generated_sections"]["overview"] == "Draft overview."

    mine = http.get("/api/my-cases?analyst=Helena").get_json()
    assert mine[0]["ai_analysis"]["sections"]["overview"] == "Approved overview."

    # Another analyst sees nothing of Helena's.
    assert http.get("/api/my-cases?analyst=Paul").get_json() == []


def test_model_unavailable_never_blocks_the_analysis(app_and_writer):
    app, _ = app_and_writer
    container = app.config["container"]
    container.insight.writer = None
    container.insight.unavailable_reason = "AI analysis needs ANTHROPIC_API_KEY"
    container.extraction.structurer = FakeStructurer({"BK": 1})  # tiny, fails checks
    http = app.test_client()
    case_id, _, run_id = _extract(http)

    dataset_id = _submit_and_validate(
        http, case_id, run_id, supervisor="s", acknowledge_failed_checks=True
    ).get_json()["id"]
    response = http.post(f"/api/datasets/{dataset_id}/analysis")
    assert response.status_code == 200
    ai = response.get_json()["ai_analysis"]
    assert ai["status"] == "FAILED"
    assert "ANTHROPIC_API_KEY" in ai["failure_reason"]

    # Retry once configured.
    container.insight.writer = FakeWriter()
    retried = http.post(f"/api/cases/{case_id}/ai-analysis", json={"author": "Helena"})
    assert retried.status_code == 201
    assert retried.get_json()["status"] == "DRAFT"


def test_cases_without_an_analyst_are_listed_as_unassigned(app_and_writer):
    app, _ = app_and_writer
    http = app.test_client()
    http.post("/api/cases", json={"client": "OLD", "fiscal_year": 2023})
    unassigned = http.get("/api/my-cases?analyst=").get_json()
    assert [c["client"] for c in unassigned] == ["OLD"]
    assert unassigned[0]["analyst"] is None


def test_deleting_a_case_removes_its_ai_analysis(app_and_writer):
    app, _ = app_and_writer
    container = app.config["container"]
    container.extraction.structurer = FakeStructurer({"BK": 1})
    http = app.test_client()
    case_id, _, run_id = _extract(http)
    dataset_id = _submit_and_validate(
        http, case_id, run_id, supervisor="s", acknowledge_failed_checks=True
    ).get_json()["id"]
    http.post(f"/api/datasets/{dataset_id}/analysis")
    assert container.ai_analyses.list_for_case(case_id)

    assert http.delete(f"/api/cases/{case_id}", json={"role": "supervisor", "author": "s"}).status_code == 204
    assert container.ai_analyses.list_for_case(case_id) == []