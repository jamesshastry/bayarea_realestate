"""Affordability + monthly-cost computation.

Implements the C3 contract:

    affordability(buyer: Buyer, market_ctx: MarketContext) -> AffordabilityResult
    monthly_cost(price: Decimal, area_ctx: AreaContext) -> MonthlyCost

Conventions enforced here:

- All money is ``Decimal``. We never coerce to ``float`` inside the
  function bodies; intermediate ratios are also ``Decimal`` so the
  arithmetic chain is unbroken.
- Every quantize uses ``ROUND_HALF_EVEN`` (banker's rounding) to match
  the TS port's default ``Number.toFixed`` semantics post-string-cast.
- No I/O, no clock, no random. ``buyer.rate``, ``buyer.term_years``, and
  the area's tax/insurance/PMI inputs are all explicit.

Math is per ``docs/design.md`` §5.1:

- ``comfortable`` = price at which the front-end DTI cap (28%) on the
  total monthly housing cost ``M`` binds, given the buyer's income.
- ``stretch`` = price at which the back-end DTI cap (36%) on
  ``M + monthly_debts`` binds.
- ``max_by_loan_type`` = price ceiling such that the *loan amount*
  (price − down_payment) ≤ the loan-type's principal limit AND the
  back-end DTI cap holds.

We solve for ``price`` by binary search rather than algebraic inversion
because the per-month total ``M(price)`` is piecewise:

- Tax = price × tax_rate / 12 — linear in price.
- P&I depends on the loan amount = price − down_payment, where
  down_payment is a fixed input (not a percentage of price). Linear in
  price.
- PMI applies only when LTV > 80%, i.e. only for loans where
  ``price > down_payment / 0.20``. Step at the threshold.
- Mello / HOA / insurance / fixed insurance + wildfire surcharge are all
  price-independent.

Binary search keeps the code shape identical to the TS port (where
algebraic inversion would diverge across float rounding).
"""

from __future__ import annotations

from decimal import ROUND_HALF_EVEN, Decimal, getcontext
from typing import Literal

from ._types import (
    AffordabilityResult,
    AreaContext,
    Buyer,
    LoanType,
    MarketContext,
    MonthlyCost,
)
from .tax_rules import (
    DTI_BACK_END,
    DTI_FRONT_END,
    MIN_DOWN_PAYMENT_PCT,
    PMI_LTV_THRESHOLD,
    loan_limit,
    property_tax_rate,
)

# Decimal precision is tuned for currency math: 28 digits is more than
# enough to keep $1B prices and $0.01 cents in the same expression
# without rounding error. We set it once at import time; every function
# in this module reads ``getcontext()`` for ROUND_HALF_EVEN.
_CTX = getcontext()
_CTX.prec = 28
_CTX.rounding = ROUND_HALF_EVEN

# Two-decimal cents.
_CENT = Decimal("0.01")
# Whole-dollar (used for top-line affordability prices — no FTHB cares
# about cents on a $1.5M price ceiling).
_DOLLAR = Decimal("1")
# Binary search tolerance: $1. Any tighter is below the rounding noise of
# the inputs.
_PRICE_EPSILON = Decimal("1")
# Search ceiling: $50M. Anything above is non-FTHB and would inflate the
# binary-search iteration count.
_PRICE_CEILING = Decimal("50_000_000")
# Smallest meaningful price we'll ever return.
_PRICE_FLOOR = Decimal("0")


def _round_money(amount: Decimal) -> Decimal:
    """Round to whole cents with banker's rounding."""

    return amount.quantize(_CENT, rounding=ROUND_HALF_EVEN)


def _round_dollar(amount: Decimal) -> Decimal:
    """Round to whole dollars (for top-line price ceilings)."""

    return amount.quantize(_DOLLAR, rounding=ROUND_HALF_EVEN)


def principal_and_interest(
    loan_amount: Decimal, annual_rate: Decimal, term_years: int
) -> Decimal:
    """Standard mortgage P&I formula.

    ``M = L * r / (1 - (1 + r)^-n)`` where ``r`` is the monthly rate
    and ``n`` is the number of monthly payments.

    Edge cases:
    - ``loan_amount == 0`` → 0 (no loan, no payment).
    - ``annual_rate == 0`` → ``loan_amount / n`` (linear amortization).
    """

    if loan_amount <= 0:
        return Decimal("0")
    n = term_years * 12
    if annual_rate == 0:
        return _round_money(loan_amount / Decimal(n))
    monthly_rate = annual_rate / Decimal("12")
    one_plus_r = Decimal("1") + monthly_rate
    # (1 + r)^-n via integer power on the inverse — ``Decimal`` supports
    # ``** int`` directly.
    factor = Decimal("1") - (one_plus_r**-n)
    payment = loan_amount * monthly_rate / factor
    return _round_money(payment)


def monthly_cost(price: Decimal, area_ctx: AreaContext) -> MonthlyCost:
    """Compute the monthly cost breakdown for a target ``price``.

    Per F-AFF-04, the breakdown components MUST sum to the total. The
    Hypothesis test ``test_monthly_cost_components_sum_to_total`` enforces
    this property over a wide input range.
    """

    if price < 0:
        raise ValueError(f"price must be non-negative, got {price}")
    price = _round_money(price)

    loan_amount = price - area_ctx.down_payment
    if loan_amount < 0:
        loan_amount = Decimal("0")

    p_and_i = principal_and_interest(loan_amount, area_ctx.rate, area_ctx.term_years)

    # Property tax — annualized rate applied to *price* (not assessed
    # value). Per Prop 13 the assessed value resets to purchase price on
    # change of ownership, so for an FTHB price ≈ assessed value at
    # year 0. Subsequent years compound at PROP_13_ANNUAL_CAP — that's a
    # TCO concern, not an affordability concern.
    annual_tax = price * area_ctx.property_tax_rate
    tax = _round_money(annual_tax / Decimal("12"))

    # Mello-Roos / HOA / insurance — straight per-month conversions.
    mello = _round_money(area_ctx.mello_roos_annual / Decimal("12"))
    hoa = _round_money(area_ctx.hoa_monthly)
    annual_insurance = (
        area_ctx.insurance_annual * area_ctx.wildfire_surcharge_multiplier
    )
    insurance = _round_money(annual_insurance / Decimal("12"))

    # PMI — applied only when LTV > 80%. We use original LTV at
    # origination per ``docs/glossary/pmi.md``.
    if price > 0:
        ltv = loan_amount / price
    else:
        ltv = Decimal("0")
    if ltv > PMI_LTV_THRESHOLD:
        annual_pmi = loan_amount * area_ctx.pmi_annual_rate
        pmi = _round_money(annual_pmi / Decimal("12"))
    else:
        pmi = Decimal("0")

    total = _round_money(p_and_i + tax + mello + hoa + insurance + pmi)
    return MonthlyCost(
        price=price,
        p_and_i=p_and_i,
        tax=tax,
        mello=mello,
        hoa=hoa,
        insurance=insurance,
        pmi=pmi,
        total=total,
    )


def _build_area_ctx_from_buyer(buyer: Buyer, market_ctx: MarketContext) -> AreaContext:
    """Internal helper: build an ``AreaContext`` from buyer + market.

    The affordability calc itself doesn't take an explicit ``AreaContext``;
    it derives a sensible one from the county's typical tax rate plus the
    buyer's loan parameters. Callers that need parcel-specific Mello /
    HOA / insurance call ``monthly_cost`` directly with their own
    ``AreaContext``.
    """

    return AreaContext(
        county=market_ctx.county,
        property_tax_rate=property_tax_rate(market_ctx.county),
        mello_roos_annual=Decimal("0"),
        hoa_monthly=Decimal("0"),
        # 0.35% of price annualized is a workable Bay Area homeowners'
        # estimate; the wildfire surcharge layer handles FHSZ areas. The
        # *real* number comes from ``packages/adapters/insurance_quote``
        # in Phase 5; Phase 1 uses the area-typical fallback.
        insurance_annual=Decimal("3500"),
        wildfire_surcharge_multiplier=Decimal("1.0"),
        rate=buyer.rate,
        term_years=buyer.term_years,
        down_payment=buyer.down_payment,
    )


def _solve_max_price_for_monthly(
    monthly_cap: Decimal,
    area_ctx: AreaContext,
    upper_bound: Decimal = _PRICE_CEILING,
) -> Decimal:
    """Binary-search the largest ``price`` whose ``monthly_cost.total`` ≤ cap.

    Returns ``Decimal("0")`` if even the floor (down payment, no loan)
    already exceeds the cap (i.e., taxes/insurance/HOA on the down
    payment alone blow the budget).
    """

    if monthly_cap <= 0:
        return Decimal("0")

    lo = _PRICE_FLOOR
    hi = upper_bound
    # The floor case: a price equal to down_payment means loan = 0 and
    # P&I = PMI = 0, but tax/insurance still apply. Check that the floor
    # is feasible; if not, no price works.
    floor_cost = monthly_cost(area_ctx.down_payment, area_ctx).total
    if floor_cost > monthly_cap:
        return Decimal("0")

    # The ceiling case: if even ``hi`` is affordable, we cap there
    # (don't return ``Infinity``; UI would explode).
    ceiling_cost = monthly_cost(hi, area_ctx).total
    if ceiling_cost <= monthly_cap:
        return _round_dollar(hi)

    while hi - lo > _PRICE_EPSILON:
        mid = (hi + lo) / Decimal("2")
        cost = monthly_cost(mid, area_ctx).total
        if cost > monthly_cap:
            hi = mid
        else:
            lo = mid

    return _round_dollar(lo)


def _binding_constraint(
    comfortable: Decimal,
    stretch: Decimal,
    max_overall: Decimal,
    max_loan_capped: Decimal,
    cash_capped: Decimal,
) -> Literal["dti_front", "dti_back", "loan_limit", "cash_on_hand"]:
    """Identify which rule binds the *maximum* affordability row.

    Order of precedence (lowest is most-binding):
    1. cash_on_hand — buyer literally cannot put down enough to clear
       the loan-type's minimum down-payment pct on any meaningful price.
    2. dti_front (28%) — comfortable cap is the binding rule.
    3. dti_back (36%) — stretch cap is the binding rule.
    4. loan_limit — agency principal ceiling is the binding rule.
    """

    # Cash binds when our cash-on-hand-implied price is less than the
    # other constraints (i.e., the down payment isn't enough for any
    # loan-type at the given price).
    if cash_capped <= max_loan_capped and cash_capped <= stretch:
        return "cash_on_hand"
    # If max_overall sits at the loan ceiling, that's binding.
    if max_overall == max_loan_capped and max_loan_capped < stretch:
        return "loan_limit"
    if max_overall <= comfortable:
        return "dti_front"
    return "dti_back"


def _max_price_per_loan_type(
    buyer: Buyer,
    market_ctx: MarketContext,
    area_ctx: AreaContext,
    monthly_cap: Decimal,
) -> dict[str, Decimal]:
    """Per-loan-type max-price grid.

    For each loan type:
      max_price = min(
        # Loan principal cap → price = down_payment + loan_limit
        down_payment + loan_limit(loan_type, county),
        # DTI cap → solve monthly_cost(price) ≤ monthly_cap
        _solve_max_price_for_monthly(monthly_cap, area_ctx),
        # Min-down-payment cap → price = down_payment / min_down_pct
        down_payment / min_down_pct,
      )

    The last term enforces "the buyer's cash must satisfy the loan
    type's minimum down" — for a $50K down payment, a 5%-min loan tops
    out at a $1M price regardless of what DTI or loan-limit allow.
    """

    grid: dict[str, Decimal] = {}
    dti_cap_price = _solve_max_price_for_monthly(monthly_cap, area_ctx)
    for loan_type in ("conforming", "high_balance", "jumbo", "fha"):
        loan_type_typed: LoanType = loan_type  # type: ignore[assignment]
        principal_ceiling = loan_limit(market_ctx.county, loan_type_typed)
        # For jumbo, principal_ceiling is Infinity → loan_principal_cap is
        # essentially unbounded.
        if principal_ceiling == Decimal("Infinity"):
            loan_principal_cap = _PRICE_CEILING
        else:
            loan_principal_cap = buyer.down_payment + principal_ceiling

        min_down_pct = MIN_DOWN_PAYMENT_PCT[loan_type_typed]
        if min_down_pct > 0:
            cash_cap = buyer.down_payment / min_down_pct
        else:  # pragma: no cover - all current loan types have positive minimums
            cash_cap = _PRICE_CEILING

        per_type_max = min(loan_principal_cap, dti_cap_price, cash_cap)
        if (
            per_type_max < 0
        ):  # pragma: no cover - defensive; min() of non-negatives can't be negative
            per_type_max = Decimal("0")
        grid[loan_type] = _round_dollar(per_type_max)
    return grid


def affordability(buyer: Buyer, market_ctx: MarketContext) -> AffordabilityResult:
    """Compute affordability triplet for a buyer in a market.

    Returns ``comfortable``, ``stretch``, and ``max_by_loan_type`` per
    F-AFF-02. Also returns the binding constraint name and the monthly-
    cost breakdowns at the comfortable + stretch points so the UI can
    render them without a second function call.
    """

    if buyer.annual_income < 0:
        raise ValueError(
            f"annual_income must be non-negative, got {buyer.annual_income}"
        )
    if buyer.down_payment < 0:
        raise ValueError(f"down_payment must be non-negative, got {buyer.down_payment}")
    if buyer.monthly_debts < 0:
        raise ValueError(
            f"monthly_debts must be non-negative, got {buyer.monthly_debts}"
        )
    if buyer.term_years <= 0:
        raise ValueError(f"term_years must be positive, got {buyer.term_years}")

    monthly_income = buyer.annual_income / Decimal("12")
    front_cap = monthly_income * DTI_FRONT_END
    back_cap = monthly_income * DTI_BACK_END - buyer.monthly_debts
    if back_cap < 0:
        back_cap = Decimal("0")

    area_ctx = _build_area_ctx_from_buyer(buyer, market_ctx)

    comfortable_price = _solve_max_price_for_monthly(front_cap, area_ctx)
    stretch_price = _solve_max_price_for_monthly(back_cap, area_ctx)

    max_by_loan_type = _max_price_per_loan_type(buyer, market_ctx, area_ctx, back_cap)
    # Overall max is the largest per-loan-type max — typically jumbo.
    max_overall = max(max_by_loan_type.values()) if max_by_loan_type else Decimal("0")

    # Identify the binding constraint at the *max overall* row. We look
    # at the conforming row (most likely to bind on cash + loan-limit)
    # plus jumbo (most likely to bind on cash alone or DTI).
    cash_capped = buyer.down_payment / MIN_DOWN_PAYMENT_PCT["conforming"]
    binding = _binding_constraint(
        comfortable=comfortable_price,
        stretch=stretch_price,
        max_overall=max_overall,
        max_loan_capped=max_by_loan_type["high_balance"],
        cash_capped=_round_dollar(cash_capped),
    )

    comfortable_monthly = monthly_cost(comfortable_price, area_ctx)
    stretch_monthly = monthly_cost(stretch_price, area_ctx)

    return AffordabilityResult(
        buyer=buyer,
        market_ctx=market_ctx,
        comfortable=comfortable_price,
        stretch=stretch_price,
        max_by_loan_type=max_by_loan_type,
        binding_constraint=binding,
        comfortable_monthly=comfortable_monthly,
        stretch_monthly=stretch_monthly,
    )


__all__ = [
    "affordability",
    "monthly_cost",
]
