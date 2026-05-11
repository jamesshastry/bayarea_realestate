"""Unit tests for ``finance.cost_of_waiting.compute``.

The grid is 3 (appreciation) × 3 (rate) cells. Tests cover:
- Grid shape and ordering.
- Sign conventions (waiting in an appreciating market costs money).
- Break-even rate logic.
- Determinism + Decimal cleanliness.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from finance import tax_rules
from finance._types import AreaContext, Buyer, County, WaitParams
from finance.cost_of_waiting import cost_of_waiting


def _buyer() -> Buyer:
    return Buyer(
        annual_income=Decimal("300_000"),
        monthly_debts=Decimal("0"),
        down_payment=Decimal("200_000"),
        rate=Decimal("0.0675"),
        term_years=30,
    )


def _area_ctx(*, rate: Decimal = Decimal("0.0675")) -> AreaContext:
    return AreaContext(
        county=County.ALAMEDA,
        property_tax_rate=tax_rules.property_tax_rate(County.ALAMEDA),
        mello_roos_annual=Decimal("0"),
        hoa_monthly=Decimal("0"),
        insurance_annual=Decimal("3500"),
        wildfire_surcharge_multiplier=Decimal("1.0"),
        rate=rate,
        term_years=30,
        down_payment=Decimal("200_000"),
    )


def _params(
    *,
    target_price: Decimal = Decimal("1_200_000"),
    months: int = 12,
    current_rent: Decimal = Decimal("3500"),
    current_rate: Decimal = Decimal("0.0675"),
) -> WaitParams:
    return WaitParams(
        target_price=target_price,
        wait_horizon_months=months,
        current_rate=current_rate,
        current_rent=current_rent,
        area_ctx=_area_ctx(rate=current_rate),
    )


def test_grid_is_3x3() -> None:
    grid = cost_of_waiting(_buyer(), "alameda::fremont", _params())
    assert len(grid.cells) == 3
    for row in grid.cells:
        assert len(row) == 3


def test_grid_cell_ordering_is_appreciation_outer_rate_inner() -> None:
    """Outer index = appreciation scenario, inner = rate scenario.

    Appreciation defaults are (-2%, +3%, +6%); rate defaults are
    (-50bp, flat, +50bp). Verify the cell at [0][2] is (low appreciation
    × high rate) and [2][0] is (high appreciation × rate drop).
    """

    grid = cost_of_waiting(_buyer(), "alameda::fremont", _params())
    assert grid.cells[0][0].appreciation_annual == Decimal("-0.02")
    assert grid.cells[0][2].rate_change == Decimal("0.005")
    assert grid.cells[2][0].appreciation_annual == Decimal("0.06")
    assert grid.cells[2][0].rate_change == Decimal("-0.005")


def test_appreciation_change_dollars_sign() -> None:
    """Positive annual appreciation → positive ``appreciation_change_dollars``."""

    grid = cost_of_waiting(_buyer(), "x", _params())
    # +6% row: positive change.
    assert grid.cells[2][0].appreciation_change_dollars > Decimal("0")
    # -2% row: negative change.
    assert grid.cells[0][0].appreciation_change_dollars < Decimal("0")


def test_rent_paid_during_wait_constant_across_grid() -> None:
    grid = cost_of_waiting(_buyer(), "x", _params(months=6, current_rent=Decimal("4000")))
    expected = Decimal("4000") * Decimal("6")
    for row in grid.cells:
        for cell in row:
            assert cell.rent_paid_during_wait == expected


def test_monthly_payment_now_constant_across_grid() -> None:
    grid = cost_of_waiting(_buyer(), "x", _params())
    first = grid.cells[0][0].monthly_payment_now
    for row in grid.cells:
        for cell in row:
            assert cell.monthly_payment_now == first


def test_rate_drop_lowers_monthly_payment_later() -> None:
    grid = cost_of_waiting(_buyer(), "x", _params())
    # Within a single appreciation row, the rate-drop column should
    # have a lower monthly_payment_later than the rate-rise column.
    for row in grid.cells:
        assert row[0].monthly_payment_later < row[2].monthly_payment_later


def test_high_appreciation_makes_waiting_more_expensive() -> None:
    """Holding rate flat, comparing -2% vs +6%: waiting in the
    appreciating market should yield a larger ``net_dollar_impact``."""

    grid = cost_of_waiting(_buyer(), "x", _params())
    # Middle column (flat rate scenario).
    low_app = grid.cells[0][1].net_dollar_impact
    high_app = grid.cells[2][1].net_dollar_impact
    assert high_app > low_app


def test_break_even_rate_drop_zero_when_waiting_already_pays() -> None:
    """If appreciation is negative enough that waiting saves money even
    at zero rate change, ``break_even_rate_drop`` should be 0."""

    # Use a buyer with no rent (rent_paid term won't dominate) and very
    # negative appreciation in the 3-month horizon.
    params = _params(
        months=3,
        current_rent=Decimal("0"),
        target_price=Decimal("1_500_000"),
    )
    grid = cost_of_waiting(_buyer(), "x", params)
    # The -2% appreciation column at flat rate.
    cell = grid.cells[0][1]
    if cell.net_dollar_impact <= 0:
        assert cell.break_even_rate_drop == Decimal("0")


def test_break_even_rate_drop_positive_when_waiting_costs() -> None:
    grid = cost_of_waiting(_buyer(), "x", _params())
    # +6% × +50bp: definitely costs money to wait.
    cell = grid.cells[2][2]
    assert cell.net_dollar_impact > 0
    assert cell.break_even_rate_drop > Decimal("0")


def test_break_even_rate_drop_capped_at_5pp() -> None:
    """Break-even is capped at 5pp; we never return values above that."""

    grid = cost_of_waiting(_buyer(), "x", _params())
    for row in grid.cells:
        for cell in row:
            assert cell.break_even_rate_drop <= Decimal("0.05")


def test_compute_is_deterministic() -> None:
    a = cost_of_waiting(_buyer(), "x", _params())
    b = cost_of_waiting(_buyer(), "x", _params())
    assert a == b


def test_compute_rejects_zero_target_price() -> None:
    params = _params(target_price=Decimal("0"))
    with pytest.raises(ValueError, match="target_price"):
        cost_of_waiting(_buyer(), "x", params)


def test_compute_rejects_zero_horizon() -> None:
    params = _params(months=0)
    with pytest.raises(ValueError, match="wait_horizon_months"):
        cost_of_waiting(_buyer(), "x", params)


def test_compute_rejects_zero_term() -> None:
    bad_buyer = Buyer(
        annual_income=Decimal("100_000"),
        monthly_debts=Decimal("0"),
        down_payment=Decimal("50_000"),
        rate=Decimal("0.05"),
        term_years=0,
    )
    with pytest.raises(ValueError, match="term_years"):
        cost_of_waiting(bad_buyer, "x", _params())


def test_grid_top_level_fields() -> None:
    params = _params(target_price=Decimal("950_000"), months=24, current_rate=Decimal("0.07"))
    grid = cost_of_waiting(_buyer(), "x", params)
    assert grid.target_price == Decimal("950_000")
    assert grid.wait_horizon_months == 24
    assert grid.current_rate == Decimal("0.07")


@settings(max_examples=20, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    target=st.decimals(min_value=Decimal("400_000"), max_value=Decimal("3_000_000"), places=0),
    months=st.sampled_from([3, 6, 12, 24]),
    rent=st.decimals(min_value=Decimal("0"), max_value=Decimal("10_000"), places=0),
)
def test_grid_shape_invariant_across_random_inputs(
    target: Decimal, months: int, rent: Decimal
) -> None:
    params = _params(target_price=target, months=months, current_rent=rent)
    grid = cost_of_waiting(_buyer(), "x", params)
    assert len(grid.cells) == 3
    for row in grid.cells:
        assert len(row) == 3
        for cell in row:
            # Each cell's monthly_payment_now equals the others (constant)
            assert cell.monthly_payment_now == grid.cells[0][0].monthly_payment_now
            # Rent paid is the constant.
            assert cell.rent_paid_during_wait == rent * Decimal(months)
