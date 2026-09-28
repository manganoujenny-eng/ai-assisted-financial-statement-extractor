"""R3 — Stable funding coverage.  *** YOUR EXERCISE ***

    (Equity + Financial debt) / Fixed assets
    (CP + DD) / AZ

Family: structure. Unit: x. Reading: higher is better — above 1 the long-term
resources cover the long-term uses, and the surplus is working capital.

The trap in this one
--------------------
AZ is the item your README already flags: ground truth annotates it against
the BRUT (gross) column while your extractor reports NET. Whichever one you
settle on, R3 moves. Before implementing, decide and write down *in one
sentence* which column R3 consumes, and why. That sentence belongs in the
thesis, because a jury will ask: two defensible conventions, one documented
choice.

Suggested answer to defend: NET, because the ratio compares resources
available today against assets as they stand on the balance sheet today, and
BZ — which CHK001 balances against — is itself a NET total. Mixing a BRUT
numerator with a NET balance sheet would make the equilibrium check and the
ratio disagree about what the same document says.
"""

from __future__ import annotations

from decimal import Decimal

from ..statement import FinancialStatement
from .definition import HIGHER_IS_BETTER, RatioDefinition


def calculate(statement: FinancialStatement) -> Decimal:
    raise NotImplementedError("R3 — see the module docstring")


DEFINITION = RatioDefinition(
    code="R3",
    name="Stable funding coverage",
    family="Structure",
    formula="(CP + DD) / AZ",
    required_items=(),  # TODO
    unit="x",
    direction=HIGHER_IS_BETTER,
    calculate=calculate,
)
