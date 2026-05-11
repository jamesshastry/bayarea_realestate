"""Unit + Hypothesis property tests for ``finance.affordability``.

Property invariants asserted (per the task brief):
- Monotonicity: more income → ``comfortable`` and ``stretch`` never
  decrease (with everything else held constant).
- Conservation: ``MonthlyCost`` components sum to ``total``.
- Determinism: same inputs → same outputs.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from finance import tax_rules
from finance._types import AreaContext, Buyer, County, MarketContext
from finance.affordability import affordability, monthly_cost


def _bay_area_market() -> MarketContext:
    return MarketContext(county=County.ALAMEDA)


def _bay_area_area_ctx(
    *,
    rate: Decimal = Decimal("0.0675"),
    down: Decimal = Decimal("150000"),
) -> AreaContext:
    return AreaContext(
        county=County.ALAMEDA,
        property_tax_rate=tax_rules.property_tax_rate(County.ALAMEDA),
        mello_roos_annual=Decimal("0"),
        hoa_monthly=Decimal("0"),
        insurance_annual=Decimal("3500"),
        wildfire_surcharge_multiplier=Decimal("1.0"),
        rate=rate,
        term_years=30,
        down_payment=down,
    )


# ---------------------------------------------------------------------------
# monthly_cost — unit + property tests
# ---------------------------------------------------------------------------


def test_monthly_cost_components_sum_to_total_unit() -> None:
    area = _bay_area_area_ctx()
    cost = monthly_cost(Decimal("1_200_000"), area)
    total = cost.p_and_i + cost.tax + cost.mello + cost.hoa + cost.insurance + cost.pmi
    assert total == cost.total


def test_monthly_cost_pmi_zero_when_down_at_least_20_pct() -> None:
    area = _bay_area_area_ctx(down=Decimal("400000"))  # 20% on $2M
    cost = monthly_cost(Decimal("2_000_000"), area)
    assert cost.pmi == Decimal("0")


def test_monthly_cost_pmi_applied_when_down_below_20_pct() -> None:
    area = _bay_area_area_ctx(down=Decimal("100000"))  # 10% on $1M
    cost = monthly_cost(Decimal("1_000_000"), area)
    assert cost.pmi > Decimal("0")


def test_monthly_cost_zero_loan_when_price_below_down() -> None:
    area = _bay_area_area_ctx(down=Decimal("1_000_000"))
    cost = monthly_cost(Decimal("500_000"), area)
    # P&I is zero, PMI is zero, but tax/insurance still apply.
    assert cost.p_and_i == Decimal("0")
    assert cost.pmi == Decimal("0")
    assert cost.tax > Decimal("0")
    assert cost.insurance > Decimal("0")


def test_monthly_cost_zero_rate_path() -> None:
    """When the rate is exactly 0 the P&I formula degenerates to
    ``loan_amount / n``. We use a tiny loan to avoid the search-bound
    helpers."""

    area = _bay_area_area_ctx(rate=Decimal("0"), down=Decimal("0"))
    cost = monthly_cost(Decimal("3600"), area)
    expected_p_and_i = Decimal("3600") / Decimal(30 * 12)
    assert cost.p_and_i == expected_p_and_i.quantize(Decimal("0.01"))


def test_monthly_cost_rejects_negative_price() -> None:
    area = _bay_area_area_ctx()
    with pytest.raises(ValueError, match="non-negative"):
        monthly_cost(Decimal("-1"), area)


def test_monthly_cost_wildfire_surcharge_applied() -> None:
    """A 2x wildfire surcharge should approximately double the
    monthly-insurance line.

    Note: we compare *near* equality (within $0.02) because
    ``insurance_annual * multiplier / 12`` and ``(insurance_annual / 12)
    * multiplier`` round to subtly different cents due to ROUND_HALF_EVEN
    on the per-month boundary. The TS port reproduces the same rounding
    so its golden output matches Python's exactly.
    """

    base_area = _bay_area_area_ctx()
    surcharged_area = AreaContext(
        county=base_area.county,
        property_tax_rate=base_area.property_tax_rate,
        mello_roos_annual=base_area.mello_roos_annual,
        hoa_monthly=base_area.hoa_monthly,
        insurance_annual=base_area.insurance_annual,
        wildfire_surcharge_multiplier=Decimal("2.0"),
        rate=base_area.rate,
        term_years=base_area.term_years,
        down_payment=base_area.down_payment,
    )
    base = monthly_cost(Decimal("1_000_000"), base_area)
    surcharged = monthly_cost(Decimal("1_000_000"), surcharged_area)
    # Allow 1-cent rounding tolerance.
    assert abs(surcharged.insurance - base.insurance * Decimal("2")) <= Decimal("0.01")
    # Surcharge always increases (or holds) the insurance line.
    assert surcharged.insurance >= base.insurance


@settings(
    max_examples=80,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(
    price=st.decimals(min_value=Decimal("100_000"), max_value=Decimal("5_000_000"), places=2),
    down=st.decimals(min_value=Decimal("0"), max_value=Decimal("500_000"), places=2),
    rate=st.decimals(min_value=Decimal("0.01"), max_value=Decimal("0.12"), places=4),
    term=st.sampled_from([15, 30]),
)
def test_monthly_cost_components_sum_to_total_property(
    price: Decimal, down: Decimal, rate: Decimal, term: int
) -> None:
    """For any reasonable price/down/rate/term, the seven components
    sum exactly to the total."""

    area = AreaContext(
        county=County.ALAMEDA,
        property_tax_rate=tax_rules.property_tax_rate(County.ALAMEDA),
        mello_roos_annual=Decimal("4500"),
        hoa_monthly=Decimal("250"),
        insurance_annual=Decimal("3500"),
        wildfire_surcharge_multiplier=Decimal("1.5"),
        rate=rate,
        term_years=term,
        down_payment=down,
    )
    cost = monthly_cost(price, area)
    summed = cost.p_and_i + cost.tax + cost.mello + cost.hoa + cost.insurance + cost.pmi
    assert summed == cost.total


# ---------------------------------------------------------------------------
# affordability — unit + property tests
# ---------------------------------------------------------------------------


def test_affordability_basic_shape() -> None:
    buyer = Buyer(
        annual_income=Decimal("300_000"),
        monthly_debts=Decimal("0"),
        down_payment=Decimal("150_000"),
        rate=Decimal("0.0675"),
        term_years=30,
    )
    result = affordability(buyer, _bay_area_market())

    # comfortable ≤ stretch (28% < 36%)
    assert result.comfortable <= result.stretch
    # max_by_loan_type has all four loan types
    assert set(result.max_by_loan_type.keys()) == {
        "conforming",
        "high_balance",
        "jumbo",
        "fha",
    }
    # All maxes are non-negative.
    for v in result.max_by_loan_type.values():
        assert v >= Decimal("0")
    # The breakdown invariant on the comfortable point still holds.
    monthly = result.comfortable_monthly
    summed = (
        monthly.p_and_i
        + monthly.tax
        + monthly.mello
        + monthly.hoa
        + monthly.insurance
        + monthly.pmi
    )
    assert summed == monthly.total


def test_affordability_high_income_hits_jumbo_or_dti_ceiling() -> None:
    """A $1M/yr buyer with $500K down should hit the DTI back-end cap or
    the jumbo principal — never cash-on-hand."""

    buyer = Buyer(
        annual_income=Decimal("1_000_000"),
        monthly_debts=Decimal("0"),
        down_payment=Decimal("500_000"),
        rate=Decimal("0.0675"),
        term_years=30,
    )
    result = affordability(buyer, _bay_area_market())
    assert result.binding_constraint != "cash_on_hand"
    # The jumbo ceiling should be the largest entry in the grid.
    assert result.max_by_loan_type["jumbo"] >= result.max_by_loan_type["high_balance"]


def test_affordability_low_cash_binds_on_cash_on_hand() -> None:
    buyer = Buyer(
        annual_income=Decimal("400_000"),
        monthly_debts=Decimal("0"),
        # Tiny down → cash-on-hand binds well below the DTI capacity.
        down_payment=Decimal("5_000"),
        rate=Decimal("0.0675"),
        term_years=30,
    )
    result = affordability(buyer, _bay_area_market())
    assert result.binding_constraint == "cash_on_hand"


def test_affordability_zero_income_returns_zero_prices() -> None:
    buyer = Buyer(
        annual_income=Decimal("0"),
        monthly_debts=Decimal("0"),
        down_payment=Decimal("0"),
        rate=Decimal("0.0675"),
        term_years=30,
    )
    result = affordability(buyer, _bay_area_market())
    assert result.comfortable == Decimal("0")
    assert result.stretch == Decimal("0")


def test_affordability_high_debts_drive_stretch_below_comfortable() -> None:
    buyer = Buyer(
        annual_income=Decimal("200_000"),
        monthly_debts=Decimal("5_500"),  # eats into back-end DTI
        down_payment=Decimal("150_000"),
        rate=Decimal("0.0675"),
        term_years=30,
    )
    result = affordability(buyer, _bay_area_market())
    # The back-end DTI cap is 36% × $16.7K = $6K; minus $5.5K debts = $500
    # for housing — so stretch is much smaller than comfortable.
    assert result.stretch < result.comfortable


def test_affordability_rejects_negative_income() -> None:
    buyer = Buyer(
        annual_income=Decimal("-1"),
        monthly_debts=Decimal("0"),
        down_payment=Decimal("0"),
        rate=Decimal("0.0675"),
        term_years=30,
    )
    with pytest.raises(ValueError, match="annual_income"):
        affordability(buyer, _bay_area_market())


def test_affordability_rejects_negative_down_payment() -> None:
    buyer = Buyer(
        annual_income=Decimal("100_000"),
        monthly_debts=Decimal("0"),
        down_payment=Decimal("-1"),
        rate=Decimal("0.0675"),
        term_years=30,
    )
    with pytest.raises(ValueError, match="down_payment"):
        affordability(buyer, _bay_area_market())


def test_affordability_rejects_negative_monthly_debts() -> None:
    buyer = Buyer(
        annual_income=Decimal("100_000"),
        monthly_debts=Decimal("-1"),
        down_payment=Decimal("0"),
        rate=Decimal("0.0675"),
        term_years=30,
    )
    with pytest.raises(ValueError, match="monthly_debts"):
        affordability(buyer, _bay_area_market())


def test_affordability_rejects_zero_term() -> None:
    buyer = Buyer(
        annual_income=Decimal("100_000"),
        monthly_debts=Decimal("0"),
        down_payment=Decimal("0"),
        rate=Decimal("0.0675"),
        term_years=0,
    )
    with pytest.raises(ValueError, match="term_years"):
        affordability(buyer, _bay_area_market())


def test_affordability_is_deterministic() -> None:
    buyer = Buyer(
        annual_income=Decimal("400_000"),
        monthly_debts=Decimal("500"),
        down_payment=Decimal("200_000"),
        rate=Decimal("0.0625"),
        term_years=30,
    )
    a = affordability(buyer, _bay_area_market())
    b = affordability(buyer, _bay_area_market())
    assert a == b


@settings(
    max_examples=40,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
)
@given(
    income=st.decimals(min_value=Decimal("100_000"), max_value=Decimal("800_000"), places=0),
    bonus=st.decimals(min_value=Decimal("0"), max_value=Decimal("200_000"), places=0),
    down=st.decimals(min_value=Decimal("50_000"), max_value=Decimal("400_000"), places=0),
)
def test_affordability_monotone_in_income(income: Decimal, bonus: Decimal, down: Decimal) -> None:
    """More income → ``comfortable`` and ``stretch`` never decrease."""

    base = Buyer(
        annual_income=income,
        monthly_debts=Decimal("0"),
        down_payment=down,
        rate=Decimal("0.0675"),
        term_years=30,
    )
    boosted = Buyer(
        annual_income=income + bonus,
        monthly_debts=Decimal("0"),
        down_payment=down,
        rate=Decimal("0.0675"),
        term_years=30,
    )
    a = affordability(base, _bay_area_market())
    b = affordability(boosted, _bay_area_market())
    assert b.comfortable >= a.comfortable
    assert b.stretch >= a.stretch
    # Per-loan-type max also monotone.
    for k in a.max_by_loan_type:
        assert b.max_by_loan_type[k] >= a.max_by_loan_type[k]


@settings(
    max_examples=30,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
)
@given(
    extra_debt=st.decimals(min_value=Decimal("0"), max_value=Decimal("3000"), places=0),
)
def test_affordability_monotone_in_monthly_debts(extra_debt: Decimal) -> None:
    """More monthly debts → ``stretch`` never increases (back-end DTI
    binding); ``comfortable`` is unaffected (front-end DTI ignores
    other debts)."""

    base = Buyer(
        annual_income=Decimal("250_000"),
        monthly_debts=Decimal("0"),
        down_payment=Decimal("100_000"),
        rate=Decimal("0.0675"),
        term_years=30,
    )
    debted = Buyer(
        annual_income=base.annual_income,
        monthly_debts=base.monthly_debts + extra_debt,
        down_payment=base.down_payment,
        rate=base.rate,
        term_years=base.term_years,
    )
    a = affordability(base, _bay_area_market())
    b = affordability(debted, _bay_area_market())
    assert b.stretch <= a.stretch
    assert b.comfortable == a.comfortable


def test_affordability_loan_limit_binding_constraint() -> None:
    """Construct a buyer where the high-balance row is the largest of
    the four loan types AND the high-balance ceiling is the binding
    rule (DTI doesn't bind first).

    With $100K down and high income, jumbo cash cap = $100K / 10% = $1M,
    while high-balance row = $100K + $1.21M = $1.31M. Since DTI permits
    both, the overall max equals the high-balance row → "loan_limit".
    """

    buyer = Buyer(
        annual_income=Decimal("700_000"),  # ample DTI capacity
        monthly_debts=Decimal("0"),
        down_payment=Decimal("100_000"),
        rate=Decimal("0.0625"),
        term_years=30,
    )
    result = affordability(buyer, _bay_area_market())
    assert result.binding_constraint == "loan_limit", (
        f"expected loan_limit, got {result.binding_constraint}; "
        f"max_by_loan_type={result.max_by_loan_type}"
    )


def test_affordability_huge_down_payment_floor_exceeds_budget() -> None:
    """When even owning the down-payment-priced home (loan = 0) would
    exceed the buyer's monthly DTI cap, ``_solve_max_price_for_monthly``
    must short-circuit to 0."""

    buyer = Buyer(
        annual_income=Decimal("30_000"),  # tiny income
        monthly_debts=Decimal("0"),
        down_payment=Decimal("5_000_000"),  # huge down → floor tax/insurance alone is unaffordable
        rate=Decimal("0.0675"),
        term_years=30,
    )
    result = affordability(buyer, _bay_area_market())
    assert result.comfortable == Decimal("0")
    assert result.stretch == Decimal("0")


def test_affordability_back_cap_clamps_to_zero_when_debts_exceed_dti() -> None:
    """If monthly_debts exceeds the back-end-DTI capacity, the back-cap
    floors at 0 (so we don't end up with a negative budget)."""

    buyer = Buyer(
        annual_income=Decimal("100_000"),  # ~$8.3K monthly
        monthly_debts=Decimal("20_000"),  # 20K debt > 36% of monthly income
        down_payment=Decimal("100_000"),
        rate=Decimal("0.0675"),
        term_years=30,
    )
    result = affordability(buyer, _bay_area_market())
    assert result.stretch == Decimal("0")


def test_affordability_extremely_large_income_capped_at_search_ceiling() -> None:
    """The binary search has a hard ceiling so we don't return ``Infinity``.

    A buyer with $50M income should still get a finite, reasonable max.
    """

    buyer = Buyer(
        annual_income=Decimal("50_000_000"),
        monthly_debts=Decimal("0"),
        down_payment=Decimal("10_000_000"),
        rate=Decimal("0.0675"),
        term_years=30,
    )
    result = affordability(buyer, _bay_area_market())
    assert result.max_by_loan_type["jumbo"].is_finite()
    assert result.max_by_loan_type["jumbo"] > Decimal("0")
