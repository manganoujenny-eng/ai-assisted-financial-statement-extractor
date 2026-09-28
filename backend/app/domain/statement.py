"""A financial statement as the domain layer sees it.

This is the only shape the ratio engine and the consistency checks ever
receive: a plain mapping of SYSCOHADA code -> Amount, for one fiscal year.
No PDF, no database row, no JSON. That is what makes it possible to run the
thousands of computations required by the sensitivity analysis of dossier
§19.2 in seconds, and to unit-test the whole business core with three lines
of setup.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Iterator, Mapping

from .value_objects import Amount, ItemCode


@dataclass(frozen=True)
class FinancialStatement:
    """Code-indexed amounts for one fiscal year.

    >>> fs = FinancialStatement.from_dict({"BK": 100, "BT": 20})
    >>> fs["BK"]
    Amount('100.00')
    >>> fs.get("XX") is None
    True
    """

    amounts: Mapping[str, Amount] = field(default_factory=dict)
    fiscal_year: int | None = None
    currency: str = "XAF"

    @classmethod
    def from_dict(
        cls,
        raw: Mapping[str, object],
        fiscal_year: int | None = None,
    ) -> "FinancialStatement":
        """Build from a plain dict, skipping entries with no usable amount.

        A missing item must stay missing. BR-02 is explicit: a ratio short of
        a required item is NOT_COMPUTABLE — it is never computed on a zero
        substituted for an absence. So ``None`` here is dropped, not coerced.
        """
        amounts: dict[str, Amount] = {}
        for key, value in raw.items():
            if value is None:
                continue
            code = ItemCode(key)  # raises on anything that is not a real code
            amounts[code.code] = value if isinstance(value, Amount) else Amount(value)
        return cls(amounts=amounts, fiscal_year=fiscal_year)

    @classmethod
    def from_extracted_json(
        cls,
        payload: Mapping[str, object],
        year: str = "current_year",
    ) -> "FinancialStatement":
        """Build from the JSON Helena's extractor already writes.

        ``data/extracted/*.json`` holds ``{"line_items": {"BK": {"code": ...,
        "current_year": ..., "prior_year": ...}}}``. This is the seam between
        the extraction work already done and the analysis work still to do.
        """
        line_items = payload.get("line_items") or {}
        raw = {}
        for code, item in line_items.items():  # type: ignore[union-attr]
            if len(str(code)) != 2 or not str(code).isalpha():
                continue
            raw[code] = item.get(year)  # type: ignore[union-attr]
        return cls.from_dict(raw)

    # --- read access ----------------------------------------------------
    def __getitem__(self, code: str | ItemCode) -> Amount:
        return self.amounts[str(code).upper()]

    def get(self, code: str | ItemCode) -> Amount | None:
        return self.amounts.get(str(code).upper())

    def __contains__(self, code: object) -> bool:
        return str(code).upper() in self.amounts

    def __iter__(self) -> Iterator[str]:
        return iter(self.amounts)

    def __len__(self) -> int:
        return len(self.amounts)

    def codes(self) -> set[str]:
        return set(self.amounts)

    def missing(self, required: Iterable[str]) -> list[str]:
        """Which of ``required`` this statement does not carry."""
        return sorted(code for code in required if code.upper() not in self.amounts)

    def with_override(self, code: str | ItemCode, value: object) -> "FinancialStatement":
        """Return a copy with one item changed.

        The statement is frozen, so perturbing an item for the error-injection
        protocol (dossier §19.2) produces a *new* statement. Nothing the
        campaign does can corrupt the ground truth it started from.
        """
        amounts = dict(self.amounts)
        amounts[ItemCode(code).code] = value if isinstance(value, Amount) else Amount(value)
        return FinancialStatement(
            amounts=amounts, fiscal_year=self.fiscal_year, currency=self.currency
        )

    def to_dict(self) -> dict[str, str]:
        return {code: str(amount.value) for code, amount in sorted(self.amounts.items())}
