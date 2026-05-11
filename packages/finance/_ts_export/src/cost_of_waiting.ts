/**
 * Cost-of-Waiting calculator per `docs/design.md` §5.3.3 — TS port of
 * `packages/finance/cost_of_waiting.py`.
 *
 * Implements the C3 contract:
 *
 *   costOfWaiting(buyer, area_id, params) -> WaitGrid
 *
 * Returns a 9-cell grid: 3 appreciation scenarios × 3 rate scenarios.
 *
 * Sign convention: a *positive* `net_dollar_impact` means waiting cost
 * the buyer money; *negative* means waiting saved money. UI presentation
 * is descriptive (per operating principle #4); we never label scenarios
 * as "good" or "bad".
 *
 * The function is pure — no clock, no globals — and uses `Decimal`
 * throughout so byte-equal output parity with the Python implementation
 * is exact.
 *
 * `area_id` is part of the contract for future evolution (Phase 3 will
 * look up area-specific defaults), but Phase 1 doesn't use it: the caller
 * already passes the resolved `params.area_ctx`. The signature stays
 * fixed so neither side of the C3 contract has to change.
 */

import { Decimal } from "./decimal.js";
import { monthlyCost, principalAndInterest } from "./affordability.js";
import type {
  AreaContext,
  Buyer,
  WaitCell,
  WaitGrid,
  WaitParams,
} from "./types.js";

const ZERO = new Decimal("0");
const ONE = new Decimal("1");
const TWELVE = new Decimal("12");
const TWO = new Decimal("2");
const CENT = new Decimal("0.01");
const RATE_QUANTUM = new Decimal("0.0001");

function roundMoney(amount: Decimal): Decimal {
  return amount.quantize(CENT);
}

/** Project price `months` months out at `annual_appreciation` (compounded
 *  monthly). Negative `annual_appreciation` projects depreciation. */
function laterPrice(targetPrice: Decimal, annualAppreciation: Decimal, months: number): Decimal {
  const monthlyRate = annualAppreciation.div(TWELVE);
  const factor = ONE.add(monthlyRate).pow(months);
  return targetPrice.mul(factor);
}

/** Total monthly payment at `price` if the loan rate were `rate`. */
function paymentAt(price: Decimal, areaCtx: AreaContext, rate: Decimal): Decimal {
  const derived: AreaContext = {
    county: areaCtx.county,
    property_tax_rate: areaCtx.property_tax_rate,
    mello_roos_annual: areaCtx.mello_roos_annual,
    hoa_monthly: areaCtx.hoa_monthly,
    insurance_annual: areaCtx.insurance_annual,
    wildfire_surcharge_multiplier: areaCtx.wildfire_surcharge_multiplier,
    rate,
    term_years: areaCtx.term_years,
    down_payment: areaCtx.down_payment,
    pmi_annual_rate: areaCtx.pmi_annual_rate,
  };
  return monthlyCost(price, derived).total;
}

/** Net dollar impact of waiting. Components (signs as the user
 *  experiences them — positive = bad):
 *
 *    + appreciation_change    (price went up while waiting → bad)
 *    + rent_paid              (rent paid during wait is spent money → bad)
 *    + (later - now) * months (higher monthly payment over loan life — but
 *                              truncated to the wait horizon for the
 *                              cumulative metric)
 *
 *  A negative `appreciation_change` (price fell) flips the sign — that
 *  is good for the buyer. */
function impact(
  appreciationChange: Decimal,
  rentPaid: Decimal,
  monthlyPaymentNow: Decimal,
  monthlyPaymentLater: Decimal,
  months: number,
): Decimal {
  const paymentDelta = monthlyPaymentLater.sub(monthlyPaymentNow).mul(new Decimal(months));
  return appreciationChange.add(rentPaid).add(paymentDelta);
}

/** Absolute rate drop (decimal) over the wait horizon that makes the
 *  cumulative net impact zero. Returns 0 if the buyer is already better
 *  off acting now even at zero rate change; returns 0.05 (5pp sentinel)
 *  if even a 5pp drop wouldn't break even. */
function breakEvenRateDrop(
  _targetPrice: Decimal,
  later: Decimal,
  appreciationChange: Decimal,
  rentPaid: Decimal,
  monthlyPaymentNow: Decimal,
  areaCtx: AreaContext,
  months: number,
): Decimal {
  // Quick check: if waiting at 0bp move already saves money, return 0.
  const monthlyAtZero = paymentAt(later, areaCtx, areaCtx.rate);
  const impactAtZero = impact(
    appreciationChange,
    rentPaid,
    monthlyPaymentNow,
    monthlyAtZero,
    months,
  );
  if (impactAtZero.lte(ZERO)) {
    return ZERO;
  }

  let lo = ZERO;
  let hi = new Decimal("0.05"); // 5pp — generous outer bound
  const epsilon = new Decimal("50"); // $50 net-impact tolerance

  // Precondition for binary search: at hi (max drop), waiting must be
  // cheaper than at lo. If even a 5pp drop doesn't make waiting break
  // even, return hi as a sentinel so the UI renders "rates would need to
  // drop > 5pp" rather than a misleading number.
  const monthlyAtHi = paymentAt(later, areaCtx, areaCtx.rate.sub(hi));
  const impactAtHi = impact(
    appreciationChange,
    rentPaid,
    monthlyPaymentNow,
    monthlyAtHi,
    months,
  );
  if (impactAtHi.gt(ZERO)) {
    return hi;
  }

  const minStep = new Decimal("0.00005"); // 0.5bp resolution
  while (hi.sub(lo).gt(minStep)) {
    const mid = hi.add(lo).div(TWO);
    const monthlyAtMid = paymentAt(later, areaCtx, areaCtx.rate.sub(mid));
    const impactAtMid = impact(
      appreciationChange,
      rentPaid,
      monthlyPaymentNow,
      monthlyAtMid,
      months,
    );
    if (impactAtMid.abs().lt(epsilon)) {
      return mid.quantize(RATE_QUANTUM);
    }
    if (impactAtMid.gt(ZERO)) {
      // Still costing money to wait — need a larger drop.
      lo = mid;
    } else {
      // Saving money — try a smaller drop.
      hi = mid;
    }
  }
  // Loop exit (search converges via `epsilon` for realistic inputs).
  return hi.add(lo).div(TWO).quantize(RATE_QUANTUM);
}

/**
 * Compute the 9-cell cost-of-waiting grid.
 *
 * Per the C3 contract the signature is
 * `(buyer, area_id, params) -> WaitGrid`.
 *
 * `area_id` is part of the contract for forward compatibility with
 * Phase-3 area-specific defaults; Phase-1 reads only `params`.
 */
export function costOfWaiting(buyer: Buyer, _areaId: string, params: WaitParams): WaitGrid {
  if (params.target_price.lte(ZERO)) {
    throw new Error(
      `target_price must be positive, got ${params.target_price.toString()}`,
    );
  }
  if (params.wait_horizon_months <= 0) {
    throw new Error(
      `wait_horizon_months must be positive, got ${params.wait_horizon_months}`,
    );
  }
  if (buyer.term_years <= 0) {
    throw new Error(`term_years must be positive, got ${buyer.term_years}`);
  }

  const months = params.wait_horizon_months;
  const targetPrice = params.target_price;
  const monthlyPaymentNow = paymentAt(targetPrice, params.area_ctx, params.current_rate);
  const rentPaidDuringWait = roundMoney(params.current_rent.mul(new Decimal(months)));

  const cells: WaitCell[][] = [];
  for (const appreciationAnnual of params.appreciation_scenarios) {
    const row: WaitCell[] = [];
    const later = laterPrice(targetPrice, appreciationAnnual, months);
    const appreciationChangeDollars = roundMoney(later.sub(targetPrice));
    for (const rateChange of params.rate_scenarios) {
      const laterRate = params.current_rate.add(rateChange);
      const monthlyPaymentLater = paymentAt(later, params.area_ctx, laterRate);
      const cumulative = roundMoney(
        monthlyPaymentLater.sub(monthlyPaymentNow).mul(new Decimal(months)),
      );
      const net = roundMoney(
        impact(
          appreciationChangeDollars,
          rentPaidDuringWait,
          monthlyPaymentNow,
          monthlyPaymentLater,
          months,
        ),
      );
      const breakEven = breakEvenRateDrop(
        targetPrice,
        later,
        appreciationChangeDollars,
        rentPaidDuringWait,
        monthlyPaymentNow,
        params.area_ctx,
        months,
      );
      row.push({
        appreciation_annual: appreciationAnnual,
        rate_change: rateChange,
        appreciation_change_dollars: appreciationChangeDollars,
        rent_paid_during_wait: rentPaidDuringWait,
        monthly_payment_now: monthlyPaymentNow,
        monthly_payment_later: monthlyPaymentLater,
        cumulative_savings_or_cost: cumulative,
        break_even_rate_drop: breakEven,
        net_dollar_impact: net,
      });
    }
    cells.push(row);
  }

  return {
    target_price: targetPrice,
    wait_horizon_months: months,
    current_rate: params.current_rate,
    cells,
  };
}

// Re-export the principal-and-interest helper so test files can verify
// the building block without re-deriving the formula (mirrors the
// Python module's `__all__`).
export { principalAndInterest };
