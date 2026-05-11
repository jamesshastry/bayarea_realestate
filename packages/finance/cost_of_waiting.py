"""Cost-of-Waiting calculator per ``docs/design.md`` §5.3.3.

Implements the C3 contract:

    cost_of_waiting(buyer: Buyer, area_id: str, params: WaitParams) -> WaitGrid

Returns a 9-cell grid: 3 appreciation scenarios × 3 rate scenarios.
Each cell is a ``WaitCell`` with the seven required outputs:

  * ``appreciation_change_dollars``
  * ``rent_paid_during_wait``
  * ``monthly_payment_now``
  * ``monthly_payment_later``
  * ``cumulative_savings_or_cost``
  * ``break_even_rate_drop``
  * ``net_dollar_impact``

Sign convention: a *positive* ``net_dollar_impact`` means waiting cost
the buyer money; *negative* means waiting saved money. UI presentation
is descriptive (per operating principle #4); we never label scenarios as
"good" or "bad."

The function is pure — no clock, no globals — and uses ``Decimal``
throughout so the TS port can reproduce byte-equal output.

``area_id`` is part of the contract for future evolution (Phase 3 will
look up area-specific defaults), but Phase 1 doesn't use it: the caller
already passes the resolved ``params.area_ctx``. The signature stays
fixed so neither side of the C3 contract has to change.
"""

from __future__ import annotations

from decimal import ROUND_HALF_EVEN, Decimal

from ._types import (
    AreaContext,
    Buyer,
    WaitCell,
    WaitGrid,
    WaitParams,
)
from .affordability import monthly_cost, principal_and_interest

_ZERO = Decimal("0")
_ONE = Decimal("1")
_TWELVE = Decimal("12")


def _round_money(amount: Decimal) -> Decimal:
    return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)


def _later_price(
    target_price: Decimal, annual_appreciation: Decimal, months: int
) -> Decimal:
    """Project price ``months`` months out at ``annual_appreciation`` (compounded monthly).

    A negative ``annual_appreciation`` (e.g., ``-0.02``) projects depreciation.
    """

    monthly_rate = annual_appreciation / _TWELVE
    factor = (_ONE + monthly_rate) ** months
    return target_price * factor


def _payment_at(price: Decimal, area_ctx: AreaContext, rate: Decimal) -> Decimal:
    """Total monthly payment at ``price`` if the loan rate were ``rate``."""

    derived = AreaContext(
        county=area_ctx.county,
        property_tax_rate=area_ctx.property_tax_rate,
        mello_roos_annual=area_ctx.mello_roos_annual,
        hoa_monthly=area_ctx.hoa_monthly,
        insurance_annual=area_ctx.insurance_annual,
        wildfire_surcharge_multiplier=area_ctx.wildfire_surcharge_multiplier,
        rate=rate,
        term_years=area_ctx.term_years,
        down_payment=area_ctx.down_payment,
        pmi_annual_rate=area_ctx.pmi_annual_rate,
    )
    return monthly_cost(price, derived).total


def _break_even_rate_drop(
    target_price: Decimal,
    later_price: Decimal,
    appreciation_change: Decimal,
    rent_paid: Decimal,
    monthly_payment_now: Decimal,
    area_ctx: AreaContext,
    months: int,
) -> Decimal:
    """The absolute rate drop (decimal) over the wait horizon that makes
    the cumulative net impact zero.

    We solve numerically: for each candidate rate drop, compute the
    cumulative net impact; binary-search the drop in [0, 0.05] (5pp)
    until the magnitude is within $50.

    Returns ``Decimal("0")`` if the buyer is *already* better off acting
    now even at zero rate change (i.e., no rate drop justifies waiting).
    """

    # Quick check: if waiting at 0bp move already saves money, return 0.
    monthly_payment_at_zero = _payment_at(later_price, area_ctx, area_ctx.rate)
    impact_at_zero = _impact(
        appreciation_change=appreciation_change,
        rent_paid=rent_paid,
        monthly_payment_now=monthly_payment_now,
        monthly_payment_later=monthly_payment_at_zero,
        months=months,
    )
    if impact_at_zero <= 0:
        # Waiting is already net-zero or better at zero rate change.
        return _ZERO

    lo = _ZERO
    hi = Decimal("0.05")  # 5pp — generous outer bound
    epsilon = Decimal("50")  # $50 net-impact tolerance

    # Precondition for binary search: at hi (max drop), waiting must be
    # cheaper than at lo (no drop). If even a 5pp drop doesn't make
    # waiting break even, return hi as a sentinel — the UI will render
    # "rates would need to drop > 5pp" rather than a misleading number.
    monthly_payment_at_hi = _payment_at(later_price, area_ctx, area_ctx.rate - hi)
    impact_at_hi = _impact(
        appreciation_change=appreciation_change,
        rent_paid=rent_paid,
        monthly_payment_now=monthly_payment_now,
        monthly_payment_later=monthly_payment_at_hi,
        months=months,
    )
    if impact_at_hi > 0:
        return hi

    while hi - lo > Decimal("0.00005"):  # 0.5bp resolution
        mid = (hi + lo) / Decimal("2")
        monthly_payment_at_mid = _payment_at(later_price, area_ctx, area_ctx.rate - mid)
        impact_at_mid = _impact(
            appreciation_change=appreciation_change,
            rent_paid=rent_paid,
            monthly_payment_now=monthly_payment_now,
            monthly_payment_later=monthly_payment_at_mid,
            months=months,
        )
        if abs(impact_at_mid) < epsilon:
            return mid.quantize(Decimal("0.0001"), rounding=ROUND_HALF_EVEN)
        if impact_at_mid > 0:
            # Still costing money to wait — need a larger drop.
            lo = mid
        else:
            # Saving money — try a smaller drop.
            hi = mid

    return (
        (hi + lo) / Decimal("2")
    ).quantize(  # pragma: no cover - search converges via line 146 for realistic inputs
        Decimal("0.0001"), rounding=ROUND_HALF_EVEN
    )


def _impact(
    appreciation_change: Decimal,
    rent_paid: Decimal,
    monthly_payment_now: Decimal,
    monthly_payment_later: Decimal,
    months: int,
) -> Decimal:
    """Net dollar impact of waiting.

    Components (signs as the user experiences them — positive = bad):

      + appreciation_change   (price went up while waiting → bad)
      + rent_paid             (rent paid during wait is spent money → bad)
      + (later - now) * months  (higher monthly payment over loan life
                                 — but truncated to the wait horizon
                                 here for the *cumulative* metric)

    A negative ``appreciation_change`` (price fell) flips the sign — that
    is good for the buyer.
    """

    payment_delta = (monthly_payment_later - monthly_payment_now) * Decimal(months)
    return appreciation_change + rent_paid + payment_delta


def cost_of_waiting(buyer: Buyer, area_id: str, params: WaitParams) -> WaitGrid:
    """Compute the 9-cell cost-of-waiting grid.

    Per the C3 contract the signature is
    ``(buyer: Buyer, area_id: str, params: WaitParams) -> WaitGrid``.

    ``area_id`` is part of the contract for forward compatibility with
    Phase-3 area-specific defaults; Phase-1 reads only ``params``.
    """

    if params.target_price <= 0:
        raise ValueError(f"target_price must be positive, got {params.target_price}")
    if params.wait_horizon_months <= 0:
        raise ValueError(
            f"wait_horizon_months must be positive, got {params.wait_horizon_months}"
        )
    if buyer.term_years <= 0:
        raise ValueError(f"term_years must be positive, got {buyer.term_years}")

    months = params.wait_horizon_months
    target_price = params.target_price
    monthly_payment_now = _payment_at(
        target_price, params.area_ctx, params.current_rate
    )
    rent_paid_during_wait = _round_money(params.current_rent * Decimal(months))

    rows: list[list[WaitCell]] = []
    for appreciation_annual in params.appreciation_scenarios:
        row: list[WaitCell] = []
        later_price = _later_price(target_price, appreciation_annual, months)
        appreciation_change_dollars = _round_money(later_price - target_price)
        for rate_change in params.rate_scenarios:
            later_rate = params.current_rate + rate_change
            monthly_payment_later = _payment_at(
                later_price, params.area_ctx, later_rate
            )
            cumulative = _round_money(
                (monthly_payment_later - monthly_payment_now) * Decimal(months)
            )
            net = _round_money(
                _impact(
                    appreciation_change=appreciation_change_dollars,
                    rent_paid=rent_paid_during_wait,
                    monthly_payment_now=monthly_payment_now,
                    monthly_payment_later=monthly_payment_later,
                    months=months,
                )
            )
            break_even = _break_even_rate_drop(
                target_price=target_price,
                later_price=later_price,
                appreciation_change=appreciation_change_dollars,
                rent_paid=rent_paid_during_wait,
                monthly_payment_now=monthly_payment_now,
                area_ctx=params.area_ctx,
                months=months,
            )
            row.append(
                WaitCell(
                    appreciation_annual=appreciation_annual,
                    rate_change=rate_change,
                    appreciation_change_dollars=appreciation_change_dollars,
                    rent_paid_during_wait=rent_paid_during_wait,
                    monthly_payment_now=monthly_payment_now,
                    monthly_payment_later=monthly_payment_later,
                    cumulative_savings_or_cost=cumulative,
                    break_even_rate_drop=break_even,
                    net_dollar_impact=net,
                )
            )
        rows.append(row)

    return WaitGrid(
        target_price=target_price,
        wait_horizon_months=months,
        current_rate=params.current_rate,
        cells=rows,
    )


# Re-export the principal-and-interest helper for the test file (tests
# can verify the building block without re-deriving the formula).
__all__ = [
    # Internal helpers exposed for tests only.
    "_break_even_rate_drop",
    "_impact",
    "_later_price",
    "_payment_at",
    "cost_of_waiting",
    "principal_and_interest",
]
