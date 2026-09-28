"""R4 — Net margin.  *** YOUR EXERCISE ***

    Net income / Revenue x 100
    XI / XB x 100

Family: profitability. Unit: %. Reading: higher is better.

Two traps in this one
---------------------
1. **The x 100.** ``Amount / Amount`` gives a Decimal. Multiply by
   ``Decimal(100)``, never by the integer literal inside a float expression.
   And do not round here: the engine rounds once, at the end (BR-15).

2. **The sign of XI.** This is the ambiguity your README already documents.
   A loss is a negative net income and a negative margin — which is correct
   and must stay negative. But if the ``+``/``-`` operator column is not
   interpreted, a loss can arrive as a positive number, and R4 will then
   report a healthy margin for a company that lost money. That is the
   textbook *silent false positive* of dossier §18.1: a wrong value that
   passed every check and reached a client-facing indicator.

   Write the ratio plainly. Then, as a separate piece of work, resolve the
   sign column in the extractor. Do not paper over it here — a guard in R4
   would hide the problem instead of measuring it, and measuring it is the
   contribution of the thesis.
"""

from __future__ import annotations

from decimal import Decimal

from ..statement import FinancialStatement
from .definition import HIGHER_IS_BETTER, RatioDefinition


def calculate(statement: FinancialStatement) -> Decimal:
    raise NotImplementedError("R4 — see the module docstring")


DEFINITION = RatioDefinition(
    code="R4",
    name="Net margin",
    family="Profitability",
    formula="XI / XB x 100",
    required_items=(),  # TODO
    unit="%",
    direction=HIGHER_IS_BETTER,
    calculate=calculate,
)
