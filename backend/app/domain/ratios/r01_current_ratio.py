"""      ****************  R1 — Current ratio. ************************

    (Current assets + Cash) / (Current liabilities + Short-term bank facilities)
    (BK + BT) / (DP + DT)

Family: liquidity. Unit: x (a pure number — francs over francs).
Reading: above 1, the company can cover what it owes within the year out of
what it holds; below 1, it cannot, *at that date*.

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
    numerator = statement["BK"] + statement["BT"]
    denominator = statement["DP"] + statement["DT"]
    return numerator / denominator


DEFINITION = RatioDefinition(
    code="R1",
    name="Current ratio",
    family="Liquidity",
    formula="(BK + BT) / (DP + DT)",
    required_items=("BK", "BT", "DP", "DT"),
    unit="x",
    direction=HIGHER_IS_BETTER,
    calculate=calculate,
)
