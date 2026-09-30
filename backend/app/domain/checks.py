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
from email import message
from typing import Callable

from jinja2.utils import missing

from .statement import FinancialStatement
from .syscohada import REQUIRED_CODES
from .value_objects import Amount

BLOCKING = "BLOCKING"
WARNING = "WARNING"


@dataclass(frozen=True)
class CheckOutcome: ##DEFINES THE RESULT OF THE CHECKS
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
# CHK002 — worked example of a BLOCKING check
# ==========================================================================
def check_subtotal_consistency(statement: FinancialStatement) -> CheckOutcome:
    missing = statement.missing(
        ["AZ", "BK" , "BT" , "BZ" , "CP" , "DD" , "DP" , "DT" ,"DZ" ]
    )
    if missing:
        return _skipped(
            "CHK002",
            "Subtotal consistency" ,
            BLOCKING,
            missing,
        )
    #if BU and DV are missing chang it in to value zero
    bu = statement.get("BU")
    dv = statement.get("DV")

    asset_total = statement["AZ"] + statement["BK"] + statement["BT"]
    if bu is not None:
        asset_total += bu

    liability_total = statement["CP"] + statement["DD"] + statement["DP"] + statement["DT"]
    if dv is not None:
        liability_total += dv

    asset_gap = (asset_total - statement["BZ"]).value
    liability_gap = (liability_total - statement["DZ"]).value

    if asset_gap == 0 and liability_gap == 0:
        return CheckOutcome(
            code="CHK002",
            label="Subtotal consistency",
            severity=WARNING,
            passed=True,
            gap=0,
            message="asset and liability subtotal consistency",
            items_used=(
                "AZ", "BK", "BT", "BU", "BZ",
                "CP", "DD", "DP", "DT", "DV", "DZ",
            ),
        )
    if asset_gap != 0 and liability_gap != 0:
        message = (
            f"asset gap of {Amount(asset_gap)}; "
            f"liability gap of {Amount(liability_gap)}; "
        )
    elif asset_gap != 0:
        message = (
            f"asset subtotal is inconsitency , "
            f"gap of {Amount(asset_gap)}"
        )

    else:
        message = (
            f"liability subtotal is inconsistent "
            f"gap of {Amount(liability_gap)}"
        )

    gap = asset_gap if abs(asset_gap) >= abs(liability_gap) else liability_gap

    return CheckOutcome(
        code="CHK002",
        label="Subtotal consistency",
        severity=BLOCKING,
        passed= False,
        gap=gap,
        message=message,
        items_used=(
            "AZ", "BK", "BT", "BU", "BZ",
            "CP", "DD", "DP", "DT", "DV", "DZ",
        ),
    )

# ==========================================================================
# CHK003 — worked example of a BLOCKING check
# ==========================================================================
def check_net_income_consistency(statement: FinancialStatement) -> CheckOutcome:
    missing = statement.missing(["XI" , "CJ"])

    if missing:
        return _skipped(
            "CHK003",
            "Net income consistency",
            BLOCKING,
            missing,
        )
    income_statement_result = statement["XI"]
    balance_sheet_result = statement["CJ"]

    gap = (income_statement_result - balance_sheet_result).value
    passed = gap == 0

    return CheckOutcome(
        code="CHK003",
        label="Net income consistency",
        severity=BLOCKING,
        passed=passed,
        gap=gap,
        message=(
            "XI - CJ"
            if passed
            else (
            f"XI ({income_statement_result}) ≠ "
            f"CJ ({balance_sheet_result}), "
            f"gap of {Amount(gap)}"
        )
    ),
    items_used = ("XI" , "CJ")
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
# CHK004 — worked example of a BLOCKING check
# ==========================================================================
def check_completeness(statement: FinancialStatement) -> CheckOutcome:
    missing = statement.missing(REQUIRED_CODES)

    if not  missing:
        return CheckOutcome(
            code="CHK004",
            label="Completeness",
            severity=BLOCKING,
            passed=True,
            gap=0 ,
            message= "all required items are present " ,
            items_used = REQUIRED_CODES,
        )
    return CheckOutcome(
        code="CHK004",
        label="Completeness",
        severity=BLOCKING,
        passed=False,
        gap=len(missing),
        message= f"missing required items: {', '.join(missing)}",
        items_used= tuple(missing)
    )



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
