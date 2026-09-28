"""R2 — Equity ratio.  *** YOUR EXERCISE ***

    Equity / (Equity + Financial debt)
    CP / (CP + DD)

Family: structure. Unit: x. Reading: higher is better.

What to do
----------
1. Write ``calculate`` — two lines, modelled on ``r01_current_ratio.py``.
2. Fill in ``required_items`` (it is empty, which is why the engine currently
   answers "not implemented yet" rather than "missing item").
3. ``tests/unit/domain/test_ratios.py::TestR2`` is already written and
   currently skipped. Delete its ``@pytest.mark.skip`` line and make it pass.

The module is already registered in ``engine.py``, so the moment ``calculate``
returns a number the dashboard shows it. Nothing else to wire.

The trap in this one
--------------------
CP and DD can both be zero (a shell company with no equity and no debt).
Do NOT guard against it here. Let ``Amount.__truediv__`` raise
ZeroDivisionError and let the engine answer NOT_COMPUTABLE with a reason —
that is BR-03, and it is the engine's job precisely so that you do not write
the same guard five times. A test covers this case.

Second point, worth a paragraph in your thesis: CP appears in R2, R3 and R5.
Three of the five ratios depend on the same item. An extraction error on CP
corrupts three indicators at once — that is exactly the amplification
phenomenon of dossier §18, visible before a single measurement is taken.
"""

from __future__ import annotations

from decimal import Decimal

from ..statement import FinancialStatement
from .definition import HIGHER_IS_BETTER, RatioDefinition


def calculate(statement: FinancialStatement) -> Decimal:
    raise NotImplementedError("R2 — see the module docstring")


DEFINITION = RatioDefinition(
    code="R2",
    name="Equity ratio",
    family="Structure",
    formula="CP / (CP + DD)",
    required_items=(),  # TODO: which items does this ratio need?
    unit="x",
    direction=HIGHER_IS_BETTER,
    calculate=calculate,
)
