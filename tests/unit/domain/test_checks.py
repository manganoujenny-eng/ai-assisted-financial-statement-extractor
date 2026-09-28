"""The consistency checks.

CHK001 and CHK005 are implemented and their tests pass. CHK002, CHK003 and
CHK004 are your exercises: their tests are written and skipped. Delete the
``@pytest.mark.skip`` line, run the test, watch it fail, then make it pass.

That order matters. A test written after the code tends to describe what the
code happens to do; a test written first describes what the code should do.
These are written first — for you.
"""

import pytest

from app.domain.checks import (
    BLOCKING,
    WARNING,
    check_balance_equilibrium,
    check_completeness,
    check_net_income_consistency,
    check_plausible_signs,
    check_subtotal_consistency,
    has_blocking_failure,
    run_all,
)
from app.domain.statement import FinancialStatement


class TestCHK001:
    def test_passes_when_the_balance_sheet_balances(self, balanced):
        outcome = check_balance_equilibrium(balanced)
        assert outcome.passed
        assert outcome.gap == 0
        assert outcome.severity == BLOCKING

    def test_fails_and_quantifies_the_gap(self, unbalanced):
        outcome = check_balance_equilibrium(unbalanced)
        assert not outcome.passed
        # The gap is the whole point: "out by 13" is a diagnosis,
        # "inconsistent" is only an alarm.
        assert outcome.gap == -13
        assert outcome.is_blocking_failure

    def test_is_not_evaluated_when_an_item_is_missing(self):
        statement = FinancialStatement.from_dict({"BZ": 100})
        outcome = check_balance_equilibrium(statement)
        assert outcome.passed  # not failed: absence is CHK004's business
        assert "missing" in outcome.message


class TestCHK005:
    def test_passes_on_plausible_signs(self, balanced):
        assert check_plausible_signs(balanced).passed

    def test_warns_without_blocking_on_a_negative_revenue(self, balanced):
        suspect = balanced.with_override("XB", -1)
        outcome = check_plausible_signs(suspect)
        assert not outcome.passed
        assert outcome.severity == WARNING
        # A warning must never stop a validation. BR-08.
        assert not outcome.is_blocking_failure


# ==========================================================================
@pytest.mark.skip(reason="EXERCISE: implement check_subtotal_consistency (BR-06)")
class TestCHK002:
    def test_passes_when_both_sides_add_up(self, balanced):
        outcome = check_subtotal_consistency(balanced)
        assert outcome.passed
        assert outcome.gap == 0

    def test_fails_when_the_asset_subtotals_do_not_add_up(self, balanced):
        # BK is inflated by 1 000 but BZ is left alone: the sides still each
        # show the same total, so CHK001 passes and only CHK002 catches this.
        broken = balanced.with_override("BK", 6_747_235)
        outcome = check_subtotal_consistency(broken)
        assert not outcome.passed
        assert abs(outcome.gap) == 1000
        assert "asset" in outcome.message.lower()

    def test_fails_when_the_liability_subtotals_do_not_add_up(self, balanced):
        broken = balanced.with_override("DP", 3_747_235)
        outcome = check_subtotal_consistency(broken)
        assert not outcome.passed
        assert "liabilit" in outcome.message.lower()

    def test_treats_an_absent_translation_difference_as_zero(self, balanced):
        # BU and DV are routinely absent from a real package. Their absence
        # must not make the check unevaluable.
        without = FinancialStatement.from_dict(
            {k: v for k, v in balanced.to_dict().items() if k not in ("BU", "DV")}
        )
        assert check_subtotal_consistency(without).passed


@pytest.mark.skip(reason="EXERCISE: implement check_net_income_consistency (BR-07)")
class TestCHK003:
    def test_passes_when_xi_equals_cj(self, balanced):
        assert check_net_income_consistency(balanced).passed

    def test_fails_when_they_disagree(self, balanced):
        broken = balanced.with_override("CJ", 999_999)
        outcome = check_net_income_consistency(broken)
        assert not outcome.passed
        assert outcome.gap == 1

    def test_catches_the_sign_error_your_readme_documents(self, balanced):
        # A loss read as a gain: XI positive where CJ is negative. This is
        # the exact failure mode the unresolved +/- operator column produces.
        broken = balanced.with_override("CJ", -1_000_000)
        assert not check_net_income_consistency(broken).passed


@pytest.mark.skip(reason="EXERCISE: implement check_completeness")
class TestCHK004:
    def test_passes_when_every_required_item_is_present(self, balanced):
        assert check_completeness(balanced).passed

    def test_fails_and_names_what_is_missing(self, balanced):
        partial = FinancialStatement.from_dict(
            {k: v for k, v in balanced.to_dict().items() if k not in ("XB", "CP")}
        )
        outcome = check_completeness(partial)
        assert not outcome.passed
        assert outcome.gap == 2
        assert "XB" in outcome.message and "CP" in outcome.message


# ==========================================================================
class TestRunAll:
    def test_survives_the_unimplemented_checks(self, balanced):
        # While CHK002-004 are still exercises, the chain must keep running:
        # nothing downstream can be tested if an unfinished check crashes it.
        outcomes = run_all(balanced)
        assert len(outcomes) == 5

    def test_a_broken_balance_sheet_blocks_validation(self, unbalanced):
        assert has_blocking_failure(run_all(unbalanced))

    def test_a_sound_balance_sheet_does_not(self, balanced):
        assert not has_blocking_failure(run_all(balanced))
