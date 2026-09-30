"""The ratio engine and the five core ratios.

R1 is implemented; its tests pass. R2 to R5 are skipped exercises. Un-skip
one class at a time and work through it — the expected values below were
computed by hand from the fixture, exactly as the ground truth of dossier
§19.1 is computed by hand from a real package.
"""

from decimal import Decimal

import pytest

from app.domain.ratios import (
    COMPUTED,
    NOT_COMPUTABLE,
    REGISTRY,
    compute_all,
    compute_one,
    definition_of,
)
from app.domain.statement import FinancialStatement


def compute(code: str, statement: FinancialStatement):
    return compute_one(definition_of(code), statement)


class TestR1:
    def test_computes_the_expected_value(self, balanced):
        # (BK 6 746 235 + BT 500 000) / (DP 3 746 235 + DT 500 000)
        # = 7 246 235 / 4 246 235 = 1.7065... -> 1.7 (BR-15, one decimal)
        result = compute("R1", balanced)
        assert result.status == COMPUTED
        assert result.value == Decimal("1.7")
        assert result.unit == "x"

    def test_keeps_the_items_it_used(self, balanced):
        # BR-04. This is what makes the propagation analysis computable
        # after the fact, without replaying the chain.
        result = compute("R1", balanced)
        assert set(result.items_used) == {"BK", "BT", "DP", "DT"}
        assert result.inputs["BK"] == "6746235.00"

    def test_a_missing_item_is_a_reason_not_a_zero(self, balanced):
        # BR-02. The tempting bug is to treat an absent BT as 0 and carry on:
        # the ratio would then be computed, plausible, and wrong.
        without_bt = FinancialStatement.from_dict(
            {k: v for k, v in balanced.to_dict().items() if k != "BT"}
        )
        result = compute("R1", without_bt)
        assert result.status == NOT_COMPUTABLE
        assert result.value is None
        assert "BT" in result.reason

    def test_a_zero_denominator_is_a_reason_not_a_crash(self, balanced):
        # BR-03. A company with no current liabilities at all is unusual but
        # not impossible, and it must not produce a 500.
        no_liabilities = balanced.with_override("DP", 0).with_override("DT", 0)
        result = compute("R1", no_liabilities)
        assert result.status == NOT_COMPUTABLE
        assert result.reason == "zero denominator"



class TestR2:
    def test_computes_the_expected_value(self, balanced):
        # CP 5 000 000 / (CP 5 000 000 + DD 2 000 000) = 0.714... -> 0.7
        result = compute("R2", balanced)
        assert result.status == COMPUTED
        assert result.value == Decimal("0.7")

    def test_declares_its_required_items(self):
        assert set(definition_of("R2").required_items) == {"CP", "DD"}

    def test_zero_equity_and_zero_debt_is_not_computable(self, balanced):
        empty = balanced.with_override("CP", 0).with_override("DD", 0)
        assert compute("R2", empty).status == NOT_COMPUTABLE



class TestR3:
    def test_computes_the_expected_value(self, balanced):
        # (CP 5 000 000 + DD 2 000 000) / AZ 4 000 000 = 1.75 -> 1.8
        result = compute("R3", balanced)
        assert result.status == COMPUTED
        assert result.value == Decimal("1.8")

    def test_no_fixed_assets_at_all_is_not_computable(self, balanced):
        assert compute("R3", balanced.with_override("AZ", 0)).status == NOT_COMPUTABLE



class TestR4:
    def test_computes_a_percentage(self, balanced):
        # XI 1 000 000 / XB 20 000 000 x 100 = 5.0 %
        result = compute("R4", balanced)
        assert result.status == COMPUTED
        assert result.value == Decimal("5.0")
        assert result.unit == "%"

    def test_a_loss_gives_a_negative_margin(self, balanced):
        # It must stay negative. A margin that comes out positive on a loss
        # is the silent false positive of dossier §18.1.
        loss = balanced.with_override("XI", -2_000_000)
        assert compute("R4", loss).value == Decimal("-10.0")



class TestR5:
    def test_computes_a_percentage(self, balanced):
        # XI 1 000 000 / CP 5 000 000 x 100 = 20.0 %
        assert compute("R5", balanced).value == Decimal("20.0")

    def test_negative_equity(self, balanced):
        """Your design decision. Adjust this test to the option you chose.

        As written it expects option (b) of the module docstring: refuse to
        return a number that would read as a splendid performance for an
        insolvent company. If you chose option (a), change the assertion —
        and write down why in the thesis.
        """
        insolvent = balanced.with_override("CP", -1_000_000)
        result = compute("R5", insolvent)
        assert result.status == NOT_COMPUTABLE
        assert "negative equity" in (result.reason or "")


class TestTheEngineItself:
    def test_knows_the_five_core_ratios(self):
        assert sorted(REGISTRY) == ["R1", "R2", "R3", "R4", "R5"]

    def test_computes_the_whole_set_without_raising(self, balanced):
        # Even while R2..R5 are unwritten: an unimplemented ratio is reported
        # as NOT_COMPUTABLE, so the dashboard keeps working while you go
        # through them one by one.
        results = compute_all(balanced)
        assert len(results) == 5

    def test_is_reproducible(self, balanced):
        # NFR-02. Run it twice, get the same thing — no randomness, no clock,
        # no network. This is what makes the sensitivity analysis meaningful.
        assert [r.value for r in compute_all(balanced)] == [
            r.value for r in compute_all(balanced)
        ]

    def test_an_unknown_ratio_says_so_clearly(self):
        with pytest.raises(KeyError, match="R9"):
            definition_of("R9")
