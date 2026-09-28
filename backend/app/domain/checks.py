"""Accounting consistency checks.

A check answers one question about a statement and answers it the same way
every time. It never calls a language model, never touches the database,
never raises on bad data — it *reports*.

Severity decides what the rest of the system may do (BR-12, FR-13):

* BLOCKING — validation is refused while it fails.
* WARNING  — recorded and displayed, but does not stop anything.

Two checks are implemented below as worked examples, one of each severity.
The remaining three are your exercises: the contract, the tests and the
guidance are already written, only the body is missing.

Dossier: §3.2 (checks), BR-05 to BR-09, FR-09, FR-12.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Callable

from .statement import FinancialStatement
from .syscohada import REQUIRED_CODES
from .value_objects import Amount

BLOCKING = "BLOCKING"
WARNING = "WARNING"


@dataclass(frozen=True)
class CheckOutcome:
    """What one check has to say about one statement.

    ``gap`` is the quantified discrepancy the dossier asks every check to
    carry (§12.1, CheckResult). It is what turns "the balance sheet does not
    balance" into "the balance sheet is out by 13 F CFA" — the difference
    between an alarm and a diagnosis.
    """

    code: str
    label: str
    severity: str
    passed: bool
    gap: Decimal | None = None
    message: str = ""
    items_used: tuple[str, ...] = ()

    @property
    def is_blocking_failure(self) -> bool:
        return self.severity == BLOCKING and not self.passed


@dataclass(frozen=True)
class Check:
    """One consistency check. See ``REGISTRY`` at the bottom of the module."""

    code: str
    label: str
    severity: str
    run: Callable[[FinancialStatement], CheckOutcome] = field(repr=False)


def _skipped(code: str, label: str, severity: str, missing: list[str]) -> CheckOutcome:
    """A check that cannot run because an item it needs is absent.

    It is reported as *passed* with an explicit message rather than failed.
    Reason: a missing item is the completeness check's business (CHK004), and
    failing it twice would make one problem look like two. Say this out loud
    at the defence — a jury asks exactly this kind of question.
    """
    return CheckOutcome(
        code=code,
        label=label,
        severity=severity,
        passed=True,
        gap=None,
        message=f"not evaluated — missing item(s): {', '.join(missing)}",
        items_used=tuple(missing),
    )


# ==========================================================================
# CHK001 — worked example of a BLOCKING check
# ==========================================================================
def check_balance_equilibrium(statement: FinancialStatement) -> CheckOutcome:
    """BR-05 — total assets equal total liabilities and equity. Zero tolerance.

    BZ (TOTAL GÉNÉRAL ACTIF) must equal DZ (TOTAL GÉNÉRAL PASSIF). This is
    the oldest rule in accounting and the cheapest way to catch an extraction
    that read one column too far to the right.

    Zero tolerance means exactly zero: amounts are Decimal, not float, so
    equality is safe to test directly.
    """
    missing = statement.missing(["BZ", "DZ"])
    if missing:
        return _skipped("CHK001", "Balance sheet equilibrium", BLOCKING, missing)

    assets = statement["BZ"]
    liabilities = statement["DZ"]
    gap = (assets - liabilities).value
    passed = gap == 0

    return CheckOutcome(
        code="CHK001",
        label="Balance sheet equilibrium",
        severity=BLOCKING,
        passed=passed,
        gap=gap,
        message=(
            "BZ = DZ"
            if passed
            else f"BZ ({assets}) ≠ DZ ({liabilities}), gap of {Amount(gap)}"
        ),
        items_used=("BZ", "DZ"),
    )


# ==========================================================================
# CHK005 — worked example of a WARNING check
# ==========================================================================
def check_plausible_signs(statement: FinancialStatement) -> CheckOutcome:
    """BR-08 — a negative asset or negative revenue warns, it does not block.

    Why a warning and not a block: a negative revenue is almost certainly an
    extraction error, but "almost certainly" is not "certainly", and blocking
    a case on a judgement call would push analysts to work around the system.
    A warning that is read beats a block that is bypassed.
    """
    suspicious: list[str] = []
    for code in ("AZ", "BK", "BT", "BZ", "XB"):
        amount = statement.get(code)
        if amount is not None and amount.is_negative():
            suspicious.append(f"{code} = {amount}")

    passed = not suspicious
    return CheckOutcome(
        code="CHK005",
        label="Plausible signs on assets and revenue",
        severity=WARNING,
        passed=passed,
        gap=None,
        message="all signs plausible" if passed else "negative: " + "; ".join(suspicious),
        items_used=("AZ", "BK", "BT", "BZ", "XB"),
    )


# ==========================================================================
# CHK002 — YOUR EXERCISE (blocking)
# ==========================================================================
def check_subtotal_consistency(statement: FinancialStatement) -> CheckOutcome:
    """BR-06 — the headings inside an aggregate sum to that aggregate's total.

    TO IMPLEMENT. On the SYSCOHADA revised balance sheet:

        assets      : AZ + BK + BT + BU  ==  BZ
        liabilities : CP + DD + DP + DT + DV  ==  DZ

    BU and DV (currency translation differences) are frequently absent from a
    package. Treat an absent BU/DV as zero *for this check only* — that is a
    presentation convention, not the substitution BR-02 forbids. AZ, BK, BT,
    BZ, CP, DD, DP, DT, DZ on the other hand are required: if one is missing,
    return ``_skipped(...)``.

    Report the larger of the two gaps, and name in ``message`` which side is
    out. An engagement manager reading "liabilities side out by 1 000" knows
    where to look; one reading "subtotals inconsistent" does not.

    Tests waiting for you: ``tests/unit/domain/test_checks.py::TestCHK002``.
    Remove the ``@pytest.mark.skip`` there when you start.
    """
    raise NotImplementedError("CHK002 — see the docstring, then delete this line")


# ==========================================================================
# CHK003 — YOUR EXERCISE (blocking)
# ==========================================================================
def check_net_income_consistency(statement: FinancialStatement) -> CheckOutcome:
    """BR-07 — net income in the income statement equals net income in equity.

    TO IMPLEMENT. XI (RÉSULTAT NET, income statement) must equal CJ (Résultat
    net de l'exercice, carried inside equity on the liabilities side).

    Watch out, and this is the interesting part: your own README already
    records that XI/XG carry a sign ambiguity, because the income statement's
    ``+``/``-`` operator column is not yet interpreted. So this check will
    sometimes fail on a *correctly* extracted document. That is a finding,
    not a bug — it belongs in the failure typology of dossier §19.3, and
    resolving the sign column is the prerequisite.

    Start with the strict equality. When it fires on a real document, look at
    the operator column before touching the check.
    """
    raise NotImplementedError("CHK003 — see the docstring, then delete this line")


# ==========================================================================
# CHK004 — YOUR EXERCISE (blocking)
# ==========================================================================
def check_completeness(statement: FinancialStatement) -> CheckOutcome:
    """Every item the five core ratios need is present.

    TO IMPLEMENT, and it is the shortest of the three: compare
    ``statement.codes()`` against ``REQUIRED_CODES`` (imported above) and
    fail if anything is missing, listing exactly what.

    ``gap`` here is the *count* of missing items. A check's gap does not have
    to be a monetary amount — it has to be a number that means something.
    """
    raise NotImplementedError("CHK004 — see the docstring, then delete this line")


# ==========================================================================
REGISTRY: tuple[Check, ...] = (
    Check("CHK001", "Balance sheet equilibrium", BLOCKING, check_balance_equilibrium),
    Check("CHK002", "Subtotal consistency", BLOCKING, check_subtotal_consistency),
    Check("CHK003", "Net income consistency", BLOCKING, check_net_income_consistency),
    Check("CHK004", "Completeness of required items", BLOCKING, check_completeness),
    Check("CHK005", "Plausible signs", WARNING, check_plausible_signs),
)


def run_all(statement: FinancialStatement) -> list[CheckOutcome]:
    """Run every registered check and return every outcome.

    A check that is not yet implemented is reported as a WARNING saying so,
    instead of crashing the extraction. The chain must keep running while you
    are still writing CHK002 — otherwise nothing downstream can be tested and
    you are blocked on your own unfinished work.

    Remove this tolerance once the five are implemented: by then, a check
    that raises is a real defect and should stop the run loudly.
    """
    outcomes: list[CheckOutcome] = []
    for check in REGISTRY:
        try:
            outcomes.append(check.run(statement))
        except NotImplementedError:
            outcomes.append(
                CheckOutcome(
                    code=check.code,
                    label=check.label,
                    severity=WARNING,
                    passed=True,
                    message="not implemented yet",
                )
            )
    return outcomes


def has_blocking_failure(outcomes: list[CheckOutcome]) -> bool:
    """BR-12 / FR-13 — may this dataset be validated?"""
    return any(outcome.is_blocking_failure for outcome in outcomes)
