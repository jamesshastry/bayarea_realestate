/**
 * Affordability + monthly-cost computation — TS port of
 * `packages/finance/affordability.py`.
 *
 * Implements the C3 contract:
 *
 *   affordability(buyer, market_ctx) -> AffordabilityResult
 *   monthlyCost(price, area_ctx) -> MonthlyCost
 *
 * Conventions enforced here (mirroring the Python module):
 *
 * - All money is `Decimal`. We never coerce to JS `number` inside the
 *   function bodies; intermediate ratios are `Decimal` too so the
 *   arithmetic chain is unbroken.
 * - Every quantize uses `ROUND_HALF_EVEN` (banker's rounding).
 * - No I/O, no clock, no random.
 *
 * Math is per `docs/design.md` §5.1:
 *
 * - `comfortable` = price at which the front-end DTI cap (28%) on the
 *   total monthly housing cost `M` binds, given the buyer's income.
 * - `stretch`     = price at which the back-end DTI cap (36%) on
 *   `M + monthly_debts` binds.
 * - `max_by_loan_type` = price ceiling such that the *loan amount*
 *   (price − down_payment) ≤ the loan-type's principal limit AND the
 *   back-end DTI cap holds.
 *
 * We solve for `price` by binary search rather than algebraic inversion
 * because `M(price)` is piecewise (PMI step at LTV = 80%); binary search
 * keeps the code shape identical to the Python implementation, which is
 * what makes byte-equal output achievable.
 */

import { Decimal, maxDecimal } from "./decimal.js";
import {
  DTI_BACK_END,
  DTI_FRONT_END,
  MIN_DOWN_PAYMENT_PCT,
  PMI_LTV_THRESHOLD,
  isJumboSentinel,
  loanLimit,
  propertyTaxRate,
} from "./tax_rules.js";
import type {
  AffordabilityResult,
  AreaContext,
  Buyer,
  LoanType,
  MarketContext,
  MonthlyCost,
} from "./types.js";

/** Two-decimal cents pattern (e.g. for monthly money lines). */
const CENT = new Decimal("0.01");
/** Whole-dollar pattern (used for top-line affordability prices). */
const DOLLAR = new Decimal("1");
/** Binary search tolerance: $1. Anything tighter is below the rounding
 *  noise of the inputs. */
const PRICE_EPSILON = new Decimal("1");
/** Search ceiling: $50M — anything above is non-FTHB and would blow up the
 *  iteration count. */
const PRICE_CEILING = new Decimal("50000000");
const PRICE_FLOOR = new Decimal("0");
const TWO = new Decimal("2");
const TWELVE = new Decimal("12");
const ZERO = new Decimal("0");

/** Round to whole cents with banker's rounding. */
function roundMoney(amount: Decimal): Decimal {
  return amount.quantize(CENT);
}

/** Round to whole dollars (for top-line price ceilings). */
function roundDollar(amount: Decimal): Decimal {
  return amount.quantize(DOLLAR);
}

/**
 * Standard mortgage P&I formula:
 *
 *   M = L * r / (1 - (1 + r)^-n)
 *
 * where `r` is the monthly rate and `n` is the number of monthly payments.
 *
 * Edge cases:
 * - `loan_amount <= 0`  → 0 (no loan, no payment).
 * - `annual_rate == 0`  → `loan_amount / n` (linear amortization).
 */
export function principalAndInterest(
  loanAmount: Decimal,
  annualRate: Decimal,
  termYears: number,
): Decimal {
  if (loanAmount.lte(ZERO)) {
    return new Decimal("0");
  }
  const n = termYears * 12;
  if (annualRate.isZero()) {
    return roundMoney(loanAmount.div(new Decimal(n)));
  }
  const monthlyRate = annualRate.div(TWELVE);
  const onePlusR = new Decimal("1").add(monthlyRate);
  // (1 + r)^-n via integer power on the inverse — `Decimal.pow` mirrors
  // Python's `Decimal ** int` semantics for negative integer exponents
  // (returns 1 / pow(positive)).
  const factor = new Decimal("1").sub(onePlusR.pow(-n));
  const payment = loanAmount.mul(monthlyRate).div(factor);
  return roundMoney(payment);
}

/**
 * Compute the monthly cost breakdown for a target `price`.
 *
 * Per F-AFF-04, the breakdown components MUST sum to the total. The
 * `properties.test.ts` invariant `monthlyCost.components_sum_to_total`
 * enforces this property over a wide input range.
 */
export function monthlyCost(price: Decimal, areaCtx: AreaContext): MonthlyCost {
  if (price.lt(ZERO)) {
    throw new Error(`price must be non-negative, got ${price.toString()}`);
  }
  const roundedPrice = roundMoney(price);

  let loanAmount = roundedPrice.sub(areaCtx.down_payment);
  if (loanAmount.lt(ZERO)) {
    loanAmount = new Decimal("0");
  }

  const pAndI = principalAndInterest(loanAmount, areaCtx.rate, areaCtx.term_years);

  // Property tax — annualized rate applied to *price* (not assessed
  // value). Per Prop 13 the assessed value resets to purchase price on
  // change of ownership, so for an FTHB price ≈ assessed value at year 0.
  const annualTax = roundedPrice.mul(areaCtx.property_tax_rate);
  const tax = roundMoney(annualTax.div(TWELVE));

  // Mello-Roos / HOA / insurance — straight per-month conversions.
  const mello = roundMoney(areaCtx.mello_roos_annual.div(TWELVE));
  const hoa = roundMoney(areaCtx.hoa_monthly);
  const annualInsurance = areaCtx.insurance_annual.mul(areaCtx.wildfire_surcharge_multiplier);
  const insurance = roundMoney(annualInsurance.div(TWELVE));

  // PMI — applied only when LTV > 80%. We use original LTV at
  // origination per `docs/glossary/pmi.md`.
  let ltv: Decimal;
  if (roundedPrice.gt(ZERO)) {
    ltv = loanAmount.div(roundedPrice);
  } else {
    ltv = new Decimal("0");
  }
  let pmi: Decimal;
  if (ltv.gt(PMI_LTV_THRESHOLD)) {
    const annualPmi = loanAmount.mul(areaCtx.pmi_annual_rate);
    pmi = roundMoney(annualPmi.div(TWELVE));
  } else {
    pmi = new Decimal("0");
  }

  const total = roundMoney(
    pAndI.add(tax).add(mello).add(hoa).add(insurance).add(pmi),
  );
  return {
    price: roundedPrice,
    p_and_i: pAndI,
    tax,
    mello,
    hoa,
    insurance,
    pmi,
    total,
  };
}

/** Internal helper: build an `AreaContext` from buyer + market.
 *
 *  The affordability calc itself doesn't take an explicit `AreaContext`;
 *  it derives a sensible one from the county's typical tax rate plus the
 *  buyer's loan parameters. Callers that need parcel-specific Mello /
 *  HOA / insurance call `monthlyCost` directly with their own
 *  `AreaContext`. */
function buildAreaCtxFromBuyer(buyer: Buyer, marketCtx: MarketContext): AreaContext {
  return {
    county: marketCtx.county,
    property_tax_rate: propertyTaxRate(marketCtx.county),
    mello_roos_annual: new Decimal("0"),
    hoa_monthly: new Decimal("0"),
    // 0.35% of price annualized is a workable Bay Area homeowners'
    // estimate; the wildfire surcharge layer handles FHSZ areas. The
    // *real* number comes from `packages/adapters/insurance_quote` in
    // Phase 5; Phase 1 uses the area-typical fallback.
    insurance_annual: new Decimal("3500"),
    wildfire_surcharge_multiplier: new Decimal("1.0"),
    rate: buyer.rate,
    term_years: buyer.term_years,
    down_payment: buyer.down_payment,
    pmi_annual_rate: new Decimal("0.0055"),
  };
}

/** Binary-search the largest `price` whose `monthlyCost.total ≤ cap`.
 *
 *  Returns `Decimal("0")` if even the floor (down payment, no loan)
 *  already exceeds the cap (i.e., taxes/insurance/HOA on the down
 *  payment alone blow the budget). */
function solveMaxPriceForMonthly(
  monthlyCap: Decimal,
  areaCtx: AreaContext,
  upperBound: Decimal = PRICE_CEILING,
): Decimal {
  if (monthlyCap.lte(ZERO)) {
    return new Decimal("0");
  }

  let lo = PRICE_FLOOR;
  let hi = upperBound;
  // Floor case: a price equal to down_payment means loan = 0 and
  // P&I = PMI = 0, but tax/insurance still apply. If even that floor is
  // not feasible, no price works.
  const floorCost = monthlyCost(areaCtx.down_payment, areaCtx).total;
  if (floorCost.gt(monthlyCap)) {
    return new Decimal("0");
  }

  // Ceiling case: if even `hi` is affordable, cap there (don't return
  // `Infinity`; UI would explode).
  const ceilingCost = monthlyCost(hi, areaCtx).total;
  if (ceilingCost.lte(monthlyCap)) {
    return roundDollar(hi);
  }

  while (hi.sub(lo).gt(PRICE_EPSILON)) {
    const mid = hi.add(lo).div(TWO);
    const cost = monthlyCost(mid, areaCtx).total;
    if (cost.gt(monthlyCap)) {
      hi = mid;
    } else {
      lo = mid;
    }
  }

  return roundDollar(lo);
}

/** Identify which rule binds the *maximum* affordability row. Order of
 *  precedence (lowest is most-binding): cash_on_hand → dti_front →
 *  dti_back → loan_limit. */
function bindingConstraint(
  comfortable: Decimal,
  stretch: Decimal,
  maxOverall: Decimal,
  maxLoanCapped: Decimal,
  cashCapped: Decimal,
): "dti_front" | "dti_back" | "loan_limit" | "cash_on_hand" {
  if (cashCapped.lte(maxLoanCapped) && cashCapped.lte(stretch)) {
    return "cash_on_hand";
  }
  if (maxOverall.eq(maxLoanCapped) && maxLoanCapped.lt(stretch)) {
    return "loan_limit";
  }
  if (maxOverall.lte(comfortable)) {
    return "dti_front";
  }
  return "dti_back";
}

/** Per-loan-type max-price grid.
 *
 *  For each loan type:
 *    max_price = min(
 *      down_payment + loan_limit(loan_type, county),  // loan ceiling
 *      solveMaxPriceForMonthly(monthly_cap, area_ctx), // DTI cap
 *      down_payment / min_down_pct,                   // cash cap
 *    )
 *
 *  The last term enforces "the buyer's cash must satisfy the loan
 *  type's minimum down" — for a $50K down, a 5%-min loan tops out at
 *  $1M regardless of what DTI or loan-limit allow. */
function maxPricePerLoanType(
  buyer: Buyer,
  marketCtx: MarketContext,
  areaCtx: AreaContext,
  monthlyCap: Decimal,
): Record<string, Decimal> {
  const grid: Record<string, Decimal> = {};
  const dtiCapPrice = solveMaxPriceForMonthly(monthlyCap, areaCtx);
  const loanTypes: LoanType[] = ["conforming", "high_balance", "jumbo", "fha"];
  for (const loanType of loanTypes) {
    const principalCeiling = loanLimit(marketCtx.county, loanType);
    let loanPrincipalCap: Decimal;
    if (isJumboSentinel(principalCeiling)) {
      // For jumbo, the "no agency limit" sentinel collapses to the
      // search ceiling — same semantics as Python's `Decimal("Infinity")`
      // when later passed through `min(...)` against finite prices.
      loanPrincipalCap = PRICE_CEILING;
    } else {
      loanPrincipalCap = buyer.down_payment.add(principalCeiling);
    }

    const minDownPct = MIN_DOWN_PAYMENT_PCT[loanType];
    let cashCap: Decimal;
    if (minDownPct.gt(ZERO)) {
      cashCap = buyer.down_payment.div(minDownPct);
    } else {
      // Defensive — all current loan types have positive minimums.
      cashCap = PRICE_CEILING;
    }

    let perTypeMax = loanPrincipalCap;
    if (dtiCapPrice.lt(perTypeMax)) perTypeMax = dtiCapPrice;
    if (cashCap.lt(perTypeMax)) perTypeMax = cashCap;
    if (perTypeMax.lt(ZERO)) {
      perTypeMax = new Decimal("0");
    }
    grid[loanType] = roundDollar(perTypeMax);
  }
  return grid;
}

/**
 * Compute affordability triplet for a buyer in a market.
 *
 * Returns `comfortable`, `stretch`, and `max_by_loan_type` per F-AFF-02.
 * Also returns the binding constraint name and the monthly-cost
 * breakdowns at the comfortable + stretch points so the UI can render
 * them without a second function call.
 */
export function affordability(
  buyer: Buyer,
  marketCtx: MarketContext,
): AffordabilityResult {
  if (buyer.annual_income.lt(ZERO)) {
    throw new Error(
      `annual_income must be non-negative, got ${buyer.annual_income.toString()}`,
    );
  }
  if (buyer.down_payment.lt(ZERO)) {
    throw new Error(
      `down_payment must be non-negative, got ${buyer.down_payment.toString()}`,
    );
  }
  if (buyer.monthly_debts.lt(ZERO)) {
    throw new Error(
      `monthly_debts must be non-negative, got ${buyer.monthly_debts.toString()}`,
    );
  }
  if (buyer.term_years <= 0) {
    throw new Error(`term_years must be positive, got ${buyer.term_years}`);
  }

  const monthlyIncome = buyer.annual_income.div(TWELVE);
  const frontCap = monthlyIncome.mul(DTI_FRONT_END);
  let backCap = monthlyIncome.mul(DTI_BACK_END).sub(buyer.monthly_debts);
  if (backCap.lt(ZERO)) {
    backCap = new Decimal("0");
  }

  const areaCtx = buildAreaCtxFromBuyer(buyer, marketCtx);

  const comfortablePrice = solveMaxPriceForMonthly(frontCap, areaCtx);
  const stretchPrice = solveMaxPriceForMonthly(backCap, areaCtx);

  const maxByLoanType = maxPricePerLoanType(buyer, marketCtx, areaCtx, backCap);
  // Overall max is the largest per-loan-type max — typically jumbo.
  const values = Object.values(maxByLoanType);
  const maxOverall = values.length > 0 ? maxDecimal(values) : new Decimal("0");

  // Identify the binding constraint at the *max overall* row. We look at
  // the high_balance row (most likely to bind on cash + loan-limit) plus
  // jumbo (most likely to bind on cash alone or DTI).
  const cashCappedRaw = buyer.down_payment.div(MIN_DOWN_PAYMENT_PCT.conforming);
  const highBalanceMax = maxByLoanType.high_balance;
  if (!highBalanceMax) {
    // Defensive — `maxPricePerLoanType` always populates this key.
    throw new Error("internal: high_balance entry missing from max_by_loan_type");
  }
  const binding = bindingConstraint(
    comfortablePrice,
    stretchPrice,
    maxOverall,
    highBalanceMax,
    roundDollar(cashCappedRaw),
  );

  const comfortableMonthly = monthlyCost(comfortablePrice, areaCtx);
  const stretchMonthly = monthlyCost(stretchPrice, areaCtx);

  return {
    buyer,
    market_ctx: marketCtx,
    comfortable: comfortablePrice,
    stretch: stretchPrice,
    max_by_loan_type: maxByLoanType,
    binding_constraint: binding,
    comfortable_monthly: comfortableMonthly,
    stretch_monthly: stretchMonthly,
  };
}
