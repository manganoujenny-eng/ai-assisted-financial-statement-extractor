"""EvaluationService — Part D, the part that makes this research.

Two things happen here, and they are different in nature:

1. **Controlled error injection** (§19.2) — implemented below, in full.
   Perturb one item by a known percentage, recompute every ratio, measure
   what moved. It is mechanical, it needs no corpus, it runs in seconds
   because the domain layer needs nothing to run, and it produces the item x
   ratio sensitivity matrix the firm can reuse after the internship.

2. **Campaign measurement against ground truth** (§18.1) — week 7,
   exercises 16 to 19: silent false positives, field-level accuracy,
   ratio-level accuracy and the amplification coefficient. Each compares
   one extraction with its hand-made ground truth (the W2 corpus).

Run the sensitivity matrix the day R2..R5 are implemented, before the corpus
exists. You will already be able to see which item carries the most risk —
and that single table will change how you spend weeks 3 to 7.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

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
                            baseline_value=base_result.measured,
                            perturbed_value=new_result.measured,
                            relative_deviation=deviation,
                            intercepted_by_checks=intercepted,
                        )
                    )
        return matrix

    # --- §18.1, campaign measurement against ground truth ---------------
    #
    # The four measurements compare ONE extraction with ONE ground truth.
    # Decisions taken (each one belongs in the thesis):
    #
    #   * The ground truth defines what is judged. It lists the required
    #     items (W2); an extra line the extractor also read has no reference
    #     value, so it is outside every denominator.
    #   * A field is right only if its amount is EXACTLY the truth's (to the
    #     franc cent, BR-15). The only tolerance is the 1 % on ratios.
    #   * A missing item is an error for field accuracy, but NOT a silent
    #     false positive: CHK004 blocks the case and the ratio says
    #     NOT_COMPUTABLE, so the absence is visible.

    def silent_false_positives(
        self, extracted: FinancialStatement, truth: FinancialStatement
    ) -> list[str]:
        """Exercise 16 — wrong values that passed every automated check. §18.1.

        The indicator the dossier calls "the most important of all": an
        error that clears the checks and ends up in a ratio shown to a client.

        1. the items where extraction and truth disagree: present in both,
           with a different amount (an absence is visible, see above);
        2. run the checks on the EXTRACTED statement — the only one the
           system ever sees;
        3. if a blocking check fails, the case cannot be validated and an
           analyst has to look at it: nothing is silent. Otherwise every
           disagreement is silent.

        Returns the codes, sorted. Two compensating errors (BK +100,
        BT -100) are both returned: that is exactly the case the checks
        cannot see.
        """
        wrong = _wrong_values(extracted, truth)
        if not wrong:
            return []
        if has_blocking_failure(run_all(extracted)):
            return []
        return wrong

    def field_accuracy(self, extracted: FinancialStatement, truth: FinancialStatement) -> Decimal:
        """Exercise 17 — share of ground-truth fields extracted exactly.

            right fields / fields in the ground truth

        A field missing from the extraction counts as wrong — otherwise an
        extractor returning one correct field would score 100 %.
        """
        if not len(truth):
            raise ValueError("the ground truth is empty: nothing to measure")
        right = sum(
            1
            for code in truth
            if extracted.get(code) is not None and extracted[code] == truth[code]
        )
        return Decimal(right) / Decimal(len(truth))

    def ratio_accuracy(
        self, extracted: FinancialStatement, truth: FinancialStatement
    ) -> Decimal:
        """Exercise 18 — share of ratios within 1 % of the ground-truth value.

        For each ratio of the registry:

        * NOT_COMPUTABLE in both        -> right (the same reasoned absence);
        * computable in one side only   -> wrong (a required item was lost,
          or invented);
        * computed in both              -> right if |e - t| <= 1 % of |t|
          (when t is 0, only e = 0 is right).
        """
        mine = {r.code: r for r in compute_all(extracted)}
        reference = compute_all(truth)
        right = sum(1 for t in reference if _ratio_agrees(mine.get(t.code), t))
        return Decimal(right) / Decimal(len(reference))

    def amplification_coefficient(
        self, field_accuracy: Decimal, ratio_accuracy: Decimal
    ) -> Decimal | None:
        """Exercise 19 — ratio error rate / field error rate. The headline number.

        Above 1 the chain amplifies (a share of wrong fields produces a larger
        share of wrong indicators); below 1 it absorbs. A perfect extraction
        has an error rate of zero: no amplification is defined, so the answer
        is a reasoned absence (None), like BR-03. Rounded to two decimals:
        it is a number to report, and 14/15 has no exact decimal form.
        """
        field_error = Decimal(1) - Decimal(field_accuracy)
        if field_error == 0:
            return None
        ratio_error = Decimal(1) - Decimal(ratio_accuracy)
        return (ratio_error / field_error).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


#: Ratio-level tolerance of §18.1: one per cent of the ground-truth value.
RATIO_TOLERANCE = Decimal("0.01")


def _wrong_values(extracted: FinancialStatement, truth: FinancialStatement) -> list[str]:
    """Ground-truth items extracted with a different amount (not missing)."""
    return sorted(
        code
        for code in truth
        if extracted.get(code) is not None and extracted[code] != truth[code]
    )


def _ratio_agrees(extracted, truth) -> bool:
    """Both sides compared on their UNROUNDED value (``measured``).

    Rounded to one decimal, R2 = 0.964 and R2 = 0.955 both show 1.0 and
    would "agree" although they are 0.9 % apart — and 1.04 vs 1.05 would
    "disagree" on display while being within tolerance. The 1 % tolerance
    is a statement about the numbers, not about their display.
    """
    if extracted is None:
        return truth.status != COMPUTED
    if truth.status != COMPUTED or extracted.status != COMPUTED:
        return truth.status == extracted.status
    t, e = truth.measured, extracted.measured
    if t is None or e is None:
        return t is None and e is None
    if t == 0:
        return e == 0
    return abs(e - t) <= RATIO_TOLERANCE * abs(t)


def _relative_deviation(base, perturbed) -> Decimal | None:
    """Measured on the unrounded values: see ``RatioResult.exact``."""
    if base.status != COMPUTED or perturbed.status != COMPUTED:
        return None
    b, p = base.measured, perturbed.measured
    if b is None or p is None or b == 0:
        return None
    return abs(p - b) / abs(b)