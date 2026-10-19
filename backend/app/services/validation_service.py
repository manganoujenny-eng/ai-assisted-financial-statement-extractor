"""ValidationService — correction (UC-04) and validation (UC-06).

The dossier separates the power to correct from the power to validate
(§6.2): "this is an internal control requirement, not a technical
convenience". The two methods below are that separation, made executable.
Access control proper is out of scope (§3.3), so the caller passes an author
— but the *shape* of the rule is already in place, and wiring real roles later
touches this file only.
"""

from __future__ import annotations

from datetime import datetime, timezone

from ..domain import entities as E
from ..domain.checks import CheckOutcome, run_all
from ..domain.ports import AuditLog, DatasetRepository, ExtractionRepository
from ..domain.value_objects import Amount


class ValidationRefused(Exception):
    """BR-12 / FR-13 — a blocking check is failing and nobody has said, on
    the record, that they are validating anyway.

    This is no longer a hard stop. It is the question "are you sure?": the
    caller can retry with ``acknowledge_failed_checks=True`` and the dataset
    is then validated, with the failing checks written into the audit entry.
    """

    def __init__(self, message: str, failures: list[CheckOutcome]) -> None:
        super().__init__(message)
        self.failures = failures


class ValidationService:
    def __init__(
        self,
        extractions: ExtractionRepository,
        datasets: DatasetRepository,
        audit: AuditLog,
    ) -> None:
        self.extractions = extractions
        self.datasets = datasets
        self.audit = audit

    # --- UC-04 ----------------------------------------------------------
    def correct_field(
        self,
        run: E.ExtractionRun,
        field_id: str,
        new_amount: str,
        author: str,
        case: E.AnalysisCase | None = None,
    ) -> list[CheckOutcome]:
        """Correct one field and rerun every check (BR-11, FR-12).

        Rerunning *all* the checks, not the ones that touch this field, is
        intentional. Correcting BK changes the asset subtotal, which changes
        the equilibrium, which can un-fail a check that had nothing to do
        with the field the analyst touched. Partial re-evaluation is how a
        system starts showing a green check that is no longer true.
        """
        if case is not None:
            _require_editable(case)
        field = next((f for f in run.fields if f.id == field_id), None)
        if field is None:
            raise KeyError(f"field {field_id} not found in run {run.id}")

        before = field.amount
        field.correct(Amount(new_amount), author)  # BR-10 lives in the entity
        self.extractions.save(run)

        self.audit.record(
            E.AuditEntry(
                entity="ExtractedField",
                entity_id=field.id,
                action="CORRECTED",
                author=author,
                detail={
                    "item_code": field.item_code,
                    "before": str(before.value),
                    "after": str(field.amount.value),
                    "proposed": str(field.proposed_amount.value)
                    if field.proposed_amount
                    else None,
                },
            )
        )
        return run_all(run.statement())

    # --- adding an item the extractor missed --------------------------
    def add_field(
        self,
        case: E.AnalysisCase,
        run: E.ExtractionRun,
        item_code: str,
        year: str,
        amount: str,
        author: str,
        document_id: str | None = None,
        source_page: int | None = None,
    ) -> tuple[E.ExtractedField, list[CheckOutcome]]:
        """Key in an item the extractor did not find (status KEYED).

        The analyst has read the item in the source document; the
        extractor missed it (a scan whose table OCR could not rebuild, a
        label it did not recognise). The field is recorded as KEYED with no
        ``proposed_amount`` — it never came from the extractor, so it must
        not count as an extraction success or an extraction error in Part D.
        Every check is rerun afterwards, exactly as after a correction.
        """
        if case.status not in {E.EXTRACTED, E.UNDER_REVIEW}:
            raise E.DomainError(
                f"items can only be added while the case is EXTRACTED or "
                f"UNDER_REVIEW (it is {case.status}) — reopen it first"
            )

        code = str(item_code or "").strip().upper()
        if len(code) != 2 or not code.isalpha():
            raise ValueError(f"not a SYSCOHADA item code: {item_code!r}")

        if year not in ("N", "N-1"):
            raise ValueError(f"year must be 'N' or 'N-1', not {year!r}")

        if any(f.item_code == code and f.year == year for f in run.fields):
            raise E.DomainError(
                f"item {code} ({year}) is already in this extraction — "
                "correct its amount instead of adding it again"
            )

        if document_id is not None and document_id not in run.document_ids:
            raise ValueError("that document is not part of this extraction run")

        if not author or not str(author).strip():
            raise ValueError("an added item needs the analyst's name")

        field = E.ExtractedField(
            item_code=code,
            amount=Amount(amount),
            extraction_id=run.id,
            document_id=document_id,
            proposed_amount=None,
            year=year,
            source_page=source_page,
            status=E.KEYED,
            corrected_by=str(author).strip(),
            corrected_at=datetime.now(timezone.utc),
        )
        run.fields.append(field)
        self.extractions.save(run)

        self.audit.record(
            E.AuditEntry(
                entity="ExtractedField",
                entity_id=field.id,
                action="KEYED",
                author=field.corrected_by,
                detail={
                    "extraction_id": run.id,
                    "item_code": code,
                    "year": year,
                    "amount": str(field.amount.value),
                    "document_id": document_id,
                    "source_page": source_page,
                },
            )
        )
        return field, run_all(run.statement())

    # --- UC-06 ----------------------------------------------------------
    def validate(
        self,
        case: E.AnalysisCase,
        run: E.ExtractionRun,
        supervisor: str,
        acknowledge_failed_checks: bool = False,
    ) -> E.ValidatedDataset:
        """Freeze the data. After this, ratios become possible (BR-01).

        The blocking checks are rerun here rather than trusted from the last
        display. Between the analyst's screen and the supervisor's click, a
        correction may have landed. Trusting a cached verdict is how a
        dataset gets validated on checks that passed ten minutes ago.

        A failing blocking check no longer forbids validation outright — it
        requires an explicit acknowledgement. Without it, ValidationRefused
        is raised exactly as before (so the screen can show the warning).
        With it, the dataset is validated and the checks that were failing
        at that moment are written into the VALIDATED audit entry: the
        override is a decision someone made, by name, not a silent pass.
        """
        if case.status != E.SUBMITTED:
            raise E.DomainError(
                f"only a case submitted for validation can be validated "
                f"(this one is {case.status}) — the analyst submits it first"
            )
        outcomes = run_all(run.statement())
        failures = [o for o in outcomes if o.is_blocking_failure]
        if failures and not acknowledge_failed_checks:
            raise ValidationRefused(
                "validation needs confirmation: "
                + "; ".join(f"{o.code} {o.message}" for o in failures),
                failures,
            )

        current_year_amounts = {
            f.item_code: str(f.amount.value)
            for f in run.fields
            if f.year == "N"
        }

        prior_year_amounts = {
            f.item_code: str(f.amount.value)
            for f in run.fields
            if f.year == "N-1"
        }

        dataset = E.ValidatedDataset(
            extraction_id=run.id,
            validated_by=supervisor,
            amounts=current_year_amounts,
            prior_year_amounts=prior_year_amounts,
        )

        for field in run.fields:
            field.status = E.VALIDATED_FIELD

        self.datasets.add(dataset)
        self.extractions.save(run)
        case.transition_to(E.VALIDATED)

        self.audit.record(
            E.AuditEntry(
                entity="ValidatedDataset",
                entity_id=dataset.id,
                action="VALIDATED",
                author=supervisor,
                detail={
                    "extraction_id": run.id,
                    "items": len(dataset.amounts),
                    # Empty when every blocking check passed. Otherwise the
                    # checks this supervisor chose to validate over.
                    "failed_checks_acknowledged": [
                        {"code": o.code, "message": o.message} for o in failures
                    ],
                },
            )
        )
        return dataset

    # --- §15, reopening -------------------------------------------------


    def reopen(self, case, run, author, reason):
        """Reopen an analysed case for correction and review.

        Reopening moves the case from ANALYSED to UNDER_REVIEW. In the current
        architecture, this is how the previous analysis is invalidated: analysis
        is no longer allowed while the case is under review.

        The ValidatedDataset is kept as a historical snapshot and is not deleted
        or modified. After corrections are reviewed and the case is validated
        again, the analysis can be recomputed from the validated data.

        Moving the case alone is not enough: ExtractedField.correct() refuses
        to touch any field still carrying VALIDATED_FIELD status, which is
        exactly what validate() set on every field last time. Without resetting
        that here, the case looks reopened but every field stays frozen. A
        field that had already been individually corrected goes back to
        CORRECTED rather than PROPOSED, so the correction history (BR-10) is
        not misrepresented as "never touched".

        The reopening is recorded in the append-only audit log so that the
        correction workflow remains traceable.
        """
        case.transition_to(E.UNDER_REVIEW)
        _unfreeze_fields(run)
        self.extractions.save(run)

        self.audit.record(
            E.AuditEntry(
                entity="AnalysisCase",
                entity_id=case.id,
                action="REOPENED",
                author=author,
                detail={"reason": reason},
            )
        )

    # --- the hand-over between analyst and supervisor ------------------
    def submit(
        self,
        case: E.AnalysisCase,
        run: E.ExtractionRun,
        author: str,
        note: str = "",
    ) -> None:
        """The analyst hands the case to the supervisor for validation.

        Allowed from EXTRACTED (nothing needed correcting) and UNDER_REVIEW
        (after a correction request). The run submitted must be the case's
        newest one and must have finished: the supervisor validates exactly
        what the analyst looked at. The SUBMITTED audit entry is what puts
        the case in the supervisor's notifications.
        """
        if case.status not in {E.EXTRACTED, E.UNDER_REVIEW}:
            raise E.DomainError(
                f"only an extracted case or one under review can be submitted "
                f"(this one is {case.status})"
            )
        if run.case_id != case.id:
            raise ValueError(f"extraction {run.id} does not belong to case {case.id}")
        if run.status != E.EXTRACTED:
            raise E.DomainError("this extraction did not finish — re-extract before submitting")
        if not run.fields:
            raise E.DomainError("there is nothing to validate in this extraction")

        case.transition_to(E.SUBMITTED)
        self.audit.record(
            E.AuditEntry(
                entity="AnalysisCase",
                entity_id=case.id,
                action="SUBMITTED",
                author=author,
                detail={"extraction_id": run.id, "note": (note or "").strip()},
            )
        )

    def request_correction(
        self,
        case: E.AnalysisCase,
        run: E.ExtractionRun,
        supervisor: str,
        message: str,
    ) -> None:
        """The supervisor sends the case back to its analyst.

        From SUBMITTED (not validated yet) or from VALIDATED / ANALYSED (a
        problem found afterwards; the validated snapshot is kept, exactly as
        with reopen). The case goes to UNDER_REVIEW so the analyst can
        correct it, then submits it again. The message is mandatory: the
        analyst must know what to fix, and the thesis must be able to show
        why a validation was refused.
        """
        message = (message or "").strip()
        if not message:
            raise ValueError("say what has to be corrected")
        if case.status not in {E.SUBMITTED, E.VALIDATED, E.ANALYSED}:
            raise E.DomainError(
                f"a correction can be requested on a submitted or validated case "
                f"(this one is {case.status})"
            )

        was = case.status
        case.transition_to(E.UNDER_REVIEW)
        if was != E.SUBMITTED:
            _unfreeze_fields(run)
            self.extractions.save(run)

        self.audit.record(
            E.AuditEntry(
                entity="AnalysisCase",
                entity_id=case.id,
                action="CORRECTION_REQUESTED",
                author=supervisor,
                detail={
                    "message": message,
                    "analyst": case.analyst,
                    "extraction_id": run.id,
                    "from_status": was,
                },
            )
        )


#: Workflow actions recorded on the case, newest last. The notifications and
#: the review screen's history read these from the audit log.
WORKFLOW_ACTIONS = ("SUBMITTED", "CORRECTION_REQUESTED", "REOPENED")


def _require_editable(case: E.AnalysisCase) -> None:
    if case.status not in {E.EXTRACTED, E.UNDER_REVIEW}:
        raise E.DomainError(
            f"items can only be corrected while the case is EXTRACTED or "
            f"UNDER_REVIEW (it is {case.status})"
        )


def _unfreeze_fields(run: E.ExtractionRun) -> None:
    """Undo what validate() did to the fields, so they can be corrected.

    ExtractedField.correct() refuses a VALIDATED_FIELD. A keyed item goes
    back to KEYED, a corrected one to CORRECTED, an untouched one to
    PROPOSED — so the correction history (BR-10) is not rewritten.
    """
    for field in run.fields:
        if field.status == E.VALIDATED_FIELD:
            if field.is_keyed:
                field.status = E.KEYED
            else:
                field.status = E.CORRECTED if field.corrected_by else E.PROPOSED