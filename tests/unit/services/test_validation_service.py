import pytest

from app.domain import entities as E
from app.domain.value_objects import Amount
from app.infra.db.memory import InMemoryAuditLog, InMemoryDatasetRepository, InMemoryExtractionRepository
from app.services.analysis_service import AnalysisService
from app.services.validation_service import ValidationRefused, ValidationService


def _services():
    extractions = InMemoryExtractionRepository()
    datasets = InMemoryDatasetRepository()
    audit = InMemoryAuditLog()
    return extractions, datasets, audit, ValidationService(extractions, datasets, audit)


def _failing_run(case_id: str) -> E.ExtractionRun:
    # BK only: Completeness (a BLOCKING check) fails on everything missing.
    return E.ExtractionRun(
        case_id=case_id,
        engine="RULE_BASED",
        fields=[E.ExtractedField(item_code="BK", amount=Amount("100"), year="N")],
    )


def test_reopening_an_analysed_case_invalidates_current_analysis():
    extractions, datasets, audit, validation = _services()
    analysis = AnalysisService(audit)

    case = E.AnalysisCase(
        client="ACME SARL",
        fiscal_year=2024,
        status=E.ANALYSED,
    )

    run = E.ExtractionRun(case_id=case.id, engine="RULE_BASED")

    validation.reopen(
        case,
        run,
        author="helena",
        reason="Correction required",
    )

    assert case.status == E.UNDER_REVIEW

    entries = audit.list_for("AnalysisCase", case.id)

    assert len(entries) == 1
    assert entries[0].action == "REOPENED"
    assert entries[0].author == "helena"
    assert entries[0].detail["reason"] == "Correction required"

    with pytest.raises(E.DomainError, match="analysis is not available"):
        analysis.analyse(
            case,
            E.ValidatedDataset(
                extraction_id="run-1",
                validated_by="supervisor",
                amounts={},
            ),
        )


def test_reopening_resets_validated_fields_so_they_can_be_corrected_again():
    """Guards the bug found while testing the reopen feature by hand: reopen()
    moved the case back to UNDER_REVIEW, but every field was left at
    VALIDATED_FIELD status from the earlier validate() call, and
    ExtractedField.correct() refuses to touch a field in that status. The
    case looked reopened in the UI while every field stayed frozen.

    The fix: reopen() also resets the fields on the run it is given. A field
    that had already been corrected once goes back to CORRECTED rather than
    PROPOSED, so BR-10's correction history is not misrepresented as "never
    touched".
    """
    extractions, datasets, audit, validation = _services()

    case = E.AnalysisCase(
        client="ACME SARL", fiscal_year=2024, status=E.ANALYSED
    )

    previously_corrected = E.ExtractedField(
        item_code="BK",
        amount=Amount("100"),
        proposed_amount=Amount("90"),
        status=E.VALIDATED_FIELD,
        corrected_by="helena",
    )
    never_corrected = E.ExtractedField(
        item_code="BT",
        amount=Amount("50"),
        proposed_amount=Amount("50"),
        status=E.VALIDATED_FIELD,
    )
    run = E.ExtractionRun(
        case_id=case.id,
        engine="RULE_BASED",
        fields=[previously_corrected, never_corrected],
    )

    validation.reopen(case, run, author="helena", reason="correction")

    assert previously_corrected.status == E.CORRECTED
    assert never_corrected.status == E.PROPOSED

    # The actual regression: correcting either field again must now be
    # allowed, not raise "field already validated".
    previously_corrected.correct(Amount("101"), "helena")
    never_corrected.correct(Amount("51"), "helena")


def test_failing_blocking_check_asks_for_confirmation_without_the_flag():
    extractions, datasets, audit, validation = _services()
    case = E.AnalysisCase(client="ACME SARL", fiscal_year=2024, status=E.SUBMITTED)
    run = _failing_run(case.id)

    with pytest.raises(ValidationRefused) as refused:
        validation.validate(case, run, supervisor="franky")

    assert any(o.code == "CHK004" for o in refused.value.failures)
    assert case.status == E.SUBMITTED
    assert datasets.list() == []


def test_acknowledged_failing_checks_validate_and_are_recorded_in_the_audit():
    extractions, datasets, audit, validation = _services()
    case = E.AnalysisCase(client="ACME SARL", fiscal_year=2024, status=E.SUBMITTED)
    run = _failing_run(case.id)

    dataset = validation.validate(
        case, run, supervisor="franky", acknowledge_failed_checks=True
    )

    assert case.status == E.VALIDATED
    assert "BK" in dataset.amounts
    entry = audit.list_for("ValidatedDataset", dataset.id)[0]
    assert entry.action == "VALIDATED"
    codes = [c["code"] for c in entry.detail["failed_checks_acknowledged"]]
    assert "CHK004" in codes

# --- item 5 workflow: submit, correction request ---------------------------
def _extracted_run(case_id: str) -> E.ExtractionRun:
    run = _failing_run(case_id)
    run.status = E.EXTRACTED
    return run


def test_validating_a_case_that_was_not_submitted_writes_nothing():
    extractions, datasets, audit, validation = _services()
    case = E.AnalysisCase(client="ACME SARL", fiscal_year=2024, status=E.EXTRACTED)
    run = _extracted_run(case.id)

    with pytest.raises(E.DomainError, match="submitted"):
        validation.validate(case, run, supervisor="franky", acknowledge_failed_checks=True)
    assert datasets.list() == []
    assert run.fields[0].status == E.PROPOSED


def test_submit_then_correction_request_then_submit_again():
    extractions, datasets, audit, validation = _services()
    case = E.AnalysisCase(client="ACME SARL", fiscal_year=2024, status=E.EXTRACTED,
                          analyst="Helena")
    run = _extracted_run(case.id)
    extractions.add(run)

    validation.submit(case, run, author="Helena", note="done")
    assert case.status == E.SUBMITTED
    # Frozen while the supervisor has it.
    with pytest.raises(E.DomainError):
        validation.correct_field(run, run.fields[0].id, "1", "Helena", case=case)

    with pytest.raises(ValueError):
        validation.request_correction(case, run, supervisor="Paul", message="  ")
    validation.request_correction(case, run, supervisor="Paul", message="BK is wrong")
    assert case.status == E.UNDER_REVIEW
    validation.correct_field(run, run.fields[0].id, "120", "Helena", case=case)
    validation.submit(case, run, author="Helena")

    actions = [(e.action, e.author) for e in audit.list_for("AnalysisCase", case.id)]
    assert actions == [
        ("SUBMITTED", "Helena"),
        ("CORRECTION_REQUESTED", "Paul"),
        ("SUBMITTED", "Helena"),
    ]
    request = audit.list_for("AnalysisCase", case.id)[1]
    assert request.detail["message"] == "BK is wrong"
    assert request.detail["analyst"] == "Helena"


def test_a_failed_or_empty_run_cannot_be_submitted():
    _, _, _, validation = _services()
    case = E.AnalysisCase(client="ACME SARL", fiscal_year=2024, status=E.EXTRACTED)
    failed = _extracted_run(case.id)
    failed.status = E.EXTRACTION_FAILED
    with pytest.raises(E.DomainError, match="did not finish"):
        validation.submit(case, failed, author="Helena")
    empty = E.ExtractionRun(case_id=case.id, engine="RULE_BASED", status=E.EXTRACTED)
    with pytest.raises(E.DomainError, match="nothing to validate"):
        validation.submit(case, empty, author="Helena")