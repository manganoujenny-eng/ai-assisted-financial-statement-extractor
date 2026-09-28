"""R5 — Return on equity.  *** YOUR EXERCISE ***

    Net income / Equity x 100
    XI / CP x 100

Family: profitability. Unit: %. Reading: higher is better.

The trap in this one
--------------------
Negative equity. A company that has accumulated losses can have CP < 0, and
then R5 is *arithmetically* computable but *financially* meaningless: a loss
divided by negative equity comes out positive, and the dashboard shows a
splendid return on equity for a company that is technically insolvent.

Do not silently return the number. Two defensible options — pick one, write
down why, and be ready to defend it:

  (a) compute it anyway and let the interpretation template refuse to read a
      ratio built on negative equity;
  (b) return NOT_COMPUTABLE with the reason "negative equity", which is
      exactly what BR-02 and BR-03 exist for — a reasoned absence of value
      rather than a misleading one.

Option (b) is the stricter reading of the dossier and the easier one to
defend in front of a jury. To take it, raise ``ValueError("negative equity")``
in ``calculate``; ``engine.py`` already turns a ValueError into
NOT_COMPUTABLE carrying your message as the reason. Look at
``engine.compute_one`` to see how, then decide.

This is the first design decision on the project that is genuinely yours.
"""

from __future__ import annotations

from decimal import Decimal

from ..statement import FinancialStatement
from .definition import HIGHER_IS_BETTER, RatioDefinition


def calculate(statement: FinancialStatement) -> Decimal:
    raise NotImplementedError("R5 — see the module docstring")


DEFINITION = RatioDefinition(
    code="R5",
    name="Return on equity",
    family="Profitability",
    formula="XI / CP x 100",
    required_items=(),  # TODO
    unit="%",
    direction=HIGHER_IS_BETTER,
    calculate=calculate,
)
