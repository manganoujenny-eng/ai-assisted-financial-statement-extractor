"""Shared fixtures.

``pytest`` finds this file automatically; anything defined here is available
to every test without an import. Run everything with, from the repository
root::

    pytest

and a single file with::

    pytest tests/unit/domain/test_ratios.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
for path in (str(BACKEND),):
    if path not in sys.path:
        sys.path.insert(0, path)

from app.domain.statement import FinancialStatement  # noqa: E402


#: A balance sheet that balances and an income statement that agrees with it.
#: Small round numbers on purpose: when a test fails you want to see at a
#: glance which item is wrong, not reach for a calculator.
#:
#:   assets      : AZ 4 000 000 + BK 6 746 235 + BT 500 000 = BZ 11 246 235
#:   liabilities : CP 5 000 000 + DD 2 000 000 + DP 3 746 235 + DT 500 000
#:                                                            = DZ 11 246 235
BALANCED = {
    "AZ": 4_000_000,
    "BK": 6_746_235,
    "BT": 500_000,
    "BU": 0,
    "BZ": 11_246_235,
    "CP": 5_000_000,
    "CJ": 1_000_000,
    "DD": 2_000_000,
    "DP": 3_746_235,
    "DT": 500_000,
    "DV": 0,
    "DZ": 11_246_235,
    "XB": 20_000_000,
    "XG": 1_500_000,
    "XI": 1_000_000,
}


@pytest.fixture
def balanced_amounts() -> dict:
    return dict(BALANCED)


@pytest.fixture
def balanced() -> FinancialStatement:
    return FinancialStatement.from_dict(BALANCED, fiscal_year=2024)


@pytest.fixture
def unbalanced() -> FinancialStatement:
    """The same statement with DZ out by 13 francs.

    Thirteen, not thirteen million: a plausible error is a far better test
    than an obvious one. Your own README records a real 13-franc discrepancy
    in the Excel test file — this fixture is that bug, turned into a test.
    """
    broken = dict(BALANCED)
    broken["DZ"] = 11_246_248
    return FinancialStatement.from_dict(broken, fiscal_year=2024)
