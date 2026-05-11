/**
 * Minimal arbitrary-precision Decimal — a hand-rolled mirror of the slice of
 * Python's `decimal.Decimal` semantics that the finance package depends on.
 *
 * Why hand-rolled (not `decimal.js` / `big.js`):
 *
 * - We need byte-equal JSON output parity with the Python implementation
 *   (`packages/finance/tests/golden/outputs.json`). Python's
 *   `format(Decimal, "f")` preserves the IBM-Decimal *(coefficient, exponent)*
 *   internal representation: `Decimal("1.0")` formats as `"1.0"`, and
 *   `Decimal("0") + Decimal("0.005")` keeps scale 3 → `"0.005"`. None of the
 *   off-the-shelf JS libraries do this without bespoke per-call scale
 *   tracking — at which point a small purpose-built class is simpler and
 *   easier to audit.
 *
 * - Zero runtime dependencies keeps `@bayre/finance` browser-bundleable
 *   without dragging an opaque transitive into the FE.
 *
 * Internal representation: `(coefficient: bigint, exponent: number)`,
 * i.e. *value = coefficient × 10^exponent*. Sign rides on `coefficient`
 * (negative coefficient = negative number; ±0 collapses to zero coefficient).
 *
 * Arithmetic semantics (matching Python's `decimal` module):
 *
 * - `add` / `sub`: result exponent = `min(a.exp, b.exp)`.
 * - `mul`: result exponent = `a.exp + b.exp`.
 * - `div`: uses a context precision (28 sig figs by default) and ROUND_HALF_EVEN.
 * - `pow(int)`: result for positive integer exponent is repeated `mul` (so
 *   `(1+r)**n` keeps the exponent chain Python produces); for negative
 *   exponent it's `1 / pow(positive)`.
 * - `quantize(other, rounding)`: forces the result's exponent to `other.exp`.
 *
 * The default rounding mode is **ROUND_HALF_EVEN** (banker's rounding) — the
 * same default Python's `decimal.getcontext()` uses and the only mode the
 * finance modules ever opt into via `quantize`.
 *
 * This file has no I/O, no `Date`, no globals beyond the precision constant.
 */

/** Precision (significant decimal digits) used for division. Matches the
 *  Python finance package's `getcontext().prec = 28`. */
export const DECIMAL_CONTEXT_PRECISION = 28;

/** Rounding mode = ROUND_HALF_EVEN (banker's rounding). The only mode used in
 *  the Python finance package; we don't expose anything else to keep the
 *  surface tiny. */
export type RoundingMode = "ROUND_HALF_EVEN";
export const ROUND_HALF_EVEN: RoundingMode = "ROUND_HALF_EVEN";

const TEN = 10n;
const ZERO_BI = 0n;
const ONE_BI = 1n;

/** Internal: 10^n as bigint, with a small cache. */
const _powCache: Map<number, bigint> = new Map();
function pow10(n: number): bigint {
  if (n < 0) {
    throw new Error(`pow10 requires non-negative n, got ${n}`);
  }
  const cached = _powCache.get(n);
  if (cached !== undefined) {
    return cached;
  }
  let r = ONE_BI;
  for (let i = 0; i < n; i++) {
    r *= TEN;
  }
  _powCache.set(n, r);
  return r;
}

/** Round a coefficient `c` divided by 10^n using banker's rounding. */
function roundHalfEven(c: bigint, n: number): bigint {
  if (n <= 0) {
    return c;
  }
  const divisor = pow10(n);
  const sign = c < ZERO_BI ? -1n : 1n;
  const absC = c < ZERO_BI ? -c : c;
  const quot = absC / divisor;
  const rem = absC % divisor;
  // Compare 2*rem to divisor.
  const twiceRem = rem * 2n;
  let result: bigint;
  if (twiceRem < divisor) {
    result = quot;
  } else if (twiceRem > divisor) {
    result = quot + ONE_BI;
  } else {
    // Exactly half — round to even.
    result = (quot & ONE_BI) === ZERO_BI ? quot : quot + ONE_BI;
  }
  return sign * result;
}

export class Decimal {
  /** Coefficient (signed). `0n` means zero regardless of `exp`. */
  readonly coef: bigint;
  /** Decimal exponent. Final value = `coef * 10^exp`. */
  readonly exp: number;

  /**
   * Construct from a string (most common — preserves source scale exactly,
   * matching Python's `Decimal("1.0")` behavior), a number (only used in
   * tests and explicitly via `Decimal.fromNumber`), a bigint, or another
   * `Decimal`.
   */
  constructor(input: string | number | bigint | Decimal) {
    if (input instanceof Decimal) {
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
      // We never want silent float drift in the finance modules. Routing a
      // raw number through `String(num)` is dangerous (loses precision); the
      // public API forbids it. Wrap a small set of safe integers here for
      // ergonomic call sites that pass `0`, `1`, `-1`, etc.
      if (!Number.isFinite(input)) {
        throw new Error(`Decimal: non-finite number ${input}`);
      }
      if (!Number.isInteger(input)) {
        throw new Error(
          `Decimal: refusing to construct from non-integer number ${input}; pass a string instead.`,
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

  static fromString(s: string): Decimal {
    return new Decimal(s);
  }

  static fromInt(n: number | bigint): Decimal {
    return new Decimal(typeof n === "bigint" ? n : BigInt(n));
  }

  static get ZERO(): Decimal {
    return new Decimal("0");
  }

  static get ONE(): Decimal {
    return new Decimal("1");
  }

  // --- Sign / comparison ---------------------------------------------------

  isZero(): boolean {
    return this.coef === ZERO_BI;
  }

  isNegative(): boolean {
    return this.coef < ZERO_BI;
  }

  isPositive(): boolean {
    return this.coef > ZERO_BI;
  }

  /** Returns -1, 0, or 1. */
  cmp(other: DecimalLike): number {
    const o = toDecimal(other);
    // Align exponents to compare.
    const minExp = Math.min(this.exp, o.exp);
    const a = this.coef * pow10(this.exp - minExp);
    const b = o.coef * pow10(o.exp - minExp);
    if (a < b) return -1;
    if (a > b) return 1;
    return 0;
  }

  eq(other: DecimalLike): boolean {
    return this.cmp(other) === 0;
  }
  lt(other: DecimalLike): boolean {
    return this.cmp(other) < 0;
  }
  lte(other: DecimalLike): boolean {
    return this.cmp(other) <= 0;
  }
  gt(other: DecimalLike): boolean {
    return this.cmp(other) > 0;
  }
  gte(other: DecimalLike): boolean {
    return this.cmp(other) >= 0;
  }

  abs(): Decimal {
    if (this.coef >= ZERO_BI) return this;
    return rebuild(-this.coef, this.exp);
  }

  neg(): Decimal {
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

  add(other: DecimalLike, precision: number = DECIMAL_CONTEXT_PRECISION): Decimal {
    const o = toDecimal(other);
    const minExp = Math.min(this.exp, o.exp);
    const a = this.coef * pow10(this.exp - minExp);
    const b = o.coef * pow10(o.exp - minExp);
    return roundToPrecision(rebuild(a + b, minExp), precision);
  }

  sub(other: DecimalLike, precision: number = DECIMAL_CONTEXT_PRECISION): Decimal {
    const o = toDecimal(other);
    const minExp = Math.min(this.exp, o.exp);
    const a = this.coef * pow10(this.exp - minExp);
    const b = o.coef * pow10(o.exp - minExp);
    return roundToPrecision(rebuild(a - b, minExp), precision);
  }

  mul(other: DecimalLike, precision: number = DECIMAL_CONTEXT_PRECISION): Decimal {
    const o = toDecimal(other);
    return roundToPrecision(
      rebuild(this.coef * o.coef, this.exp + o.exp),
      precision,
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
  div(other: DecimalLike, precision: number = DECIMAL_CONTEXT_PRECISION): Decimal {
    const o = toDecimal(other);
    if (o.coef === ZERO_BI) {
      throw new Error("Decimal.div: division by zero");
    }
    if (this.coef === ZERO_BI) {
      // Python: `Decimal("0") / Decimal("...")` returns `Decimal("0E-...")`
      // with an exponent equal to `a.exp - b.exp`. For our finance use the
      // bare-zero form is sufficient — the result only ever feeds into
      // further arithmetic + quantize, so the exponent is overwritten
      // before formatting.
      return new Decimal("0");
    }
    // Determine sign + work with magnitudes.
    const signA = this.coef < ZERO_BI ? -1n : 1n;
    const signB = o.coef < ZERO_BI ? -1n : 1n;
    const sign = signA * signB;
    const a = this.coef < ZERO_BI ? -this.coef : this.coef;
    const b = o.coef < ZERO_BI ? -o.coef : o.coef;

    // Initial integer division.
    let q = a / b;
    let r = a % b;
    let exp = this.exp - o.exp;

    if (r === ZERO_BI) {
      // Exact at the natural exponent. Emit and we're done — Python
      // collapses to the shortest representation here.
      return rebuild(sign * q, exp);
    }

    // Scale up the remainder one digit at a time until either we hit
    // exact (r == 0) or we've emitted `precision` significant digits.
    // While `q == 0` (the result is < 1), scaling up does NOT count
    // toward precision — we're just moving the leading nonzero digit
    // into place. This mirrors Python's behavior on `0.001 / 4`.
    while (r !== ZERO_BI) {
      const qDigits = q === ZERO_BI ? 0 : q.toString().length;
      if (qDigits >= precision) {
        // Round-and-stop: use the current remainder to decide.
        // remainder = r / b (still); HALF_EVEN: compare 2r to b.
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

    // If we accumulated more than `precision` digits (e.g. by ending the
    // loop with q just-overflowed), trim back with HALF_EVEN.
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
  pow(n: number, precision: number = DECIMAL_CONTEXT_PRECISION): Decimal {
    if (!Number.isInteger(n)) {
      throw new Error(`Decimal.pow: integer exponent required, got ${n}`);
    }
    if (n === 0) {
      return new Decimal("1");
    }
    // Working precision: prec + 1 + ⌈log10(|n|)⌉. The "+1 + log10(n)"
    // is the IBM spec's bound for integer pow (each multiplication can
    // shed up to 1 digit of precision; n levels deep gives log10(n)
    // extra digits, plus a guard digit).
    const absN = Math.abs(n);
    const expDigits = absN.toString().length;
    const workPrec = precision + 1 + expDigits;

    if (n < 0) {
      const positive = powAtPrecision(this, -n, workPrec);
      const inv = new Decimal("1").div(positive, workPrec);
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
  quantize(pattern: DecimalLike, _rounding: RoundingMode = ROUND_HALF_EVEN): Decimal {
    const p = toDecimal(pattern);
    const targetExp = p.exp;
    if (this.exp === targetExp) {
      return this;
    }
    if (this.exp > targetExp) {
      // Need to increase scale (more decimal places). Scale up coef.
      const diff = this.exp - targetExp;
      return rebuild(this.coef * pow10(diff), targetExp);
    }
    // this.exp < targetExp — need to drop digits with HALF_EVEN.
    const drop = targetExp - this.exp;
    const rounded = roundHalfEven(this.coef, drop);
    return rebuild(rounded, targetExp);
  }

  /**
   * Convert to integer Decimal (exponent = 0) using HALF_EVEN. Mirrors
   * Python's `Decimal.to_integral_value(rounding=ROUND_HALF_EVEN)`.
   */
  toIntegralValue(): Decimal {
    return this.quantize(new Decimal("1"));
  }

  /** Coerce to a plain JS `number`. Use only for non-money quantities (loop
   *  counters, comparisons against integers). Loses precision for values
   *  beyond `Number.MAX_SAFE_INTEGER`. */
  toNumber(): number {
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
  toString(): string {
    return formatPythonFixed(this.coef, this.exp);
  }

  /** Alias matching the function name in the spec. */
  format(): string {
    return this.toString();
  }
}

export type DecimalLike = Decimal | string | number | bigint;

/** Coerce a `DecimalLike` to a `Decimal` (cheap if already one). */
export function toDecimal(value: DecimalLike): Decimal {
  if (value instanceof Decimal) return value;
  return new Decimal(value);
}

/** Internal: parse a decimal string to `(coef, exp)`. Accepts an optional
 *  leading sign and optional decimal point. Rejects exponential forms — the
 *  finance modules never produce them, and parsing them silently would mask
 *  upstream bugs. */
function parseDecimalString(s: string): { coef: bigint; exp: number } {
  if (s.length === 0) {
    throw new Error("Decimal: empty string");
  }
  // Strip leading "+" — Python tolerates it too.
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
    if (ch === undefined || ch < "0" || ch > "9") {
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

/** Internal: fast exponentiation at the supplied precision. The mul calls
 *  pass `precision` through so each squaring step rounds to that width
 *  (not the global 28). Used by `Decimal.pow` for the IBM-spec
 *  extended-precision intermediate chain. */
function powAtPrecision(base: Decimal, n: number, precision: number): Decimal {
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

/** Internal: round a `Decimal` to at most `precision` significant digits
 *  using HALF_EVEN. Mirrors what every IBM-Decimal arithmetic operation
 *  does at the end (under a precision-bounded context).
 *
 *  Edge case: rounding 999…9 carries to 1000…0, which is one more digit.
 *  We re-check after rounding and drop one more if needed. This loop
 *  terminates in at most one extra iteration. */
function roundToPrecision(d: Decimal, precision: number): Decimal {
  if (d.coef === ZERO_BI) return d;
  let coef = d.coef;
  let exp = d.exp;
  for (;;) {
    const absCoef = coef < ZERO_BI ? -coef : coef;
    const digits = absCoef.toString().length;
    if (digits <= precision) {
      return rebuild(coef, exp);
    }
    const drop = digits - precision;
    coef = roundHalfEven(coef, drop);
    exp += drop;
    // Check again — the rounded coef may have one fewer digit (no
    // carry) or, in the carry case, exactly `precision` digits. If it
    // still exceeds (impossible here without further input), the loop
    // safely retries.
    if (coef === ZERO_BI) {
      return rebuild(ZERO_BI, exp);
    }
  }
}

/** Internal: build a `Decimal` from raw `(coef, exp)`. Centralizes the
 *  ±0 normalization so equality and formatting both see one canonical zero
 *  per scale. */
function rebuild(coef: bigint, exp: number): Decimal {
  const d = Object.create(Decimal.prototype) as Decimal;
  // Strip negative zero so `(-1) * 0 = 0` doesn't sneak through.
  const safeCoef = coef === ZERO_BI ? ZERO_BI : coef;
  Object.defineProperty(d, "coef", { value: safeCoef, enumerable: true });
  Object.defineProperty(d, "exp", { value: exp, enumerable: true });
  return d;
}

/**
 * Internal: format `(coef, exp)` exactly the way Python's
 * `format(Decimal, "f")` does. Critical to byte-equal parity — see comments
 * on `Decimal.toString` for the rule set.
 */
function formatPythonFixed(coef: bigint, exp: number): string {
  // Special-case zero: keep scale if exp < 0 (so `Decimal("0.00")` formats
  // as `"0.00"`), otherwise just `"0"`.
  if (coef === ZERO_BI) {
    if (exp >= 0) return "0";
    const places = -exp;
    return "0." + "0".repeat(places);
  }
  const sign = coef < ZERO_BI ? "-" : "";
  const absDigits = (coef < ZERO_BI ? -coef : coef).toString();
  if (exp === 0) {
    return sign + absDigits;
  }
  if (exp > 0) {
    // Right-pad with zeros (e.g. coef=12, exp=2 → "1200"). Python actually
    // emits scientific for positive exp by default, but `format(d, "f")`
    // forces non-scientific.
    return sign + absDigits + "0".repeat(exp);
  }
  // exp < 0 — `(-exp)` fractional digits.
  const places = -exp;
  if (absDigits.length <= places) {
    // 0.000...digits
    const leading = "0".repeat(places - absDigits.length);
    return sign + "0." + leading + absDigits;
  }
  const intPart = absDigits.slice(0, absDigits.length - places);
  const fracPart = absDigits.slice(absDigits.length - places);
  return sign + intPart + "." + fracPart;
}

/** Pick the maximum of a list of Decimals. Throws on empty input. */
export function maxDecimal(values: Decimal[]): Decimal {
  if (values.length === 0) {
    throw new Error("maxDecimal: empty input");
  }
  let best = values[0]!;
  for (let i = 1; i < values.length; i++) {
    const v = values[i]!;
    if (v.gt(best)) best = v;
  }
  return best;
}

/** Pick the minimum of a list of Decimals. Throws on empty input. */
export function minDecimal(values: Decimal[]): Decimal {
  if (values.length === 0) {
    throw new Error("minDecimal: empty input");
  }
  let best = values[0]!;
  for (let i = 1; i < values.length; i++) {
    const v = values[i]!;
    if (v.lt(best)) best = v;
  }
  return best;
}
