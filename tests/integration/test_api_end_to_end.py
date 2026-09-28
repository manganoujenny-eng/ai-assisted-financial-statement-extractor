"""The whole chain, over HTTP, in one test.

Upload -> extract -> correct -> validate -> analyse. It is the demonstration
of dossier §5.1 ("ten minutes, from reporting package to dashboard"), written
as a test so it cannot quietly stop working between now and the defence.

No real PDF and no model call: a fake reader and a fake structurer are
injected in place of the real adapters. That substitution takes four lines
because everything goes through ports — which is the clearest practical proof
that the architecture of §11 pays for itself.
"""

from __future__ import annotations

import io

import pytest

from app import create_app
from app.config import Config
from app.domain.ports import RawDocument, StructuredItem, StructuringResult


class FakeReader:
    """Pretends to read any file. Returns nothing the structurer looks at."""

    def supports(self, path: str) -> bool:
        return True

    def read(self, path: str) -> RawDocument:
        return RawDocument(
            file_type="PDF", document_type="NATIVE_PDF", pages_text=["fake page"]
        )


class FakeStructurer:
    """Proposes the fixture, with one deliberate error on BZ.

    The error is what makes the test worth writing: it exercises the
    correction path, the check rerun and the refusal to validate, rather than
    only the happy path where everything already works.

    It lands on BZ rather than on, say, BK for a precise reason. A wrong BZ
    breaks the equilibrium, so CHK001 catches it immediately. A wrong BK
    would leave BZ and DZ agreeing with each other and slip past CHK001
    entirely — only the subtotal check (CHK002, still an exercise) would see
    it. Worth sitting with for a moment: which errors a system catches
    depends on which checks exist, and that is the whole subject of Part D.
    """

    engine = "FAKE"

    def __init__(self, amounts: dict) -> None:
        self.amounts = amounts

    def structure(self, document: RawDocument) -> StructuringResult:
        items = [
            StructuredItem(item_code=code, amount=str(value), year="N", source_page=1)
            for code, value in self.amounts.items()
        ]
        for item in items:
            if item.item_code == "BZ":
                item.amount = "11246000"  # 235 francs short of the truth
        return StructuringResult(items=items, engine=self.engine)


@pytest.fixture
def client(tmp_path, balanced_amounts):
    app = create_app(Config(storage="memory", upload_dir=tmp_path))
    container = app.config["container"]
    container.extraction.readers = [FakeReader()]
    container.extraction.structurer = FakeStructurer(balanced_amounts)
    return app.test_client()


def test_the_whole_chain(client):
    # --- FR-01, create a case -------------------------------------------
    response = client.post("/api/cases", json={"client": "ACME SARL", "fiscal_year": 2024})
    assert response.status_code == 201
    case_id = response.get_json()["id"]

    # --- FR-02, upload and fingerprint ----------------------------------
    response = client.post(
        f"/api/cases/{case_id}/documents",
        data={"file": (io.BytesIO(b"%PDF-1.7 not really a pdf"), "statement.pdf")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 201
    document = response.get_json()
    assert len(document["sha256"]) == 64  # the cache key of NFR-08
    document_id = document["id"]

    # --- UC-03, extract --------------------------------------------------
    response = client.post(f"/api/documents/{document_id}/extractions")
    assert response.status_code == 201
    run = response.get_json()
    assert run["status"] == "EXTRACTED"
    extraction_id = run["id"]

    # --- the checks ran before any human touched the data ---------------
    response = client.get(f"/api/extractions/{extraction_id}/fields")
    payload = response.get_json()
    equilibrium = next(c for c in payload["checks"] if c["code"] == "CHK001")
    assert not equilibrium["passed"], "BZ is 235 short, the balance sheet cannot balance"
    assert equilibrium["gap"] == "-235.00"

    # --- BR-12, validation is refused while a blocking check fails ------
    response = client.post(f"/api/extractions/{extraction_id}/validation", json={})
    assert response.status_code == 409
    assert response.get_json()["error"] == "validation_refused"
    # UC-06 / E1 — the refusal lists the discrepancies, it does not just say no.
    assert response.get_json()["failing_checks"]

    # --- UC-04, correct --------------------------------------------------
    field = next(f for f in payload["fields"] if f["item_code"] == "BZ")
    response = client.patch(
        f"/api/fields/{field['id']}", json={"amount": "11246235", "author": "helena"}
    )
    assert response.status_code == 200
    corrected = response.get_json()["field"]
    assert corrected["was_corrected"] is True
    # BR-10 — what the extractor proposed is still there, and measurable.
    assert corrected["proposed_amount"] == "11246000.00"
    # BR-11 — every check was rerun, not only the ones touching BK.
    assert all(c["passed"] for c in response.get_json()["checks"])

    # --- UC-06, validate -------------------------------------------------
    response = client.post(
        f"/api/extractions/{extraction_id}/validation", json={"supervisor": "franky"}
    )
    assert response.status_code == 201
    dataset_id = response.get_json()["id"]

    # --- the ratios ------------------------------------------------------
    response = client.post(f"/api/datasets/{dataset_id}/analysis")
    assert response.status_code == 200
    ratios = {r["code"]: r for r in response.get_json()["ratios"]}

    assert ratios["R1"]["status"] == "COMPUTED"
    assert ratios["R1"]["value"] == "1.7"
    # BR-04 — the value travels with what built it.
    assert set(ratios["R1"]["items_used"]) == {"BK", "BT", "DP", "DT"}
    # BR-14 — the sentence cites its reference.
    assert ratios["R1"]["interpretation"]["reference_source"]

    # R2..R5 are still exercises: they say so, with a reason, and the
    # dashboard keeps working. BR-02 — a reasoned absence, never a zero.
    assert ratios["R5"]["status"] == "NOT_COMPUTABLE"
    assert ratios["R5"]["value"] is None

    # --- FR-18, the dashboard -------------------------------------------
    response = client.get(f"/api/cases/{case_id}/analysis")
    assert response.status_code == 200
    assert response.get_json()["case"]["status"] == "ANALYSED"


def test_the_same_document_is_not_extracted_twice(client):
    """NFR-08 — the fingerprint is what stops the second bill arriving."""
    case_id = client.post(
        "/api/cases", json={"client": "ACME SARL", "fiscal_year": 2024}
    ).get_json()["id"]

    def upload():
        return client.post(
            f"/api/cases/{case_id}/documents",
            data={"file": (io.BytesIO(b"identical bytes"), "statement.pdf")},
            content_type="multipart/form-data",
        ).get_json()

    assert upload()["id"] == upload()["id"]


def test_an_unknown_case_answers_404(client):
    assert client.get("/api/cases/does-not-exist").status_code == 404
