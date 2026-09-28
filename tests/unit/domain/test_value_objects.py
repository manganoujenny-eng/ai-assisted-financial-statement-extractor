"""Amount and ItemCode.

These tests are the specification of the value objects. Read them before
reading ``value_objects.py`` — a good test file tells you what the code is
*for*, which a docstring only claims.
"""

from decimal import Decimal

import pytest

from app.domain.value_objects import Amount, ItemCode, round_ratio


class TestAmount:
    def test_accepts_the_syscohada_thousands_separator(self):
        assert Amount("1 234 567").value == Decimal("1234567.00")

    def test_a_bare_dash_is_nil(self):
        # SYSCOHADA prints "-" for a nil line. Helena's normaliser already
        # handles it; the value object now guarantees it everywhere.
        assert Amount("-").is_zero()
        assert Amount("").is_zero()

    def test_refuses_a_float(self):
        # The point of the whole class. 0.1 + 0.2 != 0.3 in binary floating
        # point, and on a balance sheet that inexactness is visible.
        with pytest.raises(TypeError):
            Amount(0.1)

    def test_refuses_nonsense(self):
        with pytest.raises(ValueError):
            Amount("about three million")

    def test_addition_stays_exact(self):
        total = Amount("0.10") + Amount("0.20")
        assert total.value == Decimal("0.30")

    def test_dividing_two_amounts_gives_a_plain_number(self):
        # Francs over francs is dimensionless. If this ever returns an
        # Amount, a ratio has been mistaken for money.
        result = Amount(10) / Amount(4)
        assert result == Decimal("2.5")
        assert not isinstance(result, Amount)

    def test_division_by_zero_raises_rather_than_returning_infinity(self):
        with pytest.raises(ZeroDivisionError):
            Amount(10) / Amount(0)

    def test_equality_ignores_how_it_was_written(self):
        assert Amount("1 000") == Amount(1000) == Amount(Decimal("1000.00"))

    def test_display_uses_the_local_convention(self):
        assert str(Amount("1234567.5")) == "1 234 567,50"


class TestItemCode:
    def test_normalises_case_and_spacing(self):
        assert ItemCode(" bk ") == ItemCode("BK")

    @pytest.mark.parametrize("bad", ["B1", "BKK", "B", "", "b-k"])
    def test_refuses_anything_that_is_not_two_letters(self, bad):
        with pytest.raises(ValueError):
            ItemCode(bad)


def test_ratios_are_rounded_to_one_decimal():
    # BR-15. Half-up, not banker's rounding: an accountant reading 1.75
    # expects 1.8, and Python's default would give 1.8 here but 2.4 for 2.45.
    assert round_ratio(Decimal("1.75")) == Decimal("1.8")
    assert round_ratio(Decimal("2.45")) == Decimal("2.5")
