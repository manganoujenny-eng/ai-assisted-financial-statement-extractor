"""The ratio engine.

It knows how to *run* a ratio. It does not know what any ratio computes.
That separation is what the Strategy pattern buys (dossier §13): the five
business rules BR-02, BR-03, BR-04, BR-15 are enforced once, here, for every
ratio present and every ratio added later.

Read ``compute_one`` carefully — it is twenty lines and it is where four of
the project's business rules actually live.
"""

from __future__ import annotations

from decimal import Decimal, DivisionUndefined, InvalidOperation

from ..statement import FinancialStatement
from ..value_objects import round_ratio
from .definition import (
    COMPUTED,
    NOT_COMPUTABLE,
    RatioDefinition,
    RatioResult,
)
from . import (
    r01_current_ratio,
    r02_equity_ratio,
    r03_stable_funding,
    r04_net_margin,
    r05_return_on_equity,
)

# Adding a ratio = adding a module and one line here. Nothing else changes.
_MODULES = (
    r01_current_ratio,
    r02_equity_ratio,
    r03_stable_funding,
    r04_net_margin,
    r05_return_on_equity,
)

REGISTRY: dict[str, RatioDefinition] = {m.DEFINITION.code: m.DEFINITION for m in _MODULES}


def definition_of(code: str) -> RatioDefinition:
    try:
        return REGISTRY[code.upper()]
    except KeyError:
        raise KeyError(f"unknown ratio: {code!r}. Known: {sorted(REGISTRY)}") from None


def compute_one(definition: RatioDefinition, statement: FinancialStatement) -> RatioResult:
    """Compute one ratio, or explain why it cannot be computed.

    This function never raises on business grounds and never returns a
    misleading number. Every path out of it is either a value or a reason.
    """
    # BR-02 — a missing required item is a reasoned absence, never a zero.
    missing = statement.missing(definition.required_items)
    if missing:
        return RatioResult(
            code=definition.code,
            name=definition.name,
            status=NOT_COMPUTABLE,
            unit=definition.unit,
            reason=f"missing item(s): {', '.join(missing)}",
            items_used=definition.required_items,
        )

    try:
        raw = definition.calculate(statement)
    except ZeroDivisionError:
        # BR-03 — a zero denominator is an answer, not a crash.
        return RatioResult(
            code=definition.code,
            name=definition.name,
            status=NOT_COMPUTABLE,
            unit=definition.unit,
            reason="zero denominator",
            items_used=definition.required_items,
        )
    except (InvalidOperation, DivisionUndefined):
        return RatioResult(
            code=definition.code,
            name=definition.name,
            status=NOT_COMPUTABLE,
            unit=definition.unit,
            reason="undefined arithmetic operation",
            items_used=definition.required_items,
        )
    except ValueError as exc:
        # A calculator may refuse a case it judges meaningless (see R5 and
        # negative equity). Its message becomes the reason shown to the user.
        return RatioResult(
            code=definition.code,
            name=definition.name,
            status=NOT_COMPUTABLE,
            unit=definition.unit,
            reason=str(exc),
            items_used=definition.required_items,
        )
    except NotImplementedError:
        # Exercise not written yet. Reported as such so the rest of the chain
        # keeps running while you work through the ratios one at a time.
        return RatioResult(
            code=definition.code,
            name=definition.name,
            status=NOT_COMPUTABLE,
            unit=definition.unit,
            reason="ratio not implemented yet",
            items_used=definition.required_items,
        )

    # BR-04 — keep what was used. BR-15 — round once, at the end.
    return RatioResult(
        code=definition.code,
        name=definition.name,
        status=COMPUTED,
        value=round_ratio(Decimal(raw)),
        unit=definition.unit,
        items_used=definition.required_items,
        inputs={code: str(statement[code].value) for code in definition.required_items},
    )


def compute_all(statement: FinancialStatement) -> list[RatioResult]:
    """Compute the whole core set, in registry order.

    No network call, no database access, no randomness: the same statement
    always produces exactly the same results (NFR-02). That property is what
    makes the sensitivity analysis of dossier §19.2 possible at all.
    """
    return [compute_one(definition, statement) for definition in REGISTRY.values()]
