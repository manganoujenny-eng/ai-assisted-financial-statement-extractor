"""What a ratio *is*, before anything computes it.

Dossier §12.1: "RatioDefinition — describes a ratio: formula, required items,
unit, reading direction. Adding a ratio means adding a definition and its
calculator." That sentence is the whole design of this package, and the
Strategy pattern of §13 is what makes it true: the engine never grows when a
ratio is added.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Callable

from ..statement import FinancialStatement

COMPUTED = "COMPUTED"
NOT_COMPUTABLE = "NOT_COMPUTABLE"

#: Reading direction — does a high value read as favourable?
#: Never used to *judge* a ratio on its own: BR-14 forbids calling a ratio
#: favourable without an explicit reference. It only tells the interpretation
#: templates which way to phrase a comparison against a stated threshold.
HIGHER_IS_BETTER = "HIGHER_IS_BETTER"
LOWER_IS_BETTER = "LOWER_IS_BETTER"
NEUTRAL = "NEUTRAL"


@dataclass(frozen=True)
class RatioDefinition:
    code: str
    name: str
    family: str  # Liquidity | Structure | Profitability
    formula: str  # human-readable, shown in the interface next to the value
    required_items: tuple[str, ...]
    unit: str  # "x" for a pure ratio, "%" for a percentage
    direction: str
    calculate: Callable[[FinancialStatement], Decimal]


@dataclass(frozen=True)
class RatioResult:
    """A value, or a reasoned absence of value (dossier §12.1).

    ``items_used`` is stored with the result on purpose (BR-04): it is what
    makes the propagation analysis of §18 computable after the fact, without
    replaying the chain. Do not drop it when you persist the result.
    """

    code: str
    name: str
    status: str
    value: Decimal | None = None
    unit: str = ""
    reason: str | None = None
    items_used: tuple[str, ...] = ()
    inputs: dict[str, str] | None = None
    #: The value BEFORE the one-decimal rounding of BR-15. ``value`` is what
    #: people see; ``exact`` is what the evaluation measures (week 7). Rounded
    #: to one decimal, R2 = 0.964 shows as 1.0 and a 10 % error on DD moves
    #: it to 0.9 or not at all — the measurement would see the rounding, not
    #: the error. Never displayed, never persisted.
    exact: Decimal | None = None

    @property
    def measured(self) -> Decimal | None:
        """The value to measure with: exact when known, else the shown one."""
        return self.exact if self.exact is not None else self.value

    @property
    def is_computed(self) -> bool:
        return self.status == COMPUTED
