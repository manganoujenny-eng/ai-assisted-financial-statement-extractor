"""Value objects of the domain layer.

A *value object* has no identity: two Amounts holding the same number in the
same currency are the same Amount. They are immutable, they validate
themselves on construction, and they centralise the rules that would
otherwise be scattered (rounding, currency, code format).

Design dossier: section 13, pattern "Value object".
Business rule BR-15: amounts in CFA francs rounded to two decimals,
ratios to one decimal with their unit.

This module has no import outside the standard library. That is deliberate:
the domain layer must be testable without network, database or PDF (NFR-06).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Union

# Decimal, not float. A float cannot hold 0.1 exactly; on a balance sheet of
# several billion CFA francs, that inexactness becomes a visible discrepancy
# in the equilibrium check. Try it in a REPL: 0.1 + 0.2 == 0.3 is False.
Number = Union[int, str, Decimal]

AMOUNT_QUANTUM = Decimal("0.01")  # BR-15: two decimals
RATIO_QUANTUM = Decimal("0.1")  # BR-15: one decimal


@dataclass(frozen=True, order=True)
class Amount:
    """A monetary amount in CFA francs (XAF).

    >>> Amount(1000) + Amount(234)
    Amount('1234.00')
    >>> Amount("1 234 567")          # SYSCOHADA thousands separator
    Amount('1234567.00')
    >>> Amount(10) / Amount(4)
    Decimal('2.5')
    """

    value: Decimal

    def __init__(self, value: Number) -> None:
        if isinstance(value, Amount):  # tolerate re-wrapping
            value = value.value
        if isinstance(value, float):
            raise TypeError(
                "Amount refuses float: pass an int, a str or a Decimal. "
                "Floats lose precision on large amounts."
            )
        if isinstance(value, str):
            value = value.strip().replace(" ", "").replace(" ", "")
            if value in ("", "-"):
                # SYSCOHADA prints a bare dash for a nil line.
                value = "0"
        try:
            quantised = Decimal(value).quantize(AMOUNT_QUANTUM, rounding=ROUND_HALF_UP)
        except Exception as exc:  # noqa: BLE001 - re-raised with context
            raise ValueError(f"not a valid amount: {value!r}") from exc
        object.__setattr__(self, "value", quantised)

    # --- arithmetic -----------------------------------------------------
    def __add__(self, other: "Amount") -> "Amount":
        return Amount(self.value + _as_decimal(other))

    def __sub__(self, other: "Amount") -> "Amount":
        return Amount(self.value - _as_decimal(other))

    def __truediv__(self, other: "Amount") -> Decimal:
        """Amount / Amount is a plain number, not an Amount.

        Dividing francs by francs gives a dimensionless ratio. Returning an
        Amount here would be a category error — and it is exactly the kind
        of mistake a value object exists to prevent.
        """
        divisor = _as_decimal(other)
        if divisor == 0:
            raise ZeroDivisionError("division by a zero amount")
        return self.value / divisor

    def __neg__(self) -> "Amount":
        return Amount(-self.value)

    def is_zero(self) -> bool:
        return self.value == 0

    def is_negative(self) -> bool:
        return self.value < 0

    def abs(self) -> "Amount":
        return Amount(abs(self.value))

    def __repr__(self) -> str:
        return f"Amount('{self.value}')"

    def __str__(self) -> str:
        """Human formatting, SYSCOHADA style: 1 234 567,89"""
        sign = "-" if self.value < 0 else ""
        whole, _, decimals = f"{abs(self.value):.2f}".partition(".")
        grouped = " ".join(
            whole[max(i - 3, 0):i] for i in range(len(whole), 0, -3)
        ).strip()
        grouped = " ".join(reversed(grouped.split(" ")))
        return f"{sign}{grouped},{decimals}"


def _as_decimal(other: object) -> Decimal:
    if isinstance(other, Amount):
        return other.value
    if isinstance(other, (int, str, Decimal)):
        return Amount(other).value
    raise TypeError(f"cannot combine Amount with {type(other).__name__}")


ZERO = Amount(0)


# --------------------------------------------------------------------------
ITEM_CODE_PATTERN = re.compile(r"^[A-Z]{2}$")


@dataclass(frozen=True, order=True)
class ItemCode:
    """A SYSCOHADA line-item code: exactly two uppercase letters.

    BK, CP, XB, DZ... The pattern is the same one Helena's extractor already
    uses to find where real data starts in a table
    (``document_processing/structure.py``, ``CODE_PATTERN``). Wrapping it in
    a type means a code can never be silently confused with a label or with
    an arbitrary string.

    >>> ItemCode("bk")
    ItemCode('BK')
    >>> ItemCode("B1")
    Traceback (most recent call last):
    ValueError: not a SYSCOHADA item code: 'B1'
    """

    code: str

    def __init__(self, code: str) -> None:
        normalised = str(code).strip().upper()
        if not ITEM_CODE_PATTERN.match(normalised):
            raise ValueError(f"not a SYSCOHADA item code: {code!r}")
        object.__setattr__(self, "code", normalised)

    def __str__(self) -> str:
        return self.code

    def __repr__(self) -> str:
        return f"ItemCode('{self.code}')"


def round_ratio(value: Decimal) -> Decimal:
    """BR-15: a ratio is displayed to one decimal."""
    return Decimal(value).quantize(RATIO_QUANTUM, rounding=ROUND_HALF_UP)
