"""ValidationService — correction (UC-04) and validation (UC-06).

The dossier separates the power to correct from the power to validate
(§6.2): "this is an internal control requirement, not a technical
convenience". The two methods below are that separation, made executable.
Access control proper is out of scope (§3.3), so the caller passes an author
— but the *shape* of the rule is already in place, and wiring real roles later
touches this file only.
"""

from __future__ import annotations

from ..domain import entities as E
from ..domain.checks import CheckOutcome, has_blocking_failure, run_all
from ..domain.ports import AuditLog, DatasetRepository, ExtractionRepository
from ..domain.value_objects import Amount


class ValidationRefused(Exception):
    """BR-12 / FR-13 — a blocking check is failing."""

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
    ) -> list[CheckOutcome]:
        """Correct one field and rerun every check (BR-11, FR-12).

        Rerunning *all* the checks, not the ones that touch this field, is
        intentional. Correcting BK changes the asset subtotal, which changes
        the equilibrium, which can un-fail a check that had nothing to do
        with the field the analyst touched. Partial re-evaluation is how a
        system starts showing a green check that is no longer true.
        """
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

    # --- UC-06 ----------------------------------------------------------
    def validate(
        self, case: E.AnalysisCase, run: E.ExtractionRun, supervisor: str
    ) -> E.ValidatedDataset:
        """Freeze the data. After this, ratios become possible (BR-01).

        The blocking checks are rerun here rather than trusted from the last
        display. Between the analyst's screen and the supervisor's click, a
        correction may have landed. Trusting a cached verdict is how a
        dataset gets validated on checks that passed ten minutes ago.
        """
        outcomes = run_all(run.statement())
        if has_blocking_failure(outcomes):
            failures = [o for o in outcomes if o.is_blocking_failure]
            raise ValidationRefused(
                "validation refused: "
                + "; ".join(f"{o.code} {o.message}" for o in failures),
                failures,
            )

        dataset = E.ValidatedDataset(
            extraction_id=run.id,
            validated_by=supervisor,
            amounts={f.item_code: str(f.amount.value) for f in run.fields},
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
                detail={"extraction_id": run.id, "items": len(dataset.amounts)},
            )
        )
        return dataset

    # --- §15, reopening -------------------------------------------------
    def reopen(self, case: E.AnalysisCase, author: str, reason: str) -> None:
        """Permitted, but traced — and it invalidates the computed results.

        *** YOUR EXERCISE ***: the computed ratios are not invalidated yet.
        Decide what "invalidate" means concretely (delete the RatioResults?
        mark them stale? keep them with a pointer to the dataset that no
        longer exists?) and implement it. Write your reasoning down: it is a
        genuine design question, and there is no single right answer.
        """
        case.transition_to(E.UNDER_REVIEW)
        self.audit.record(
            E.AuditEntry(
                entity="AnalysisCase",
                entity_id=case.id,
                action="REOPENED",
                author=author,
                detail={"reason": reason},
            )
        )
