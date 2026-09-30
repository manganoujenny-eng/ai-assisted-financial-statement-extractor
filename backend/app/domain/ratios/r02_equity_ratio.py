"""           ********* R2 — Equity ratio. ***********

    Equity / (Equity + Financial debt)
    CP / (CP + DD)

Family: structure. Unit: x. Reading: higher is better.

Notice what this module does NOT contain:

* no handling of a missing item — the engine checks ``required_items``
  before calling ``calculate`` (BR-02);
* no handling of a zero denominator — ``Amount.__truediv__`` raises
  ZeroDivisionError and the engine turns it into NOT_COMPUTABLE (BR-03);
* no rounding — that happens once, in the engine (BR-15);
* no judgement of the value — that is the interpretation layer's business,
  and BR-14 keeps it on a leash.

A calculator is four lines. If yours is twenty, something that belongs
somewhere else has leaked into it.
"""


from __future__ import annotations

from decimal import Decimal

from ..statement import FinancialStatement
from .definition import HIGHER_IS_BETTER, RatioDefinition


def calculate(statement: FinancialStatement) -> Decimal:
    numerator = statement["CP"]
    denominator = statement["CP"] + statement["DD"]
    return numerator / denominator


DEFINITION = RatioDefinition(
    code="R2",
    name="Equity ratio",
    family="Structure",
    formula="CP / (CP + DD)",
    required_items=("CP","DD" ),
    unit="x",
    direction=HIGHER_IS_BETTER,
    calculate=calculate,
)
