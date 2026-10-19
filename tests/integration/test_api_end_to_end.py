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
from decimal import Decimal

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

    #--------------serve the original source document------------------------
    response = client.get(f"/api/documents/{document_id}/file")
    assert response.status_code == 200
    assert  response.content_type == "application/pdf"
    assert response.data == b"%PDF-1.7 not really a pdf"

    # --- UC-03, extract --------------------------------------------------
    response = client.post(f"/api/cases/{case_id}/extractions")
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

    # --- the analyst submits; nothing is validated before that ----------
    response = client.post(f"/api/extractions/{extraction_id}/validation", json={})
    assert response.status_code == 409
    assert "submitted" in response.get_json()["detail"]
    response = client.post(f"/api/cases/{case_id}/submission", json={"note": "ready"})
    assert response.status_code == 200
    assert response.get_json()["status"] == "SUBMITTED"
    # A submitted case is frozen for the analyst until the supervisor answers.
    bz = next(f for f in payload["fields"] if f["item_code"] == "BZ")
    assert client.patch(f"/api/fields/{bz['id']}", json={"amount": "1"}).status_code == 409

    # --- BR-12, validation is refused while a blocking check fails ------
    response = client.post(f"/api/extractions/{extraction_id}/validation", json={})
    assert response.status_code == 409
    assert response.get_json()["error"] == "validation_refused"
    # UC-06 / E1 — the refusal lists the discrepancies, it does not just say no.
    assert response.get_json()["failing_checks"]

    # --- the supervisor sends it back with what to fix --------------------
    response = client.post(f"/api/cases/{case_id}/correction-request", json={})
    assert response.status_code == 422  # a request without a message is refused
    response = client.post(
        f"/api/cases/{case_id}/correction-request",
        json={"message": "BZ does not match the assets total"},
    )
    assert response.status_code == 200
    assert response.get_json()["status"] == "UNDER_REVIEW"
    note = next(n for n in client.get("/api/notifications").get_json()
                if n["kind"] == "CORRECTION_REQUESTED")
    assert note["message"] == "BZ does not match the assets total"

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

    # --- submitted again, the supervisor is notified, then validates -----
    assert client.post(f"/api/cases/{case_id}/submission").status_code == 200
    kinds = [n["kind"] for n in client.get("/api/notifications").get_json()]
    assert kinds == ["SUBMITTED"]
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

    # R2..R5 are implemented and the dashboard computes them.
    assert ratios["R2"]["status"] == "COMPUTED"
    assert ratios["R3"]["status"] == "COMPUTED"
    assert ratios["R4"]["status"] == "COMPUTED"
    assert ratios["R5"]["status"] == "COMPUTED"

    # --- FR-18, the dashboard -------------------------------------------
    response = client.get(f"/api/cases/{case_id}/analysis")
    assert response.status_code == 200
    assert response.get_json()["case"]["status"] == "ANALYSED"

def test_a_successful_extraction_persists_page_count_and_is_scanned(client):
    """ExtractionService.run_extraction() learns page_count and is_scanned
    only once the reader opens the file, and used to set them on the
    in-memory SourceDocument with no repository.save() call anywhere to
    write them back. Every document, successful or not, reported both as
    null forever — which is what hid, for a while, that client4's failing
    document was a scan: the UI had no reliable signal to show "this is a
    scan" because the field never reached the database.
    """
    case_id = client.post(
        "/api/cases", json={"client": "ACME SARL", "fiscal_year": 2024}
    ).get_json()["id"]

    document_id = client.post(
        f"/api/cases/{case_id}/documents",
        data={"file": (io.BytesIO(b"%PDF-1.7 not really a pdf"), "statement.pdf")},
        content_type="multipart/form-data",
    ).get_json()["id"]

    client.post(f"/api/cases/{case_id}/extractions")

    case = client.get(f"/api/cases/{case_id}").get_json()
    document = next(d for d in case["documents"] if d["id"] == document_id)
    assert document["page_count"] is not None
    assert document["is_scanned"] is not None

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

def test_the_same_bytes_from_a_different_case_get_their_own_document(client):
    """The fingerprint proves two uploads are the same bytes — it never
    proved they are the same client's document. Before this, register_document
    looked the sha256 up globally: a second, unrelated case uploading a
    byte-identical file (an empty template is the realistic example, not a
    contrived one) silently got back the FIRST case's document — same
    case_id as before, and nothing of its own ever attached to the second
    case's own document list. Discovered by re-uploading client2's exact
    file into a brand-new case during testing and getting client2's
    document back.
    """
    case_one = client.post(
        "/api/cases", json={"client": "client A", "fiscal_year": 2024}
    ).get_json()["id"]
    case_two = client.post(
        "/api/cases", json={"client": "client B", "fiscal_year": 2024}
    ).get_json()["id"]

    def upload(case_id):
        return client.post(
            f"/api/cases/{case_id}/documents",
            data={"file": (io.BytesIO(b"identical bytes"), "template.xlsx")},
            content_type="multipart/form-data",
        ).get_json()

    document_one = upload(case_one)
    document_two = upload(case_two)

    # Two different documents, each correctly attributed to the case that
    # actually uploaded it — not one document shared, case_id frozen on
    # whichever case got there first.
    assert document_one["id"] != document_two["id"]
    assert document_one["case_id"] == case_one
    assert document_two["case_id"] == case_two

    # And each case actually has its own document in its own list — not
    # an empty list silently left behind because attach() was never called
    # on the early-return path.
    cases = client.get("/api/cases").get_json()
    case_one_payload = next(c for c in cases if c["id"] == case_one)
    case_two_payload = next(c for c in cases if c["id"] == case_two)
    assert [d["id"] for d in case_one_payload["documents"]] == [document_one["id"]]
    assert [d["id"] for d in case_two_payload["documents"]] == [document_two["id"]]

    # NFR-08 still holds for the case that matters: re-uploading the same
    # bytes to the SAME case still returns the existing document.
    assert upload(case_one)["id"] == document_one["id"]

def test_an_unknown_case_answers_404(client):
    assert client.get("/api/cases/does-not-exist").status_code == 404

class FailingStructurer:
    """Always proposes zero items — the SOCATRANS_2023.xlsx situation before
    find_side_start_columns() was fixed to stop assuming the header is on
    row 0: a document the rules genuinely cannot read.
    """

    engine = "RULE_BASED"

    def structure(self, document: RawDocument) -> StructuringResult:
        return StructuringResult(items=[], engine=self.engine)


def test_a_failed_extraction_can_be_retried_on_the_same_document(
    tmp_path, balanced_amounts
):
    """client4/client5's exact situation: an extraction fails once because
    the parser could not read that document's layout. Once the parser is
    fixed, retrying must work on the SAME document_id — no re-upload — and
    move the case all the way to EXTRACTED. This also locks in that /api/cases
    exposes failure_reason on a failed run, which the frontend needs to show
    the analyst *why* it failed rather than leaving them stuck on a case with
    no visible next step (the gap that made client4/client5 look stuck even
    after the parser fix landed — CasesPage.jsx only ever offered "Open
    Review" once any run existed, including a failed one, with no action
    that re-triggers extraction on the existing document).
    """
    app = create_app(Config(storage="memory", upload_dir=tmp_path))
    container = app.config["container"]
    container.extraction.readers = [FakeReader()]
    container.extraction.structurer = FailingStructurer()
    http = app.test_client()

    case_id = http.post(
        "/api/cases", json={"client": "SOCATRANS", "fiscal_year": 2023}
    ).get_json()["id"]

    document_id = http.post(
        f"/api/cases/{case_id}/documents",
        data={"file": (io.BytesIO(b"%PDF-1.7 socatrans"), "statement.pdf")},
        content_type="multipart/form-data",
    ).get_json()["id"]

    response = http.post(f"/api/cases/{case_id}/extractions")
    assert response.status_code == 422
    assert response.get_json()["error"] == "extraction_failed"

    cases = http.get("/api/cases").get_json()
    case_payload = next(c for c in cases if c["id"] == case_id)
    assert case_payload["status"] == "EXTRACTION_FAILED"

    failed_run = case_payload["extractions"][-1]
    assert failed_run["status"] == "EXTRACTION_FAILED"
    assert failed_run["failure_reason"] == "no usable item found in any document"

    # The parser gets fixed; retry on the SAME document_id, no re-upload.
    container.extraction.structurer = CleanStructurer(balanced_amounts)
    retry_response = http.post(f"/api/cases/{case_id}/extractions")
    assert retry_response.status_code == 201
    retried_run = retry_response.get_json()
    assert retried_run["status"] == "EXTRACTED"
    assert retried_run["id"] != failed_run["id"]

    cases_after_retry = http.get("/api/cases").get_json()
    case_after_retry = next(c for c in cases_after_retry if c["id"] == case_id)
    assert case_after_retry["status"] == "EXTRACTED"


class FakeTwoYearStructurer:
    """Proposes clean Year N and Year N-1 figures from one document.

    Used only by the FR-20 (year-over-year comparison) test below: unlike
    FakeStructurer, nothing here is deliberately wrong, because this test is
    about the comparison math, not the correction workflow.
    """

    engine = "FAKE"

    def __init__(self, current: dict, prior: dict) -> None:
        self.current = current
        self.prior = prior

    def structure(self, document: RawDocument) -> StructuringResult:
        items = [
            StructuredItem(item_code=code, amount=str(value), year="N", source_page=1)
            for code, value in self.current.items()
        ]
        items += [
            StructuredItem(item_code=code, amount=str(value), year="N-1", source_page=1)
            for code, value in self.prior.items()
        ]
        return StructuringResult(items=items, engine=self.engine)


PRIOR_YEAR_AMOUNTS = {
    "AZ": 3_500_000,
    "BK": 5_000_000,
    "BT": 300_000,
    "BZ": 8_800_000,
    "CP": 4_500_000,
    "DD": 1_800_000,
    "DP": 4_000_000,
    "DT": 500_000,
    "DZ": 8_800_000,
    "XB": 16_000_000,
    "XI": 800_000,
}


def test_year_over_year_comparison_uses_the_same_packages_prior_year_columns(
    tmp_path, balanced_amounts
):
    """FR-20 — the dashboard must compare N and N-1 when the uploaded package
    itself carries both years, not only when a separate prior-year case exists.

    This is the gap the project was left with at the end of the ReviewPage/
    DashboardPage work: ValidatedDataset.prior_year_amounts, the repository's
    {"N": ..., "N-1": ...} storage, and the dashboard route's preference for
    same-package N-1 data over a separately validated prior-year case were all
    implemented, but nothing exercised them end-to-end. This test closes that
    gap using the same fake-adapter technique as test_the_whole_chain.
    """
    app = create_app(Config(storage="memory", upload_dir=tmp_path))
    container = app.config["container"]
    container.extraction.readers = [FakeReader()]
    container.extraction.structurer = FakeTwoYearStructurer(
        current=balanced_amounts, prior=PRIOR_YEAR_AMOUNTS
    )
    http = app.test_client()

    case_id = http.post(
        "/api/cases", json={"client": "ACME SARL", "fiscal_year": 2024}
    ).get_json()["id"]

    document_id = http.post(
        f"/api/cases/{case_id}/documents",
        data={"file": (io.BytesIO(b"%PDF-1.7 two years"), "statement.pdf")},
        content_type="multipart/form-data",
    ).get_json()["id"]

    run_id = http.post(f"/api/cases/{case_id}/extractions").get_json()["id"]

    # Both years must have travelled through extraction untouched.
    fields = http.get(f"/api/extractions/{run_id}/fields").get_json()["fields"]
    assert {f["year"] for f in fields} == {"N", "N-1"}

    # Nothing was wrong, so validation should not need a correction first.
    http.post(f"/api/cases/{case_id}/submission")
    dataset_id = http.post(
        f"/api/extractions/{run_id}/validation", json={"supervisor": "franky"}
    ).get_json()["id"]

    response = http.get(f"/api/cases/{case_id}/analysis")
    assert response.status_code == 200
    payload = response.get_json()

    comparison = payload["year_comparison"]
    assert comparison is not None, "N-1 data was supplied in the same package"
    assert comparison["current_year"] == 2024
    assert comparison["previous_year"] == 2023

    by_code = {row["code"]: row for row in comparison["ratios"]}

    r1 = by_code["R1"]
    assert r1["current_status"] == "COMPUTED"
    assert r1["previous_status"] == "COMPUTED"
    assert Decimal(r1["current_value"]) == Decimal("1.7")
    assert Decimal(r1["previous_value"]) == Decimal("1.2")
    assert Decimal(r1["change"]) == Decimal("0.5")
    # 41.67%, give or take — the exact repeating decimal isn't the point.
    assert Decimal("41.6") < Decimal(r1["percent_change"]) < Decimal("41.7")

    # The stored dataset itself must still only expose Year N as "the" dataset
    # (BR-01's frozen snapshot); N-1 is comparison material, not a second
    # validated dataset of its own.
    assert payload["dataset"]["id"] == dataset_id

class CleanStructurer:
    """Proposes a balanced statement with no deliberate error.

    Unlike FakeStructurer, nothing here is wrong on purpose, because the test
    below is about which *run* the dashboard/reopen/export routes pick, not
    about the correction workflow — each validation must succeed on the
    first try so the test can control exactly when a second run appears.
    """

    engine = "FAKE"

    def __init__(self, amounts: dict) -> None:
        self.amounts = amounts

    def structure(self, document: RawDocument) -> StructuringResult:
        items = [
            StructuredItem(item_code=code, amount=str(value), year="N", source_page=1)
            for code, value in self.amounts.items()
        ]
        return StructuringResult(items=items, engine=self.engine)


def test_dashboard_reopen_and_export_use_the_most_recently_validated_run(
    tmp_path, balanced_amounts
):
    """Regression test for the lookup bug found while testing the reopen
    feature by hand: a document can carry more than one ExtractionRun (a
    reopened case is allowed back into EXTRACTING, and run_extraction()
    always adds a new run rather than replacing the old one), and each run
    can have its own validated dataset. case_dashboard(), reopen_case() and
    export_case() all used to scan for "the first run with any dataset" —
    correct only as long as a document never had more than one validated
    run. Once it does, that scan can return a stale run depending on
    repository iteration order, which is exactly what happened: the
    dashboard kept showing the superseded result, and reopen() unlocked the
    wrong run's fields.

    The fix (_latest_validated_dataset in routes.py, plus the matching
    ordering in InMemoryDatasetRepository/SqlDatasetRepository.find_by_extraction)
    always picks the run whose dataset has the latest validated_at. This test
    builds exactly two validated runs on the same document and checks that
    all three routes follow the second one, not the first.
    """
    app = create_app(Config(storage="memory", upload_dir=tmp_path))
    container = app.config["container"]
    container.extraction.readers = [FakeReader()]
    container.extraction.structurer = CleanStructurer(balanced_amounts)
    http = app.test_client()

    case_id = http.post(
        "/api/cases", json={"client": "ACME SARL", "fiscal_year": 2024}
    ).get_json()["id"]

    document_id = http.post(
        f"/api/cases/{case_id}/documents",
        data={"file": (io.BytesIO(b"%PDF-1.7 run one"), "statement.pdf")},
        content_type="multipart/form-data",
    ).get_json()["id"]

    # --- first run: extract, validate -- no correction needed, the
    # balanced fixture clears every check on the first try. ----------------
    run1_id = http.post(f"/api/cases/{case_id}/extractions").get_json()["id"]
    http.post(f"/api/cases/{case_id}/submission")
    dataset1_id = http.post(
        f"/api/extractions/{run1_id}/validation", json={"supervisor": "franky"}
    ).get_json()["id"]

    response = http.get(f"/api/cases/{case_id}/analysis").get_json()
    assert response["dataset"]["id"] == dataset1_id
    assert response["dataset"]["validated_by"] == "franky"

    # --- reopen, then re-extract: a second, independent run now exists on
    # the same document. ----------------------------------------------------
    assert http.post(f"/api/cases/{case_id}/reopen", json={}).status_code == 200

    run2_id = http.post(f"/api/cases/{case_id}/extractions").get_json()["id"]
    assert run2_id != run1_id

    http.post(f"/api/cases/{case_id}/submission")
    dataset2_id = http.post(
        f"/api/extractions/{run2_id}/validation", json={"supervisor": "priscille"}
    ).get_json()["id"]
    assert dataset2_id != dataset1_id

    # --- the dashboard must follow the second (most recent) run, not the
    # first one that merely happens to have been validated earlier. --------
    response = http.get(f"/api/cases/{case_id}/analysis").get_json()
    assert response["dataset"]["id"] == dataset2_id
    assert response["dataset"]["validated_by"] == "priscille"

    # --- export must follow the second dataset too, while the case is still
    # VALIDATED (analysis is only available while VALIDATED/ANALYSED — BR-01
    # — so this has to run before the reopen below moves it on). -----------
    export_response = http.get(f"/api/cases/{case_id}/export")
    assert export_response.status_code == 200
    assert export_response.mimetype == (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    # --- reopening again must unlock run2's fields, not run1's. A field
    # that validate() marked VALIDATED_FIELD refuses .correct() until its
    # own run is reopened (ExtractedField.correct's DomainError). If
    # reopen_case() picked run1 here, this PATCH would come back 409. ------
    assert http.post(f"/api/cases/{case_id}/reopen", json={}).status_code == 200

    run2_field_id = http.get(f"/api/extractions/{run2_id}/fields").get_json()[
        "fields"
    ][0]["id"]
    response = http.patch(
        f"/api/fields/{run2_field_id}",
        json={"amount": "1", "author": "helena"},
    )
    assert response.status_code == 200, response.get_json()