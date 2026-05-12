// src/decimal.ts
var DECIMAL_CONTEXT_PRECISION = 28;
var ROUND_HALF_EVEN = "ROUND_HALF_EVEN";
var TEN = 10n;
var ZERO_BI = 0n;
var ONE_BI = 1n;
var _powCache = /* @__PURE__ */ new Map();
function pow10(n) {
  if (n < 0) {
    throw new Error(`pow10 requires non-negative n, got ${n}`);
  }
  const cached = _powCache.get(n);
  if (cached !== void 0) {
    return cached;
  }
  let r = ONE_BI;
  for (let i = 0; i < n; i++) {
    r *= TEN;
  }
  _powCache.set(n, r);
  return r;
}
function roundHalfEven(c, n) {
  if (n <= 0) {
    return c;
  }
  const divisor = pow10(n);
  const sign = c < ZERO_BI ? -1n : 1n;
  const absC = c < ZERO_BI ? -c : c;
  const quot = absC / divisor;
  const rem = absC % divisor;
  const twiceRem = rem * 2n;
  let result;
  if (twiceRem < divisor) {
    result = quot;
  } else if (twiceRem > divisor) {
    result = quot + ONE_BI;
  } else {
    result = (quot & ONE_BI) === ZERO_BI ? quot : quot + ONE_BI;
  }
  return sign * result;
}
var Decimal = class _Decimal {
  /** Coefficient (signed). `0n` means zero regardless of `exp`. */
  coef;
  /** Decimal exponent. Final value = `coef * 10^exp`. */
  exp;
  /**
   * Construct from a string (most common — preserves source scale exactly,
   * matching Python's `Decimal("1.0")` behavior), a number (only used in
   * tests and explicitly via `Decimal.fromNumber`), a bigint, or another
   * `Decimal`.
   */
  constructor(input) {
    if (input instanceof _Decimal) {
      this.coef = input.coef;
      this.exp = input.exp;
      return;
    }
    if (typeof input === "bigint") {
      this.coef = input;
      this.exp = 0;
      return;
    }
    if (typeof input === "number") {
      if (!Number.isFinite(input)) {
        throw new Error(`Decimal: non-finite number ${input}`);
      }
      if (!Number.isInteger(input)) {
        throw new Error(
          `Decimal: refusing to construct from non-integer number ${input}; pass a string instead.`
        );
      }
      this.coef = BigInt(input);
      this.exp = 0;
      return;
    }
    const parsed = parseDecimalString(input);
    this.coef = parsed.coef;
    this.exp = parsed.exp;
  }
  // --- Class helpers -------------------------------------------------------
  static fromString(s) {
    return new _Decimal(s);
  }
  static fromInt(n) {
    return new _Decimal(typeof n === "bigint" ? n : BigInt(n));
  }
  static get ZERO() {
    return new _Decimal("0");
  }
  static get ONE() {
    return new _Decimal("1");
  }
  // --- Sign / comparison ---------------------------------------------------
  isZero() {
    return this.coef === ZERO_BI;
  }
  isNegative() {
    return this.coef < ZERO_BI;
  }
  isPositive() {
    return this.coef > ZERO_BI;
  }
  /** Returns -1, 0, or 1. */
  cmp(other) {
    const o = toDecimal(other);
    const minExp = Math.min(this.exp, o.exp);
    const a = this.coef * pow10(this.exp - minExp);
    const b = o.coef * pow10(o.exp - minExp);
    if (a < b) return -1;
    if (a > b) return 1;
    return 0;
  }
  eq(other) {
    return this.cmp(other) === 0;
  }
  lt(other) {
    return this.cmp(other) < 0;
  }
  lte(other) {
    return this.cmp(other) <= 0;
  }
  gt(other) {
    return this.cmp(other) > 0;
  }
  gte(other) {
    return this.cmp(other) >= 0;
  }
  abs() {
    if (this.coef >= ZERO_BI) return this;
    return rebuild(-this.coef, this.exp);
  }
  neg() {
    if (this.coef === ZERO_BI) return this;
    return rebuild(-this.coef, this.exp);
  }
  // --- Arithmetic ----------------------------------------------------------
  //
  // Per the IBM-Decimal spec (which Python's `decimal` module implements),
  // every arithmetic operation is rounded to the context precision. For
  // our finance modules most intermediates stay well under 28 sig figs,
  // but the `(1 + r) ** -n` chain in P&I produces wide coefficients —
  // matching Python exactly there is what makes byte-equal parity work.
  add(other, precision = DECIMAL_CONTEXT_PRECISION) {
    const o = toDecimal(other);
    const minExp = Math.min(this.exp, o.exp);
    const a = this.coef * pow10(this.exp - minExp);
    const b = o.coef * pow10(o.exp - minExp);
    return roundToPrecision(rebuild(a + b, minExp), precision);
  }
  sub(other, precision = DECIMAL_CONTEXT_PRECISION) {
    const o = toDecimal(other);
    const minExp = Math.min(this.exp, o.exp);
    const a = this.coef * pow10(this.exp - minExp);
    const b = o.coef * pow10(o.exp - minExp);
    return roundToPrecision(rebuild(a - b, minExp), precision);
  }
  mul(other, precision = DECIMAL_CONTEXT_PRECISION) {
    const o = toDecimal(other);
    return roundToPrecision(
      rebuild(this.coef * o.coef, this.exp + o.exp),
      precision
    );
  }
  /**
   * Division to context precision (28 sig figs by default), with HALF_EVEN
   * rounding. Mirrors Python's `Decimal / Decimal` under the default context.
   *
   * Implements the IBM-Decimal division algorithm (per the `decimal`
   * Python module's underlying spec): produce digits one at a time from
   * `divmod`, stop when the remainder hits zero (so exact divisions like
   * `0.0675 / 12 = 0.005625` collapse trailing zeros — matching Python
   * exactly) OR we've emitted `precision` significant digits.
   */
  div(other, precision = DECIMAL_CONTEXT_PRECISION) {
    const o = toDecimal(other);
    if (o.coef === ZERO_BI) {
      throw new Error("Decimal.div: division by zero");
    }
    if (this.coef === ZERO_BI) {
      return new _Decimal("0");
    }
    const signA = this.coef < ZERO_BI ? -1n : 1n;
    const signB = o.coef < ZERO_BI ? -1n : 1n;
    const sign = signA * signB;
    const a = this.coef < ZERO_BI ? -this.coef : this.coef;
    const b = o.coef < ZERO_BI ? -o.coef : o.coef;
    let q = a / b;
    let r = a % b;
    let exp = this.exp - o.exp;
    if (r === ZERO_BI) {
      return rebuild(sign * q, exp);
    }
    while (r !== ZERO_BI) {
      const qDigits = q === ZERO_BI ? 0 : q.toString().length;
      if (qDigits >= precision) {
        const twiceR = r * 2n;
        if (twiceR > b) {
          q += ONE_BI;
        } else if (twiceR === b) {
          if ((q & ONE_BI) === ONE_BI) {
            q += ONE_BI;
          }
        }
        break;
      }
      r *= TEN;
      const digit = r / b;
      r = r % b;
      q = q * TEN + digit;
      exp -= 1;
    }
    const qDigitsAfter = q === ZERO_BI ? 0 : q.toString().length;
    if (qDigitsAfter > precision) {
      const drop = qDigitsAfter - precision;
      q = roundHalfEven(q, drop);
      exp += drop;
    }
    return rebuild(sign * q, exp);
  }
  /**
   * Integer-exponent power. Mirrors Python's `Decimal ** int` under the
   * default context (HALF_EVEN, precision 28).
   *
   * Per the IBM-Decimal spec, integer power is computed by repeated
   * squaring with internal working precision = `precision + 1 + log10(|n|)`,
   * then the final result is rounded back to `precision`. This is what
   * makes byte-equal parity with Python's `**` work — a naive
   * "round-to-precision-at-each-step" pow accumulates more rounding
   * error than `**` does.
   *
   * - For `n >= 0`: fast exponentiation at extended precision, final round.
   * - For `n < 0`: `1 / self.pow(|n|)`, final division also at extended
   *   precision so the round-trip is symmetric.
   */
  pow(n, precision = DECIMAL_CONTEXT_PRECISION) {
    if (!Number.isInteger(n)) {
      throw new Error(`Decimal.pow: integer exponent required, got ${n}`);
    }
    if (n === 0) {
      return new _Decimal("1");
    }
    const absN = Math.abs(n);
    const expDigits = absN.toString().length;
    const workPrec = precision + 1 + expDigits;
    if (n < 0) {
      const positive = powAtPrecision(this, -n, workPrec);
      const inv = new _Decimal("1").div(positive, workPrec);
      return roundToPrecision(inv, precision);
    }
    const result = powAtPrecision(this, n, workPrec);
    return roundToPrecision(result, precision);
  }
  /**
   * Quantize to the exponent of `pattern`, with HALF_EVEN rounding.
   *
   * Mirrors `Decimal.quantize(pattern, rounding=ROUND_HALF_EVEN)`. The result
   * has the *same exponent* as `pattern` regardless of input scale, which is
   * the property the finance modules rely on for two-decimal cents.
   */
  quantize(pattern, _rounding = ROUND_HALF_EVEN) {
    const p = toDecimal(pattern);
    const targetExp = p.exp;
    if (this.exp === targetExp) {
      return this;
    }
    if (this.exp > targetExp) {
      const diff = this.exp - targetExp;
      return rebuild(this.coef * pow10(diff), targetExp);
    }
    const drop = targetExp - this.exp;
    const rounded = roundHalfEven(this.coef, drop);
    return rebuild(rounded, targetExp);
  }
  /**
   * Convert to integer Decimal (exponent = 0) using HALF_EVEN. Mirrors
   * Python's `Decimal.to_integral_value(rounding=ROUND_HALF_EVEN)`.
   */
  toIntegralValue() {
    return this.quantize(new _Decimal("1"));
  }
  /** Coerce to a plain JS `number`. Use only for non-money quantities (loop
   *  counters, comparisons against integers). Loses precision for values
   *  beyond `Number.MAX_SAFE_INTEGER`. */
  toNumber() {
    return Number(this.toString());
  }
  // --- Formatting ----------------------------------------------------------
  /**
   * Format identically to Python's `format(Decimal, "f")`. This is the
   * function that produces byte-equal JSON output against the Python golden
   * file, so any change here MUST be reflected in the parity test.
   *
   * Rules:
   *
   * - Always non-exponential.
   * - Scale (number of fractional digits) = `max(0, -exp)`.
   * - When `exp > 0` (e.g. coefficient 12, exp 2 → 1200), pads zeros on the
   *   right and emits no decimal point: `"1200"`.
   * - When `exp == 0`, no decimal point: `"12"`.
   * - When `exp < 0`, emits exactly `-exp` fractional digits (zero-padded
   *   on the left if needed): `Decimal("0.05")` → `"0.05"`,
   *   `Decimal("0.000")` → `"0.000"`.
   * - Sign: `-` prefix iff coef < 0. Negative zero collapses to `"0"`
   *   when the coefficient is exactly zero (we don't store negative zero).
   */
  toString() {
    return formatPythonFixed(this.coef, this.exp);
  }
  /** Alias matching the function name in the spec. */
  format() {
    return this.toString();
  }
};
function toDecimal(value) {
  if (value instanceof Decimal) return value;
  return new Decimal(value);
}
function parseDecimalString(s) {
  if (s.length === 0) {
    throw new Error("Decimal: empty string");
  }
  let sign = 1n;
  let i = 0;
  if (s[i] === "+") {
    i++;
  } else if (s[i] === "-") {
    sign = -1n;
    i++;
  }
  let intPart = "";
  let fracPart = "";
  let sawDigit = false;
  let inFrac = false;
  for (; i < s.length; i++) {
    const ch = s[i];
    if (ch === "." && !inFrac) {
      inFrac = true;
      continue;
    }
    if (ch === void 0 || ch < "0" || ch > "9") {
      throw new Error(`Decimal: invalid character ${JSON.stringify(ch)} in ${JSON.stringify(s)}`);
    }
    sawDigit = true;
    if (inFrac) {
      fracPart += ch;
    } else {
      intPart += ch;
    }
  }
  if (!sawDigit) {
    throw new Error(`Decimal: no digits in ${JSON.stringify(s)}`);
  }
  const digits = (intPart + fracPart).replace(/^0+(?=\d)/, "");
  const coefAbs = digits === "" ? ZERO_BI : BigInt(digits);
  const coef = coefAbs === ZERO_BI ? ZERO_BI : sign * coefAbs;
  const exp = -fracPart.length;
  return { coef, exp };
}
function powAtPrecision(base, n, precision) {
  let result = new Decimal("1");
  let b = base;
  let k = n;
  while (k > 0) {
    if ((k & 1) === 1) {
      result = result.mul(b, precision);
    }
    k >>= 1;
    if (k > 0) {
      b = b.mul(b, precision);
    }
  }
  return result;
}
function roundToPrecision(d, precision) {
  if (d.coef === ZERO_BI) return d;
  let coef = d.coef;
  let exp = d.exp;
  for (; ; ) {
    const absCoef = coef < ZERO_BI ? -coef : coef;
    const digits = absCoef.toString().length;
    if (digits <= precision) {
      return rebuild(coef, exp);
    }
    const drop = digits - precision;
    coef = roundHalfEven(coef, drop);
    exp += drop;
    if (coef === ZERO_BI) {
      return rebuild(ZERO_BI, exp);
    }
  }
}
function rebuild(coef, exp) {
  const d = Object.create(Decimal.prototype);
  const safeCoef = coef === ZERO_BI ? ZERO_BI : coef;
  Object.defineProperty(d, "coef", { value: safeCoef, enumerable: true });
  Object.defineProperty(d, "exp", { value: exp, enumerable: true });
  return d;
}
function formatPythonFixed(coef, exp) {
  if (coef === ZERO_BI) {
    if (exp >= 0) return "0";
    const places2 = -exp;
    return "0." + "0".repeat(places2);
  }
  const sign = coef < ZERO_BI ? "-" : "";
  const absDigits = (coef < ZERO_BI ? -coef : coef).toString();
  if (exp === 0) {
    return sign + absDigits;
  }
  if (exp > 0) {
    return sign + absDigits + "0".repeat(exp);
  }
  const places = -exp;
  if (absDigits.length <= places) {
    const leading = "0".repeat(places - absDigits.length);
    return sign + "0." + leading + absDigits;
  }
  const intPart = absDigits.slice(0, absDigits.length - places);
  const fracPart = absDigits.slice(absDigits.length - places);
  return sign + intPart + "." + fracPart;
}
function maxDecimal(values) {
  if (values.length === 0) {
    throw new Error("maxDecimal: empty input");
  }
  let best = values[0];
  for (let i = 1; i < values.length; i++) {
    const v = values[i];
    if (v.gt(best)) best = v;
  }
  return best;
}

// src/tax_rules.ts
var EFFECTIVE_YEAR = 2026;
var LAST_UPDATED = "2026-05-11";
var CONFORMING_BASELINE_2026 = new Decimal("806500");
var HIGH_BALANCE_CEILING_2026 = new Decimal("1209750");
var COUNTY_LOAN_LIMITS_2026 = {
  alameda: HIGH_BALANCE_CEILING_2026,
  santa_clara: HIGH_BALANCE_CEILING_2026,
  contra_costa: HIGH_BALANCE_CEILING_2026,
  san_mateo: HIGH_BALANCE_CEILING_2026,
  san_francisco: HIGH_BALANCE_CEILING_2026,
  marin: HIGH_BALANCE_CEILING_2026,
  sonoma: HIGH_BALANCE_CEILING_2026,
  napa: HIGH_BALANCE_CEILING_2026,
  solano: HIGH_BALANCE_CEILING_2026
};
var FHA_HIGH_COST_CEILING_2026 = new Decimal("1209750");
var COUNTY_PROPERTY_TAX_RATES_2026 = {
  alameda: new Decimal("0.01155"),
  santa_clara: new Decimal("0.01125"),
  contra_costa: new Decimal("0.01150"),
  san_mateo: new Decimal("0.01140"),
  san_francisco: new Decimal("0.01200"),
  marin: new Decimal("0.01125"),
  sonoma: new Decimal("0.01150"),
  napa: new Decimal("0.01100"),
  solano: new Decimal("0.01125")
};
var PROP_13_ANNUAL_CAP = new Decimal("0.02");
var PROP_13_BASE_RATE = new Decimal("0.01");
var SALT_CAP_2026 = new Decimal("10000");
var PMI_DEFAULT_ANNUAL_RATE = new Decimal("0.0055");
var PMI_LTV_THRESHOLD = new Decimal("0.80");
var DTI_FRONT_END = new Decimal("0.28");
var DTI_BACK_END = new Decimal("0.36");
var MIN_DOWN_PAYMENT_PCT = {
  // Fannie Mae Selling Guide B5-6: standard min 5%.
  conforming: new Decimal("0.05"),
  high_balance: new Decimal("0.05"),
  // Industry-typical jumbo minimum (no GSE backing).
  jumbo: new Decimal("0.10"),
  // HUD 4000.1 II.A.2: 3.5% with FICO ≥ 580.
  fha: new Decimal("0.035")
};
function conformingLimit(county) {
  const v = COUNTY_LOAN_LIMITS_2026[county];
  if (!v) throw new Error(`Unmodeled county: ${county}`);
  return v;
}
function fhaLimit(county) {
  if (county in COUNTY_LOAN_LIMITS_2026) {
    return FHA_HIGH_COST_CEILING_2026;
  }
  throw new Error(`Unmodeled county: ${county}`);
}
function propertyTaxRate(county) {
  const v = COUNTY_PROPERTY_TAX_RATES_2026[county];
  if (!v) throw new Error(`Unmodeled county: ${county}`);
  return v;
}
var JUMBO_NO_LIMIT = new Decimal("999999999999");
function loanLimit(county, loanType) {
  if (loanType === "conforming") {
    return CONFORMING_BASELINE_2026;
  }
  if (loanType === "high_balance") {
    return conformingLimit(county);
  }
  if (loanType === "fha") {
    return fhaLimit(county);
  }
  if (loanType === "jumbo") {
    return JUMBO_NO_LIMIT;
  }
  throw new Error(`Unknown loan_type: ${loanType}`);
}
function isJumboSentinel(d) {
  return d.eq(JUMBO_NO_LIMIT);
}

// src/affordability.ts
var CENT = new Decimal("0.01");
var DOLLAR = new Decimal("1");
var PRICE_EPSILON = new Decimal("1");
var PRICE_CEILING = new Decimal("50000000");
var PRICE_FLOOR = new Decimal("0");
var TWO = new Decimal("2");
var TWELVE = new Decimal("12");
var ZERO = new Decimal("0");
function roundMoney(amount) {
  return amount.quantize(CENT);
}
function roundDollar(amount) {
  return amount.quantize(DOLLAR);
}
function principalAndInterest(loanAmount, annualRate, termYears) {
  if (loanAmount.lte(ZERO)) {
    return new Decimal("0");
  }
  const n = termYears * 12;
  if (annualRate.isZero()) {
    return roundMoney(loanAmount.div(new Decimal(n)));
  }
  const monthlyRate = annualRate.div(TWELVE);
  const onePlusR = new Decimal("1").add(monthlyRate);
  const factor = new Decimal("1").sub(onePlusR.pow(-n));
  const payment = loanAmount.mul(monthlyRate).div(factor);
  return roundMoney(payment);
}
function monthlyCost(price, areaCtx) {
  if (price.lt(ZERO)) {
    throw new Error(`price must be non-negative, got ${price.toString()}`);
  }
  const roundedPrice = roundMoney(price);
  let loanAmount = roundedPrice.sub(areaCtx.down_payment);
  if (loanAmount.lt(ZERO)) {
    loanAmount = new Decimal("0");
  }
  const pAndI = principalAndInterest(loanAmount, areaCtx.rate, areaCtx.term_years);
  const annualTax = roundedPrice.mul(areaCtx.property_tax_rate);
  const tax = roundMoney(annualTax.div(TWELVE));
  const mello = roundMoney(areaCtx.mello_roos_annual.div(TWELVE));
  const hoa = roundMoney(areaCtx.hoa_monthly);
  const annualInsurance = areaCtx.insurance_annual.mul(areaCtx.wildfire_surcharge_multiplier);
  const insurance = roundMoney(annualInsurance.div(TWELVE));
  let ltv;
  if (roundedPrice.gt(ZERO)) {
    ltv = loanAmount.div(roundedPrice);
  } else {
    ltv = new Decimal("0");
  }
  let pmi;
  if (ltv.gt(PMI_LTV_THRESHOLD)) {
    const annualPmi = loanAmount.mul(areaCtx.pmi_annual_rate);
    pmi = roundMoney(annualPmi.div(TWELVE));
  } else {
    pmi = new Decimal("0");
  }
  const total = roundMoney(
    pAndI.add(tax).add(mello).add(hoa).add(insurance).add(pmi)
  );
  return {
    price: roundedPrice,
    p_and_i: pAndI,
    tax,
    mello,
    hoa,
    insurance,
    pmi,
    total
  };
}
function buildAreaCtxFromBuyer(buyer, marketCtx) {
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
    pmi_annual_rate: new Decimal("0.0055")
  };
}
function solveMaxPriceForMonthly(monthlyCap, areaCtx, upperBound = PRICE_CEILING) {
  if (monthlyCap.lte(ZERO)) {
    return new Decimal("0");
  }
  let lo = PRICE_FLOOR;
  let hi = upperBound;
  const floorCost = monthlyCost(areaCtx.down_payment, areaCtx).total;
  if (floorCost.gt(monthlyCap)) {
    return new Decimal("0");
  }
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
function bindingConstraint(comfortable, stretch, maxOverall, maxLoanCapped, cashCapped) {
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
function maxPricePerLoanType(buyer, marketCtx, areaCtx, monthlyCap) {
  const grid = {};
  const dtiCapPrice = solveMaxPriceForMonthly(monthlyCap, areaCtx);
  const loanTypes = ["conforming", "high_balance", "jumbo", "fha"];
  for (const loanType of loanTypes) {
    const principalCeiling = loanLimit(marketCtx.county, loanType);
    let loanPrincipalCap;
    if (isJumboSentinel(principalCeiling)) {
      loanPrincipalCap = PRICE_CEILING;
    } else {
      loanPrincipalCap = buyer.down_payment.add(principalCeiling);
    }
    const minDownPct = MIN_DOWN_PAYMENT_PCT[loanType];
    let cashCap;
    if (minDownPct.gt(ZERO)) {
      cashCap = buyer.down_payment.div(minDownPct);
    } else {
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
function affordability(buyer, marketCtx) {
  if (buyer.annual_income.lt(ZERO)) {
    throw new Error(
      `annual_income must be non-negative, got ${buyer.annual_income.toString()}`
    );
  }
  if (buyer.down_payment.lt(ZERO)) {
    throw new Error(
      `down_payment must be non-negative, got ${buyer.down_payment.toString()}`
    );
  }
  if (buyer.monthly_debts.lt(ZERO)) {
    throw new Error(
      `monthly_debts must be non-negative, got ${buyer.monthly_debts.toString()}`
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
  const values = Object.values(maxByLoanType);
  const maxOverall = values.length > 0 ? maxDecimal(values) : new Decimal("0");
  const cashCappedRaw = buyer.down_payment.div(MIN_DOWN_PAYMENT_PCT.conforming);
  const highBalanceMax = maxByLoanType.high_balance;
  if (!highBalanceMax) {
    throw new Error("internal: high_balance entry missing from max_by_loan_type");
  }
  const binding = bindingConstraint(
    comfortablePrice,
    stretchPrice,
    maxOverall,
    highBalanceMax,
    roundDollar(cashCappedRaw)
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
    stretch_monthly: stretchMonthly
  };
}

// src/confidence.ts
var SAMPLE_THRESHOLDS = {
  median_sale_price: { high: 30, medium: 10 },
  median_list_price: { high: 30, medium: 10 },
  median_ppsf: { high: 30, medium: 10 },
  median_dom: { high: 20, medium: 8 },
  sale_to_list_ratio: { high: 30, medium: 10 },
  months_of_supply: { high: 5, medium: 2 },
  pct_with_price_drops: { high: 50, medium: 20 },
  school_premium: { high: 20, medium: 10 }
};
var DISAGREEMENT_THRESHOLDS = {
  median_sale_price: [new Decimal("0.05"), 15],
  median_list_price: [new Decimal("0.05"), 15],
  median_ppsf: [new Decimal("0.05"), 15],
  median_dom: [new Decimal("0.30"), 20],
  active_listings: [new Decimal("0.10"), 10],
  inventory: [new Decimal("0.10"), 10],
  school_rating: null,
  // Mortgage-rate disagreement is in absolute percentage points; we
  // special-case it in `confidenceScore` because the unit differs.
  mortgage_rate: null,
  sale_to_list_ratio: [new Decimal("0.05"), 10],
  months_of_supply: [new Decimal("0.10"), 10],
  pct_with_price_drops: [new Decimal("0.10"), 10]
};
var RATE_DISAGREEMENT_THRESHOLD_PP = new Decimal("0.0025");
var RATE_DISAGREEMENT_PENALTY = 10;
var STALENESS_GRACE_DAYS = 14;
var STALENESS_DECAY_PER_DAY = 1;
var TIER_HIGH_CUTOFF = 75;
var TIER_MEDIUM_CUTOFF = 45;
function bucketScore(score) {
  if (score >= TIER_HIGH_CUTOFF) return "high";
  if (score >= TIER_MEDIUM_CUTOFF) return "medium";
  return "low";
}
function sampleSizePenalty(metricName, sampleSize) {
  const thresholds = SAMPLE_THRESHOLDS[metricName];
  if (thresholds === void 0) {
    return [0, `no per-metric threshold defined for '${metricName}'`];
  }
  if (sampleSize === null) {
    return [30, `sample size unknown for '${metricName}'`];
  }
  const { high, medium } = thresholds;
  if (sampleSize >= high) {
    return [0, null];
  }
  if (sampleSize >= medium) {
    return [
      15,
      `sample size ${sampleSize} is medium-confidence (need ${high}+ for high)`
    ];
  }
  return [
    35,
    `sample size ${sampleSize} is below low-confidence threshold (${medium})`
  ];
}
function stalenessPenalty(ageDays) {
  if (ageDays <= STALENESS_GRACE_DAYS) {
    return [0, null];
  }
  const decay = (ageDays - STALENESS_GRACE_DAYS) * STALENESS_DECAY_PER_DAY;
  return [
    decay,
    `data is ${ageDays}d old (>${STALENESS_GRACE_DAYS}d grace; -${decay})`
  ];
}
function formatThresholdPct(threshold) {
  return threshold.mul(new Decimal("100")).quantize(new Decimal("0.1")).toString();
}
function disagreementPenalty(metricName, disagreement) {
  if (disagreement === null || disagreement === void 0) {
    return [0, null];
  }
  const delta = toDecimal(typeof disagreement === "number" ? String(disagreement) : disagreement);
  if (metricName === "mortgage_rate") {
    if (delta.abs().gt(RATE_DISAGREEMENT_THRESHOLD_PP)) {
      return [
        RATE_DISAGREEMENT_PENALTY,
        `mortgage-rate sources disagree by ${delta.toString()} (>${RATE_DISAGREEMENT_THRESHOLD_PP.toString()}pp)`
      ];
    }
    return [0, null];
  }
  const thresholdPair = DISAGREEMENT_THRESHOLDS[metricName];
  if (thresholdPair === void 0 || thresholdPair === null) {
    return [0, null];
  }
  const [threshold, penalty] = thresholdPair;
  if (delta.abs().gt(threshold)) {
    const pct = delta.abs().mul(new Decimal("100")).quantize(new Decimal("0.1"));
    return [
      penalty,
      `sources disagree by ${pct.toString()}% (>${formatThresholdPct(threshold)}% threshold) on '${metricName}'`
    ];
  }
  return [0, null];
}
function confidenceScore(metric, ageDays, disagreement) {
  if (ageDays < 0) {
    throw new Error(`age_days must be non-negative, got ${ageDays}`);
  }
  if (metric.value === null) {
    return {
      score: 0,
      tier: "low",
      reasons: [`no value reported for '${metric.metric_name}'`]
    };
  }
  let score = 100;
  const reasons = [];
  const [samplePenalty, sampleReason] = sampleSizePenalty(
    metric.metric_name,
    metric.sample_size
  );
  score -= samplePenalty;
  if (sampleReason !== null) reasons.push(sampleReason);
  const [stalePenalty, staleReason] = stalenessPenalty(ageDays);
  score -= stalePenalty;
  if (staleReason !== null) reasons.push(staleReason);
  const [dPenalty, dReason] = disagreementPenalty(metric.metric_name, disagreement);
  score -= dPenalty;
  if (dReason !== null) reasons.push(dReason);
  if (score < 0) score = 0;
  if (score > 100) score = 100;
  return { score, tier: bucketScore(score), reasons };
}

// src/phase_weights.ts
var W1_S2L = new Decimal("600");
var W2_INV_PRESSURE = new Decimal("20");
var W3_DOM_FALLING = new Decimal("3");
var W4_PDROP = new Decimal("100");
var W5_INV_OVERHANG = new Decimal("20");
var W6_DOM_RISING = new Decimal("3");
var W7_INV_YOY = new Decimal("100");
var WEIGHTS = {
  w1_s2l: W1_S2L,
  w2_inv_pressure: W2_INV_PRESSURE,
  w3_dom_falling: W3_DOM_FALLING,
  w4_pdrop: W4_PDROP,
  w5_inv_overhang: W5_INV_OVERHANG,
  w6_dom_rising: W6_DOM_RISING,
  w7_inv_yoy: W7_INV_YOY
};
var PRESSURE_MIN = new Decimal("0");
var PRESSURE_MAX = new Decimal("100");

// src/timing.ts
var ZERO2 = new Decimal("0");
var THREE = new Decimal("3");
var TWELVE2 = new Decimal("12");
var HUNDRED = new Decimal("100");
var ONE = new Decimal("1");
var TWO2 = new Decimal("2");
var PCT_FIXED = new Decimal("0.01");
function clamp(value, low, high) {
  if (value.lt(low)) return low;
  if (value.gt(high)) return high;
  return value;
}
function bucketConfidence(score) {
  if (score >= TIER_HIGH_CUTOFF) return "high";
  if (score >= TIER_MEDIUM_CUTOFF) return "medium";
  return "low";
}
function computeComponents(snapshot, history) {
  const domTrend = new Decimal(snapshot.median_dom - history.baseline_dom);
  return {
    mos: snapshot.months_of_supply,
    s2l_4w: snapshot.s2l_4w,
    s2l_12w: snapshot.s2l_12w,
    pdrop: snapshot.pct_with_price_drops,
    dom_trend: domTrend,
    inv_yoy: history.inv_yoy
  };
}
function buyerPressure(components) {
  let s2lTerm = components.s2l_4w.sub(ONE).mul(W1_S2L);
  if (s2lTerm.lt(ZERO2)) {
    s2lTerm = ZERO2;
  }
  const mosShortage = THREE.sub(components.mos);
  const mosTerm = (mosShortage.gt(ZERO2) ? mosShortage : ZERO2).mul(W2_INV_PRESSURE);
  const negDomTrend = components.dom_trend.neg();
  const domTerm = (negDomTrend.gt(ZERO2) ? negDomTrend : ZERO2).mul(W3_DOM_FALLING);
  return clamp(s2lTerm.add(mosTerm).add(domTerm), PRESSURE_MIN, PRESSURE_MAX);
}
function sellerPressure(components) {
  let pdropTerm = components.pdrop.mul(W4_PDROP);
  if (pdropTerm.lt(ZERO2)) {
    pdropTerm = ZERO2;
  }
  const mosOverhang = components.mos.sub(THREE);
  const overhangTerm = (mosOverhang.gt(ZERO2) ? mosOverhang : ZERO2).mul(W5_INV_OVERHANG);
  const domTrend = components.dom_trend;
  const domRisingTerm = (domTrend.gt(ZERO2) ? domTrend : ZERO2).mul(W6_DOM_RISING);
  const invYoy = components.inv_yoy;
  const invYoyTerm = (invYoy.gt(ZERO2) ? invYoy : ZERO2).mul(W7_INV_YOY);
  return clamp(
    pdropTerm.add(overhangTerm).add(domRisingTerm).add(invYoyTerm),
    PRESSURE_MIN,
    PRESSURE_MAX
  );
}
function clockPosition(buyerP, sellerP) {
  const diff = buyerP.sub(sellerP);
  const normalized = diff.add(HUNDRED).div(HUNDRED.mul(TWO2));
  let position;
  if (normalized.gte(new Decimal("0.5"))) {
    position = TWELVE2.sub(ONE.sub(normalized).mul(new Decimal("18")));
  } else {
    position = THREE.add(new Decimal("0.5").sub(normalized).mul(new Decimal("6")));
  }
  if (position.lt(ZERO2)) position = ZERO2;
  if (position.gt(TWELVE2)) position = TWELVE2;
  return position.quantize(PCT_FIXED);
}
function classifyPhase(buyerP, sellerP, history) {
  const SIXTY = new Decimal("60");
  const FORTY = new Decimal("40");
  const THIRTY = new Decimal("30");
  const TWENTY = new Decimal("20");
  if (buyerP.gte(SIXTY) && sellerP.lt(FORTY)) {
    return "peak";
  }
  if (sellerP.gte(SIXTY) && buyerP.lt(FORTY)) {
    return "trough";
  }
  if (history.previous_phase === "trough") {
    return "recovery";
  }
  if (history.previous_phase === "recovery") {
    if (buyerP.gt(sellerP.add(TWENTY))) {
      return "peak";
    }
    return "recovery";
  }
  if (history.previous_phase === "peak") {
    return "cooling";
  }
  if (history.previous_phase === "cooling") {
    if (sellerP.lt(THIRTY) && buyerP.lt(FORTY)) {
      return "recovery";
    }
    return "cooling";
  }
  if (buyerP.gt(sellerP)) {
    return "cooling";
  }
  if (sellerP.gt(buyerP)) {
    return "recovery";
  }
  return "cooling";
}
function computePhase(snapshot, history) {
  if (snapshot.sample_size < 0) {
    throw new Error(
      `sample_size must be non-negative, got ${snapshot.sample_size}`
    );
  }
  if (snapshot.confidence_score < 0 || snapshot.confidence_score > 100) {
    throw new Error(
      `confidence_score must be in [0, 100], got ${snapshot.confidence_score}`
    );
  }
  const components = computeComponents(snapshot, history);
  const buyerP = buyerPressure(components);
  const sellerP = sellerPressure(components);
  const clock = clockPosition(buyerP, sellerP);
  const confidence = bucketConfidence(snapshot.confidence_score);
  let phase;
  if (confidence === "low") {
    phase = "unknown";
  } else {
    phase = classifyPhase(buyerP, sellerP, history);
  }
  return {
    phase,
    clock_position: clock,
    buyer_pressure: Number(buyerP.toIntegralValue().toString()),
    seller_pressure: Number(sellerP.toIntegralValue().toString()),
    components,
    confidence
  };
}

// src/cost_of_waiting.ts
var ZERO3 = new Decimal("0");
var ONE2 = new Decimal("1");
var TWELVE3 = new Decimal("12");
var TWO3 = new Decimal("2");
var CENT2 = new Decimal("0.01");
var RATE_QUANTUM = new Decimal("0.0001");
function roundMoney2(amount) {
  return amount.quantize(CENT2);
}
function laterPrice(targetPrice, annualAppreciation, months) {
  const monthlyRate = annualAppreciation.div(TWELVE3);
  const factor = ONE2.add(monthlyRate).pow(months);
  return targetPrice.mul(factor);
}
function paymentAt(price, areaCtx, rate) {
  const derived = {
    county: areaCtx.county,
    property_tax_rate: areaCtx.property_tax_rate,
    mello_roos_annual: areaCtx.mello_roos_annual,
    hoa_monthly: areaCtx.hoa_monthly,
    insurance_annual: areaCtx.insurance_annual,
    wildfire_surcharge_multiplier: areaCtx.wildfire_surcharge_multiplier,
    rate,
    term_years: areaCtx.term_years,
    down_payment: areaCtx.down_payment,
    pmi_annual_rate: areaCtx.pmi_annual_rate
  };
  return monthlyCost(price, derived).total;
}
function impact(appreciationChange, rentPaid, monthlyPaymentNow, monthlyPaymentLater, months) {
  const paymentDelta = monthlyPaymentLater.sub(monthlyPaymentNow).mul(new Decimal(months));
  return appreciationChange.add(rentPaid).add(paymentDelta);
}
function breakEvenRateDrop(_targetPrice, later, appreciationChange, rentPaid, monthlyPaymentNow, areaCtx, months) {
  const monthlyAtZero = paymentAt(later, areaCtx, areaCtx.rate);
  const impactAtZero = impact(
    appreciationChange,
    rentPaid,
    monthlyPaymentNow,
    monthlyAtZero,
    months
  );
  if (impactAtZero.lte(ZERO3)) {
    return ZERO3;
  }
  let lo = ZERO3;
  let hi = new Decimal("0.05");
  const epsilon = new Decimal("50");
  const monthlyAtHi = paymentAt(later, areaCtx, areaCtx.rate.sub(hi));
  const impactAtHi = impact(
    appreciationChange,
    rentPaid,
    monthlyPaymentNow,
    monthlyAtHi,
    months
  );
  if (impactAtHi.gt(ZERO3)) {
    return hi;
  }
  const minStep = new Decimal("0.00005");
  while (hi.sub(lo).gt(minStep)) {
    const mid = hi.add(lo).div(TWO3);
    const monthlyAtMid = paymentAt(later, areaCtx, areaCtx.rate.sub(mid));
    const impactAtMid = impact(
      appreciationChange,
      rentPaid,
      monthlyPaymentNow,
      monthlyAtMid,
      months
    );
    if (impactAtMid.abs().lt(epsilon)) {
      return mid.quantize(RATE_QUANTUM);
    }
    if (impactAtMid.gt(ZERO3)) {
      lo = mid;
    } else {
      hi = mid;
    }
  }
  return hi.add(lo).div(TWO3).quantize(RATE_QUANTUM);
}
function costOfWaiting(buyer, _areaId, params) {
  if (params.target_price.lte(ZERO3)) {
    throw new Error(
      `target_price must be positive, got ${params.target_price.toString()}`
    );
  }
  if (params.wait_horizon_months <= 0) {
    throw new Error(
      `wait_horizon_months must be positive, got ${params.wait_horizon_months}`
    );
  }
  if (buyer.term_years <= 0) {
    throw new Error(`term_years must be positive, got ${buyer.term_years}`);
  }
  const months = params.wait_horizon_months;
  const targetPrice = params.target_price;
  const monthlyPaymentNow = paymentAt(targetPrice, params.area_ctx, params.current_rate);
  const rentPaidDuringWait = roundMoney2(params.current_rent.mul(new Decimal(months)));
  const cells = [];
  for (const appreciationAnnual of params.appreciation_scenarios) {
    const row = [];
    const later = laterPrice(targetPrice, appreciationAnnual, months);
    const appreciationChangeDollars = roundMoney2(later.sub(targetPrice));
    for (const rateChange of params.rate_scenarios) {
      const laterRate = params.current_rate.add(rateChange);
      const monthlyPaymentLater = paymentAt(later, params.area_ctx, laterRate);
      const cumulative = roundMoney2(
        monthlyPaymentLater.sub(monthlyPaymentNow).mul(new Decimal(months))
      );
      const net = roundMoney2(
        impact(
          appreciationChangeDollars,
          rentPaidDuringWait,
          monthlyPaymentNow,
          monthlyPaymentLater,
          months
        )
      );
      const breakEven = breakEvenRateDrop(
        targetPrice,
        later,
        appreciationChangeDollars,
        rentPaidDuringWait,
        monthlyPaymentNow,
        params.area_ctx,
        months
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
        net_dollar_impact: net
      });
    }
    cells.push(row);
  }
  return {
    target_price: targetPrice,
    wait_horizon_months: months,
    current_rate: params.current_rate,
    cells
  };
}

export { CONFORMING_BASELINE_2026, COUNTY_LOAN_LIMITS_2026, COUNTY_PROPERTY_TAX_RATES_2026, DISAGREEMENT_THRESHOLDS, DTI_BACK_END, DTI_FRONT_END, Decimal, EFFECTIVE_YEAR, FHA_HIGH_COST_CEILING_2026, HIGH_BALANCE_CEILING_2026, LAST_UPDATED, MIN_DOWN_PAYMENT_PCT, PMI_DEFAULT_ANNUAL_RATE, PMI_LTV_THRESHOLD, PRESSURE_MAX, PRESSURE_MIN, PROP_13_ANNUAL_CAP, PROP_13_BASE_RATE, RATE_DISAGREEMENT_PENALTY, RATE_DISAGREEMENT_THRESHOLD_PP, ROUND_HALF_EVEN, SALT_CAP_2026, SAMPLE_THRESHOLDS, STALENESS_DECAY_PER_DAY, STALENESS_GRACE_DAYS, TIER_HIGH_CUTOFF, TIER_MEDIUM_CUTOFF, W1_S2L, W2_INV_PRESSURE, W3_DOM_FALLING, W4_PDROP, W5_INV_OVERHANG, W6_DOM_RISING, W7_INV_YOY, WEIGHTS, affordability, computePhase, confidenceScore, conformingLimit, costOfWaiting, fhaLimit, loanLimit, monthlyCost, principalAndInterest, propertyTaxRate };
//# sourceMappingURL=index.js.map
//# sourceMappingURL=index.js.map