"""Item 4 and the add-item feature — service level, no network, no database."""

from decimal import Decimal

import pytest

from app.domain import entities as E
from app.domain.ports import AnalysisDraft
from app.domain.value_objects import Amount
from app.infra.db.memory import (
    InMemoryAiAnalysisRepository,
    InMemoryAuditLog,
    InMemoryDatasetRepository,
    InMemoryExtractionRepository,
)
from app.services.insight_service import InsightService, build_payload, clean_sections
from app.services.validation_service import ValidationService


def _validation():
    extractions = InMemoryExtractionRepository()
    audit = InMemoryAuditLog()
    return ValidationService(extractions, InMemoryDatasetRepository(), audit), audit


def _run(case):
    return E.ExtractionRun(
        case_id=case.id,
        engine="RULE_BASED",
        document_ids=["doc-1"],
        fields=[E.ExtractedField(item_code="BK", amount=Amount("100"), year="N")],
    )


# --- add a missing item -----------------------------------------------------
def test_added_item_is_keyed_audited_and_rechecked():
    validation, audit = _validation()
    case = E.AnalysisCase(client="ACME", fiscal_year=2024, status=E.EXTRACTED)
    run = _run(case)

    field, checks = validation.add_field(
        case, run, "xb", "N", "5198800000", author="helena", document_id="doc-1", source_page=2
    )

    assert field.item_code == "XB"
    assert field.status == E.KEYED
    assert field.is_keyed and field.proposed_amount is None
    assert not field.was_corrected
    assert field in run.fields
    assert audit.list_for("ExtractedField", field.id)[0].action == "KEYED"
    completeness = next(c for c in checks if c.code == "CHK004")
    assert "XB" not in completeness.message


def test_adding_an_item_that_already_exists_is_refused():
    validation, _ = _validation()
    case = E.AnalysisCase(client="ACME", fiscal_year=2024, status=E.EXTRACTED)
    run = _run(case)
    with pytest.raises(E.DomainError, match="already in this extraction"):
        validation.add_field(case, run, "BK", "N", "1", author="helena")
    # Same code, other year: allowed.
    validation.add_field(case, run, "BK", "N-1", "90", author="helena")


@pytest.mark.parametrize(
    "code,year,document_id,author",
    [("B1", "N", None, "h"), ("BK", "N-2", None, "h"), ("XB", "N", "other-doc", "h"), ("XB", "N", None, " ")],
)
def test_bad_added_item_is_refused(code, year, document_id, author):
    validation, _ = _validation()
    case = E.AnalysisCase(client="ACME", fiscal_year=2024, status=E.EXTRACTED)
    with pytest.raises(ValueError):
        validation.add_field(case, _run(case), code, year, "1", author=author, document_id=document_id)


def test_items_cannot_be_added_to_a_validated_case():
    validation, _ = _validation()
    case = E.AnalysisCase(client="ACME", fiscal_year=2024, status=E.VALIDATED)
    with pytest.raises(E.DomainError, match="reopen it first"):
        validation.add_field(case, _run(case), "XB", "N", "1", author="helena")


def test_keyed_item_stays_keyed_through_correction_and_reopen():
    validation, _ = _validation()
    case = E.AnalysisCase(client="ACME", fiscal_year=2024, status=E.EXTRACTED)
    run = _run(case)
    field, _ = validation.add_field(case, run, "XB", "N", "10", author="helena")
    field.correct(Amount("11"), "helena")
    assert field.status == E.KEYED
    field.status = E.VALIDATED_FIELD
    case.status = E.ANALYSED
    validation.reopen(case, run, author="helena", reason="fix")
    assert field.status == E.KEYED


# --- AI commentary ----------------------------------------------------------
GOOD = {
    "overview": "Overview.",
    "ratios": [{"code": "R1", "commentary": "R1 stands at 1.2 x."}],
    "checks": "All checks passed.",
    "comparison": "No prior-period comparison is available.",
    "attention": ["Point one"],
}


class FakeWriter:
    def __init__(self, sections=GOOD, error=None):
        self.sections, self.error, self.calls, self.payloads = sections, error, 0, []

    def write(self, payload):
        self.calls += 1
        self.payloads.append(payload)
        if self.error:
            raise self.error
        return AnalysisDraft(sections=self.sections, model="m", prompt_version="v", cost_usd=Decimal("0.01"))


def _insight(writer):
    repo = InMemoryAiAnalysisRepository()
    audit = InMemoryAuditLog()
    return InsightService(writer, repo, audit, "not configured"), repo, audit


def _case_and_dataset():
    case = E.AnalysisCase(client="ACME SARL", fiscal_year=2024, status=E.ANALYSED)
    dataset = E.ValidatedDataset(extraction_id="run-1", validated_by="s", amounts={"BK": "100"})
    return case, dataset


PAYLOAD = {"ratios": [{"code": "R1"}]}


def test_payload_contains_figures_only():
    payload = build_payload(
        amounts={"BK": "100"},
        prior_year_amounts={"BK": "90"},
        ratios=[{"code": "R1", "name": "Current ratio", "status": "COMPUTED", "value": "1.2"}],
        checks=[{"code": "CHK001", "passed": True}],
        year_comparison=None,
    )
    text = str(payload)
    assert "ACME" not in text and "2024" not in text
    assert payload["items"][0] == {"code": "BK", "label": "TOTAL ACTIF CIRCULANT", "N": "100", "N-1": "90"}
    assert payload["comparison"] is None


def test_draft_is_generated_once_per_dataset_and_never_billed_twice():
    writer = FakeWriter()
    insight, repo, audit = _insight(writer)
    case, dataset = _case_and_dataset()

    first = insight.generate(case, dataset, PAYLOAD)
    second = insight.generate(case, dataset, PAYLOAD)

    assert first.status == E.AI_DRAFT
    assert second.id == first.id
    assert writer.calls == 1
    assert first.sections["ratios"] == {"R1": "R1 stands at 1.2 x."}
    assert audit.list_for("AiAnalysis", first.id)[0].action == "AI_ANALYSIS_DRAFTED"


def test_model_failure_is_recorded_not_raised():
    insight, _, _ = _insight(FakeWriter(error=RuntimeError("network down")))
    case, dataset = _case_and_dataset()
    analysis = insight.generate(case, dataset, PAYLOAD)
    assert analysis.status == E.AI_FAILED
    assert analysis.failure_reason == "network down"


def test_no_writer_configured_is_a_recorded_failure():
    insight, _, _ = _insight(None)
    case, dataset = _case_and_dataset()
    analysis = insight.generate(case, dataset, PAYLOAD)
    assert analysis.status == E.AI_FAILED and analysis.failure_reason == "not configured"


def test_commentary_on_an_unknown_ratio_is_refused():
    bad = dict(GOOD, ratios=[{"code": "R9", "commentary": "invented"}])
    insight, _, _ = _insight(FakeWriter(sections=bad))
    case, dataset = _case_and_dataset()
    assert insight.generate(case, dataset, PAYLOAD).status == E.AI_FAILED


def test_approval_keeps_the_model_text_and_records_the_edit():
    insight, repo, audit = _insight(FakeWriter())
    case, dataset = _case_and_dataset()
    draft = insight.generate(case, dataset, PAYLOAD)

    edited = dict(draft.sections, overview="Edited by the analyst.")
    insight.approve(draft, edited, author="helena")

    assert draft.status == E.AI_APPROVED
    assert draft.approved_by == "helena"
    assert draft.sections["overview"] == "Edited by the analyst."
    assert draft.generated_sections["overview"] == "Overview."
    assert draft.was_edited
    entry = audit.list_for("AiAnalysis", draft.id)[-1]
    assert entry.action == "AI_ANALYSIS_APPROVED" and entry.detail["edited_by_analyst"]

    # Approved text is never replaced, even when forced.
    assert insight.generate(case, dataset, PAYLOAD, force=True).id == draft.id
    with pytest.raises(E.DomainError):
        insight.approve(draft, edited, author="helena")


def test_approval_needs_a_name_and_a_draft():
    insight, _, _ = _insight(FakeWriter(error=RuntimeError("x")))
    case, dataset = _case_and_dataset()
    failed = insight.generate(case, dataset, PAYLOAD)
    with pytest.raises(E.DomainError):
        insight.approve(failed, GOOD, author="helena")

    insight2, _, _ = _insight(FakeWriter())
    draft = insight2.generate(case, dataset, PAYLOAD)
    with pytest.raises(E.DomainError):
        insight2.approve(draft, draft.sections, author="  ")


def test_clean_sections_rejects_wrong_shapes():
    with pytest.raises(ValueError):
        clean_sections("text")
    with pytest.raises(ValueError):
        clean_sections(dict(GOOD, attention="not a list"))
    with pytest.raises(ValueError):
        clean_sections(dict(GOOD, overview=["x"]))