"""Parameterised sentences with their thresholds.

R1 and R3 are wired with documented reference thresholds. R2, R4 and R5
intentionally have no threshold: no sufficiently strong and
context-appropriate reference was identified to justify a universal
numerical benchmark for these ratios in the context of this project.

A ratio without a documented reference still receives a factual sentence
and no judgement. This is not a gap in the code: BR-14 deliberately
prevents the system from applying an invented threshold.

For R2, R4 and R5, the absence of a threshold must therefore be explained
as a methodological decision in the thesis. The ratio remains fully
calculated and reported; only the automatic threshold-based judgement is
omitted.

Inventing a numerical threshold is not an acceptable alternative.
"""


from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from ..ratios.definition import RatioResult

NO_REFERENCE = "NO_REFERENCE"


@dataclass(frozen=True)
class Threshold:
    """A reference value and where it comes from.

    ``source`` is mandatory in spirit even though Python cannot enforce it:
    a threshold whose source is empty is exactly the invented number BR-14
    forbids.
    """

    value: Decimal
    source: str
    below_label: str
    above_label: str


#: Documented references. Empty entries are deliberate — see module docstring.
THRESHOLDS: dict[str, Threshold | None] = {
    "R1": Threshold(
        value=Decimal("1.0"),
        source=(
            "Conventional solvency reading: current assets plus cash cover "
            "current liabilities plus short-term bank facilities. Stated in "
            "the methodological note accompanying this prototype."
        ),
        below_label="below the 1.0 reference",
        above_label="at or above the 1.0 reference",
    ),
    "R2": None,
    "R3": Threshold(
        value=Decimal("1.0"),
        source=(
            "Reference selected after comparison of multiple documented "
            "financial-analysis and prudential sources. The coverage of "
            "stable uses by stable resources is expected to reach at least "
            "100%. The prototype applies this reference to stable resources "
            "(equity plus financial debt) divided by net fixed assets."
        ),
        below_label="below the 1.0 coverage reference",
        above_label="at or above the 1.0 coverage reference",
    ),
    "R4": None,
    "R5": None ,
}


@dataclass(frozen=True)
class Interpretation:
    """A sentence, and everything needed to justify it.

    ``template_id`` and ``threshold_applied`` are stored with the text so
    that the sentence remains explainable months later — §12.1 asks for
    exactly this, and §20.1 makes it the only thing about interpretation that
    is actually evaluated.
    """

    ratio_code: str
    text: str
    template_id: str
    threshold_applied: str | None = None
    reference_source: str | None = None


def interpret(result: RatioResult) -> Interpretation:
    """Turn one ratio result into one traceable sentence.

    Three templates, and no fourth path. Every sentence this system can ever
    show comes from one of them.
    """
    # --- template NOT_COMPUTABLE -----------------------------------------
    if not result.is_computed:
        return Interpretation(
            ratio_code=result.code,
            text=(
                f"{result.name} could not be computed: {result.reason}. "
                f"No value is shown rather than a value that would be wrong."
            ),
            template_id="T_NOT_COMPUTABLE",
        )

    value_text = f"{result.value} {result.unit}".strip()
    threshold = THRESHOLDS.get(result.code)

    # --- template FACTUAL (no documented reference) ----------------------
    if threshold is None:
        return Interpretation(
            ratio_code=result.code,
            text=(
                f"{result.name} stands at {value_text}. No documented "
                f"reference is available for this ratio, so no judgement is "
                f"expressed."
            ),
            template_id="T_FACTUAL_NO_REFERENCE",
            threshold_applied=NO_REFERENCE,
        )

    # --- template COMPARED (a reference exists and is cited) -------------
    assert result.value is not None
    is_above = result.value >= threshold.value
    position = threshold.above_label if is_above else threshold.below_label
    return Interpretation(
        ratio_code=result.code,
        text=f"{result.name} stands at {value_text}, {position}.",
        template_id="T_COMPARED_TO_THRESHOLD",
        threshold_applied=str(threshold.value),
        reference_source=threshold.source,
    )


def interpret_all(results: list[RatioResult]) -> list[Interpretation]:
    return [interpret(result) for result in results]
