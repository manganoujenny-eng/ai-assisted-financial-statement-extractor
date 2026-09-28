"""EvaluationService — Part D, the part that makes this research.

Two things happen here, and they are different in nature:

1. **Controlled error injection** (§19.2) — implemented below, in full.
   Perturb one item by a known percentage, recompute every ratio, measure
   what moved. It is mechanical, it needs no corpus, it runs in seconds
   because the domain layer needs nothing to run, and it produces the item x
   ratio sensitivity matrix the firm can reuse after the internship.

2. **Campaign measurement against ground truth** (§18.1) — *your exercise*.
   Field-level accuracy, ratio-level accuracy, the amplification coefficient,
   item criticality, and above all the silent false positives. The formulas
   are written out in the docstrings; the corpus is yours to build in W2.

Run the sensitivity matrix the day R2..R5 are implemented, before the corpus
exists. You will already be able to see which item carries the most risk —
and that single table will change how you spend weeks 3 to 7.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from ..domain.checks import has_blocking_failure, run_all
from ..domain.ratios import COMPUTED, compute_all
from ..domain.statement import FinancialStatement

#: The perturbations of dossier §19.2: one, five and ten per cent.
DEFAULT_PERTURBATIONS = (Decimal("0.01"), Decimal("0.05"), Decimal("0.10"))


@dataclass
class SensitivityCell:
    """One (item, ratio, perturbation) measurement."""

    item_code: str
    ratio_code: str
    perturbation: Decimal
    baseline_value: Decimal | None
    perturbed_value: Decimal | None
    relative_deviation: Decimal | None  # |perturbed - baseline| / |baseline|
    intercepted_by_checks: bool = False

    @property
    def is_measurable(self) -> bool:
        return self.relative_deviation is not None


@dataclass
class SensitivityMatrix:
    cells: list[SensitivityCell] = field(default_factory=list)

    def for_item(self, item_code: str) -> list[SensitivityCell]:
        return [c for c in self.cells if c.item_code == item_code]

    def average_sensitivity(self, item_code: str, ratio_code: str) -> Decimal | None:
        """Mean relative deviation induced in one ratio by one item."""
        values = [
            c.relative_deviation
            for c in self.cells
            if c.item_code == item_code
            and c.ratio_code == ratio_code
            and c.relative_deviation is not None
        ]
        if not values:
            return None
        return sum(values) / Decimal(len(values))

    def criticality(self, item_code: str) -> Decimal:
        """Dossier §18.1 — dependent ratios weighted by average sensitivity.

        This is the number that answers sub-question 4 of the dossier: where
        should reliability effort go? Not to the item hardest to extract — to
        the item whose errors travel furthest.
        """
        ratio_codes = {c.ratio_code for c in self.cells if c.item_code == item_code}
        total = Decimal(0)
        for ratio_code in ratio_codes:
            average = self.average_sensitivity(item_code, ratio_code)
            if average is not None:
                total += average
        return total

    def interception_rate(self) -> Decimal | None:
        """Share of injected errors the consistency checks would have caught.

        The complement of this number is the silent-false-positive surface:
        perturbations that reach a ratio without a single check firing. That
        is the scenario the whole system exists to prevent (§18.1), so this
        one line is arguably the most important measurement in the project.
        """
        measurable = [c for c in self.cells if c.is_measurable]
        if not measurable:
            return None
        intercepted = sum(1 for c in measurable if c.intercepted_by_checks)
        return Decimal(intercepted) / Decimal(len(measurable))

    def to_rows(self) -> list[dict]:
        return [
            {
                "item": c.item_code,
                "ratio": c.ratio_code,
                "perturbation": str(c.perturbation),
                "baseline": str(c.baseline_value) if c.baseline_value is not None else None,
                "perturbed": str(c.perturbed_value) if c.perturbed_value is not None else None,
                "relative_deviation": str(c.relative_deviation)
                if c.relative_deviation is not None
                else None,
                "intercepted_by_checks": c.intercepted_by_checks,
            }
            for c in self.cells
        ]


class EvaluationService:
    """Pure computation: no repository, no HTTP, no model call.

    That is why a full sensitivity campaign over a dozen items, five ratios
    and three perturbation levels — a couple of hundred complete ratio
    computations — finishes before you lift your finger off the return key.
    """

    # --- §19.2, implemented ---------------------------------------------
    def sensitivity_matrix(
        self,
        ground_truth: FinancialStatement,
        items: tuple[str, ...] | None = None,
        perturbations: tuple[Decimal, ...] = DEFAULT_PERTURBATIONS,
    ) -> SensitivityMatrix:
        """Perturb one item at a time and measure what each ratio does.

        Step 5 of the protocol — "check which of those perturbations the
        consistency checks would have intercepted" — is the ``intercepted``
        flag below. Without it the matrix says how fragile the ratios are;
        with it, the matrix says how much of that fragility the system
        actually defends against.
        """
        baseline = {r.code: r for r in compute_all(ground_truth)}
        targets = items or tuple(sorted(ground_truth.codes()))
        matrix = SensitivityMatrix()

        for item_code in targets:
            original = ground_truth[item_code]
            for perturbation in perturbations:
                perturbed_amount = original.value * (Decimal(1) + perturbation)
                perturbed_statement = ground_truth.with_override(
                    item_code, perturbed_amount
                )
                intercepted = has_blocking_failure(run_all(perturbed_statement))
                perturbed = {r.code: r for r in compute_all(perturbed_statement)}

                for ratio_code, base_result in baseline.items():
                    new_result = perturbed[ratio_code]
                    deviation = _relative_deviation(base_result, new_result)
                    matrix.cells.append(
                        SensitivityCell(
                            item_code=item_code,
                            ratio_code=ratio_code,
                            perturbation=perturbation,
                            baseline_value=base_result.value,
                            perturbed_value=new_result.value,
                            relative_deviation=deviation,
                            intercepted_by_checks=intercepted,
                        )
                    )
        return matrix

    # --- §18.1, YOUR EXERCISES ------------------------------------------
    def field_accuracy(self, extracted: FinancialStatement, truth: FinancialStatement) -> Decimal:
        """Share of extracted fields whose amount matches ground truth exactly.

        TO IMPLEMENT. Two decisions to make before you write a line, and both
        belong in the thesis:

        * an item present in the truth and absent from the extraction — does
          it count as an error, or is it outside the denominator? (Answer:
          it must count, otherwise an extractor that returns one correct
          field scores 100 %.)
        * "exactly" means exactly. Do not introduce a tolerance here without
          writing down why, because ratio-level accuracy already has one
          (one per cent) and mixing the two conventions makes the
          amplification coefficient meaningless.
        """
        raise NotImplementedError("field_accuracy — see the docstring")

    def ratio_accuracy(
        self, extracted: FinancialStatement, truth: FinancialStatement
    ) -> Decimal:
        """Share of ratios within one per cent of the ground-truth value.

        TO IMPLEMENT. Careful with the NOT_COMPUTABLE cases: a ratio that is
        NOT_COMPUTABLE in both runs agrees with the truth — it is not an
        error. A ratio computable in one and not the other is an error, and
        an interesting one: it means the extraction lost a required item.
        """
        raise NotImplementedError("ratio_accuracy — see the docstring")

    def amplification_coefficient(
        self, field_accuracy: Decimal, ratio_accuracy: Decimal
    ) -> Decimal | None:
        """Ratio-level error rate divided by field-level error rate.

        TO IMPLEMENT — three lines, and the headline number of the thesis.
        Error rate is ``1 - accuracy``. Above 1 means the chain amplifies:
        a given proportion of wrong fields produces a larger proportion of
        wrong indicators. Below 1 means it absorbs.

        Guard the zero denominator (a perfect extraction has an error rate of
        zero and no amplification is defined) — and notice that you already
        know how to express that: a reasoned absence of value, exactly like
        BR-03.
        """
        raise NotImplementedError("amplification_coefficient — see the docstring")

    def silent_false_positives(
        self, extracted: FinancialStatement, truth: FinancialStatement
    ) -> list[str]:
        """Wrong values that passed every automated check. §18.1.

        TO IMPLEMENT, and implement this one first. It is the indicator the
        dossier calls "the most important of all": an error that clears the
        checks and ends up in a ratio shown to a client.

        Method: take the items where extraction and truth disagree; run the
        checks on the extracted statement; if no blocking check fails, every
        one of those disagreements is silent. Return their codes.
        """
        raise NotImplementedError("silent_false_positives — see the docstring")


def _relative_deviation(base, perturbed) -> Decimal | None:
    if base.status != COMPUTED or perturbed.status != COMPUTED:
        return None
    if base.value is None or perturbed.value is None or base.value == 0:
        return None
    return abs(perturbed.value - base.value) / abs(base.value)
