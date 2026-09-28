"""AnalysisService — ratios and interpretations, from validated data only.

Look at the signature of ``analyse``: it takes a ``ValidatedDataset``. Not a
case, not an extraction run, not a dict. There is no overload, no ``force=``
flag and no second entry point. That is how BR-01 — "no ratio is computed
from data that has not been validated by a human" — stops being a sentence in
a document and becomes a property of the code.

No call to a language model happens anywhere in this file (dossier §14.2).
"""

from __future__ import annotations

from ..domain import entities as E
from ..domain.interpretation import Interpretation, interpret_all
from ..domain.ports import AuditLog
from ..domain.ratios import RatioResult, compute_all


class AnalysisService:
    def __init__(self, audit: AuditLog) -> None:
        self.audit = audit

    def analyse(
        self, case: E.AnalysisCase, dataset: E.ValidatedDataset, author: str = "system"
    ) -> tuple[list[RatioResult], list[Interpretation]]:
        statement = dataset.statement()
        results = compute_all(statement)
        interpretations = interpret_all(results)

        if case.status == E.VALIDATED:
            case.transition_to(E.ANALYSED)

        self.audit.record(
            E.AuditEntry(
                entity="ValidatedDataset",
                entity_id=dataset.id,
                action="ANALYSED",
                author=author,
                detail={
                    "computed": [r.code for r in results if r.is_computed],
                    "not_computable": {
                        r.code: r.reason for r in results if not r.is_computed
                    },
                },
            )
        )
        return results, interpretations
