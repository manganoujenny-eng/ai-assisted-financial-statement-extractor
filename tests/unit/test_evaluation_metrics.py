"""Week 7 — the measurements of dossier §18.1 (exercises 16 to 19).

Every test builds an "extraction" by changing the ground truth on purpose,
so the expected answer can be worked out by hand. ``balanced`` (conftest.py)
is the ground truth: it balances, and every check passes on it.
"""

from decimal import Decimal

from app.domain.statement import FinancialStatement
from app.services.evaluation_service import EvaluationService

service = EvaluationService()


def _without(statement: FinancialStatement, code: str) -> FinancialStatement:
    amounts = {k: v for k, v in statement.amounts.items() if k != code}
    return FinancialStatement(amounts=amounts, fiscal_year=statement.fiscal_year)


# --- 16. Silent false positives ------------------------------------------
class TestSilentFalsePositives:
    def test_a_perfect_extraction_has_none(self, balanced):
        assert service.silent_false_positives(balanced, balanced) == []

    def test_a_wrong_revenue_passes_every_check_and_is_silent(self, balanced):
        # XB is in no balance-sheet identity: nothing can catch it.
        extracted = balanced.with_override("XB", 18_000_000)
        assert service.silent_false_positives(extracted, balanced) == ["XB"]

    def test_an_error_a_blocking_check_catches_is_not_silent(self, balanced):
        # BZ alone breaks the equilibrium: CHK001 blocks validation.
        extracted = balanced.with_override("BZ", 11_000_000)
        assert service.silent_false_positives(extracted, balanced) == []

    def test_once_a_check_blocks_every_error_of_the_statement_is_seen(self, balanced):
        # The analyst must open the case to fix BZ, so the XB error is no
        # longer silent either: it sits in a statement under review.
        extracted = balanced.with_override("BZ", 11_000_000).with_override("XB", 1)
        assert service.silent_false_positives(extracted, balanced) == []

    def test_compensating_errors_are_both_silent(self, balanced):
        # Two errors that cancel out: BK +100 and BT -100 keep BZ right.
        extracted = balanced.with_override("BK", 6_746_335).with_override("BT", 499_900)
        assert service.silent_false_positives(extracted, balanced) == ["BK", "BT"]

    def test_a_missing_item_is_not_a_wrong_value(self, balanced):
        # Missing XB: CHK004 blocks, and the ratio shows NOT_COMPUTABLE.
        assert service.silent_false_positives(_without(balanced, "XB"), balanced) == []


# --- 17. Field-level accuracy --------------------------------------------
class TestFieldAccuracy:
    def test_a_perfect_extraction_scores_one(self, balanced):
        assert service.field_accuracy(balanced, balanced) == Decimal(1)

    def test_one_wrong_field_out_of_fifteen(self, balanced):
        extracted = balanced.with_override("XB", 18_000_000)
        assert service.field_accuracy(extracted, balanced) == Decimal(14) / Decimal(15)

    def test_a_missing_field_counts_as_an_error(self, balanced):
        assert service.field_accuracy(_without(balanced, "XB"), balanced) == Decimal(14) / Decimal(15)

    def test_exactly_means_exactly(self, balanced):
        # One franc out on 20 million is still a wrong field.
        extracted = balanced.with_override("XB", 20_000_001)
        assert service.field_accuracy(extracted, balanced) < 1

    def test_items_the_truth_does_not_cover_are_not_judged(self, balanced):
        # The ground truth covers the required items only; an extra line the
        # extractor also read cannot be scored without a reference value.
        extracted = balanced.with_override("AD", 123)
        assert service.field_accuracy(extracted, balanced) == Decimal(1)


# --- 18. Ratio-level accuracy --------------------------------------------
class TestRatioAccuracy:
    def test_a_perfect_extraction_scores_one(self, balanced):
        assert service.ratio_accuracy(balanced, balanced) == Decimal(1)

    def test_a_ten_percent_revenue_error_breaks_only_the_net_margin(self, balanced):
        extracted = balanced.with_override("XB", 22_000_000)
        assert service.ratio_accuracy(extracted, balanced) == Decimal(4) / Decimal(5)

    def test_less_than_one_percent_away_is_still_right(self, balanced):
        # XB +0.5 %: R4 moves by about 0.5 %, inside the 1 % tolerance.
        extracted = balanced.with_override("XB", 20_100_000)
        assert service.ratio_accuracy(extracted, balanced) == Decimal(1)

    def test_not_computable_on_both_sides_agrees(self, balanced):
        truth = _without(balanced, "XB")
        assert service.ratio_accuracy(truth, truth) == Decimal(1)

    def test_computable_on_one_side_only_is_an_error(self, balanced):
        # The extraction lost XB: R4 is NOT_COMPUTABLE, the truth has a value.
        assert service.ratio_accuracy(_without(balanced, "XB"), balanced) == Decimal(4) / Decimal(5)


# --- 19. Amplification coefficient ---------------------------------------
class TestAmplification:
    def test_ratio_error_rate_over_field_error_rate(self):
        # 10 % of fields wrong, 40 % of ratios wrong: the chain amplifies x4.
        assert service.amplification_coefficient(Decimal("0.9"), Decimal("0.6")) == Decimal(4)

    def test_below_one_means_the_chain_absorbs(self):
        assert service.amplification_coefficient(Decimal("0.8"), Decimal("0.9")) == Decimal("0.5")

    def test_a_perfect_extraction_has_no_amplification(self):
        assert service.amplification_coefficient(Decimal(1), Decimal(1)) is None

    def test_on_a_real_pair(self, balanced):
        # One wrong field in 15 (XB), one wrong ratio in 5 (R4): (1/5)/(1/15) = 3.
        extracted = balanced.with_override("XB", 22_000_000)
        fields = service.field_accuracy(extracted, balanced)
        ratios = service.ratio_accuracy(extracted, balanced)
        assert service.amplification_coefficient(fields, ratios) == Decimal(3)


# --- Measured on the unrounded values -----------------------------------
class TestMeasuredUnrounded:
    """BR-15 rounds a ratio to one decimal FOR DISPLAY. The evaluation must
    not measure the display: R2 = 0.714 and R2 = 0.704 both show 0.7."""

    def test_the_engine_keeps_the_exact_value_next_to_the_shown_one(self, balanced):
        from app.domain.ratios import compute_all

        r2 = next(r for r in compute_all(balanced) if r.code == "R2")
        assert r2.value == Decimal("0.7")  # what people see
        assert r2.exact > Decimal("0.714") and r2.exact < Decimal("0.715")

    def test_an_error_hidden_by_the_rounding_is_still_an_error(self, balanced):
        # DD +5 %: R2 goes from 0.714 to 0.704, 1.4 % away (> 1 % tolerance),
        # though both show 0.7. Only R2 and R3 use DD; R3 moves too.
        extracted = balanced.with_override("DD", 2_100_000)
        assert service.ratio_accuracy(extracted, balanced) == Decimal(3) / Decimal(5)

    def test_a_small_error_moves_the_sensitivity_matrix(self, balanced):
        # DD +1 % leaves the displayed R2 at 0.7; the measured R2 still moves.
        matrix = service.sensitivity_matrix(
            balanced, items=("DD",), perturbations=(Decimal("0.01"),)
        )
        r2 = next(c for c in matrix.cells if c.ratio_code == "R2")
        assert r2.relative_deviation > 0