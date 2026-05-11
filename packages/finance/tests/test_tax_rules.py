"""Sanity checks on the pinned 2026 tax / loan-limit constants.

These tests are intentionally chunky on the structural invariants
(every Bay Area county is enumerated; every loan type has a min
down-payment; etc.) because the constants will be re-pinned annually
and a smoke test catches accidental deletion or rate inversion.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from finance import tax_rules
from finance._types import County, LoanType


def test_effective_year_is_2026() -> None:
    assert tax_rules.EFFECTIVE_YEAR == 2026
    # The pinned date string also encodes the year.
    assert tax_rules.LAST_UPDATED.startswith("2026")


def test_every_county_has_a_loan_limit_and_a_tax_rate() -> None:
    for county in County:
        assert county in tax_rules.COUNTY_LOAN_LIMITS_2026, f"missing loan limit for {county}"
        assert county in tax_rules.COUNTY_PROPERTY_TAX_RATES_2026, (
            f"missing property tax rate for {county}"
        )


def test_high_balance_ceiling_is_150_pct_of_baseline() -> None:
    """Per FHFA methodology the high-cost ceiling = 150% of baseline.

    We allow a $50 rounding tolerance because the published numbers are
    rounded to the nearest $50.
    """

    expected = tax_rules.CONFORMING_BASELINE_2026 * Decimal("1.5")
    delta = abs(tax_rules.HIGH_BALANCE_CEILING_2026 - expected)
    assert delta < Decimal("100"), (
        f"High-balance ceiling {tax_rules.HIGH_BALANCE_CEILING_2026} not within $100 of "
        f"1.5x baseline {expected}"
    )


def test_every_bay_area_county_uses_high_balance_ceiling() -> None:
    """All nine Bay Area counties qualify for the high-balance ceiling.

    If a future year demotes a county, this test must fail to force a
    conscious decision.
    """

    for county, limit in tax_rules.COUNTY_LOAN_LIMITS_2026.items():
        assert limit == tax_rules.HIGH_BALANCE_CEILING_2026, (
            f"{county} should use the high-balance ceiling but is {limit}"
        )


def test_property_tax_rates_are_within_legal_range() -> None:
    """Prop 13 base rate is 1%; effective rates go up with bonds and
    assessments. None should be below 1% or above 1.5%.
    """

    for county, rate in tax_rules.COUNTY_PROPERTY_TAX_RATES_2026.items():
        assert Decimal("0.01") <= rate <= Decimal("0.015"), (
            f"{county} effective rate {rate} outside sanity band"
        )


@pytest.mark.parametrize("loan_type", ["conforming", "high_balance", "jumbo", "fha"])
def test_min_down_payment_is_defined_and_positive(loan_type: LoanType) -> None:
    pct = tax_rules.MIN_DOWN_PAYMENT_PCT[loan_type]
    assert pct > Decimal("0")
    assert pct <= Decimal("0.20"), f"min-down for {loan_type} is implausibly high ({pct})"


def test_dti_thresholds_are_canonical() -> None:
    assert tax_rules.DTI_FRONT_END == Decimal("0.28")
    assert tax_rules.DTI_BACK_END == Decimal("0.36")


def test_pmi_threshold_is_80_percent_ltv() -> None:
    assert tax_rules.PMI_LTV_THRESHOLD == Decimal("0.80")


def test_prop_13_constants() -> None:
    assert tax_rules.PROP_13_ANNUAL_CAP == Decimal("0.02")
    assert tax_rules.PROP_13_BASE_RATE == Decimal("0.01")


def test_salt_cap_is_10k() -> None:
    assert tax_rules.SALT_CAP_2026 == Decimal("10000")


def test_conforming_limit_helper_for_each_county() -> None:
    for county in County:
        assert tax_rules.conforming_limit(county) == tax_rules.HIGH_BALANCE_CEILING_2026


def test_fha_limit_for_each_county() -> None:
    for county in County:
        assert tax_rules.fha_limit(county) == tax_rules.FHA_HIGH_COST_CEILING_2026


def test_property_tax_rate_helper_matches_table() -> None:
    for county in County:
        assert (
            tax_rules.property_tax_rate(county)
            == (tax_rules.COUNTY_PROPERTY_TAX_RATES_2026[county])
        )


def test_loan_limit_helper_per_loan_type() -> None:
    county = County.ALAMEDA
    assert tax_rules.loan_limit(county, "conforming") == tax_rules.CONFORMING_BASELINE_2026
    assert tax_rules.loan_limit(county, "high_balance") == tax_rules.HIGH_BALANCE_CEILING_2026
    assert tax_rules.loan_limit(county, "fha") == tax_rules.FHA_HIGH_COST_CEILING_2026
    assert tax_rules.loan_limit(county, "jumbo") == Decimal("Infinity")


def test_loan_limit_helper_rejects_unknown_loan_type() -> None:
    with pytest.raises(ValueError, match="Unknown loan_type"):
        tax_rules.loan_limit(County.ALAMEDA, "vintage_special")  # type: ignore[arg-type]


def test_fha_limit_rejects_unknown_county() -> None:
    """If we ever add a County member without an entry in
    ``COUNTY_LOAN_LIMITS_2026``, ``fha_limit`` must raise.
    """

    class FakeCounty:
        value = "atlantis"

    with pytest.raises(KeyError):
        tax_rules.fha_limit(FakeCounty())  # type: ignore[arg-type]
