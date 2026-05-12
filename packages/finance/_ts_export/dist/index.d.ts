/** Rounding mode = ROUND_HALF_EVEN (banker's rounding). The only mode used in
 *  the Python finance package; we don't expose anything else to keep the
 *  surface tiny. */
type RoundingMode = "ROUND_HALF_EVEN";
declare const ROUND_HALF_EVEN: RoundingMode;
declare class Decimal {
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
    constructor(input: string | number | bigint | Decimal);
    static fromString(s: string): Decimal;
    static fromInt(n: number | bigint): Decimal;
    static get ZERO(): Decimal;
    static get ONE(): Decimal;
    isZero(): boolean;
    isNegative(): boolean;
    isPositive(): boolean;
    /** Returns -1, 0, or 1. */
    cmp(other: DecimalLike): number;
    eq(other: DecimalLike): boolean;
    lt(other: DecimalLike): boolean;
    lte(other: DecimalLike): boolean;
    gt(other: DecimalLike): boolean;
    gte(other: DecimalLike): boolean;
    abs(): Decimal;
    neg(): Decimal;
    add(other: DecimalLike, precision?: number): Decimal;
    sub(other: DecimalLike, precision?: number): Decimal;
    mul(other: DecimalLike, precision?: number): Decimal;
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
    div(other: DecimalLike, precision?: number): Decimal;
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
    pow(n: number, precision?: number): Decimal;
    /**
     * Quantize to the exponent of `pattern`, with HALF_EVEN rounding.
     *
     * Mirrors `Decimal.quantize(pattern, rounding=ROUND_HALF_EVEN)`. The result
     * has the *same exponent* as `pattern` regardless of input scale, which is
     * the property the finance modules rely on for two-decimal cents.
     */
    quantize(pattern: DecimalLike, _rounding?: RoundingMode): Decimal;
    /**
     * Convert to integer Decimal (exponent = 0) using HALF_EVEN. Mirrors
     * Python's `Decimal.to_integral_value(rounding=ROUND_HALF_EVEN)`.
     */
    toIntegralValue(): Decimal;
    /** Coerce to a plain JS `number`. Use only for non-money quantities (loop
     *  counters, comparisons against integers). Loses precision for values
     *  beyond `Number.MAX_SAFE_INTEGER`. */
    toNumber(): number;
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
    toString(): string;
    /** Alias matching the function name in the spec. */
    format(): string;
}
type DecimalLike = Decimal | string | number | bigint;

/**
 * TypeScript mirror of `packages/finance/_types.py`.
 *
 * Field names are STABLE — golden-file parity with the Python implementation
 * is asserted byte-equal in CI. Renaming a field here is a contract change
 * (per `docs/contracts.md` C3) that requires a coordinated bump on both
 * sides of the Python ↔ TS boundary.
 *
 * Money is `Decimal` (in-tree class — see `decimal.ts`). We never use
 * `number` for currency: the float-drift tax shows up immediately in the
 * golden-file diff.
 *
 * Per `docs/design.md` §5 these are pure data carriers — no methods, no
 * I/O. Every `as_of_date` the user might supply is a field on a payload
 * below, never read from a clock.
 */

/** Loan-type discriminator used in `AffordabilityResult.max_by_loan_type`.
 *  The set is fixed by 2026 California FTHB economics — see
 *  `docs/glossary/jumbo.md`. */
type LoanType = "conforming" | "high_balance" | "jumbo" | "fha";
/** Market-clock phase per `docs/datamodel.md` §6a. `"unknown"` when sample
 *  size or confidence is too low to classify reliably. */
type MarketPhase = "peak" | "cooling" | "trough" | "recovery" | "unknown";
/** Bucketed confidence tier per `docs/design.md` §5.2. */
type ConfidenceTier = "low" | "medium" | "high";
/** California counties relevant to Phase-1 conforming-limit rules. The 2026
 *  conforming + high-balance limits in `tax_rules.ts` are pinned per county;
 *  we enumerate only the counties Phase 1 cares about. Adding a new county
 *  is a config change in `tax_rules.ts` AND adding a member here. */
type County = "alameda" | "santa_clara" | "contra_costa" | "san_mateo" | "san_francisco" | "marin" | "sonoma" | "napa" | "solano";
/**
 * A first-time-home-buyer's financial profile.
 *
 * Money fields are gross USD, `Decimal`. `credit_score_band` matches the
 * FICO bands stored in `buyer.credit_score_band` per `docs/datamodel.md`
 * §8.1 (e.g., `"740-779"`).
 *
 * `rate` is APR as a `Decimal` (e.g., `new Decimal("0.0675")` for 6.75%).
 * `term_years` is whole years (15 or 30 in Phase 1).
 */
interface Buyer {
    annual_income: Decimal;
    monthly_debts: Decimal;
    down_payment: Decimal;
    rate: Decimal;
    term_years: number;
    credit_score_band: string;
    base_income: Decimal | null;
    bonus_income: Decimal | null;
    rsu_income: Decimal | null;
}
/**
 * Per-area market context the affordability calc needs.
 *
 * `county` drives the conforming / high-balance / jumbo cutoffs.
 * `area_median_price` is for sanity-check warnings only — never enters
 * monetary computation.
 */
interface MarketContext {
    county: County;
    area_median_price: Decimal | null;
}
/**
 * Per-area inputs for the `monthlyCost` breakdown.
 *
 * `mello_roos_annual` is the parcel-known annual amount when we have it
 * (per `docs/glossary/mello-roos.md`); when unknown, the caller passes an
 * area-typical estimate. Either way we never silently zero it out.
 */
interface AreaContext {
    county: County;
    property_tax_rate: Decimal;
    mello_roos_annual: Decimal;
    hoa_monthly: Decimal;
    insurance_annual: Decimal;
    wildfire_surcharge_multiplier: Decimal;
    rate: Decimal;
    term_years: number;
    down_payment: Decimal;
    pmi_annual_rate: Decimal;
}
/**
 * Monthly cost decomposition for a price.
 *
 * Conservation: `p_and_i + tax + mello + hoa + insurance + pmi == total`
 * is asserted by `properties.test.ts`.
 */
interface MonthlyCost {
    price: Decimal;
    p_and_i: Decimal;
    tax: Decimal;
    mello: Decimal;
    hoa: Decimal;
    insurance: Decimal;
    pmi: Decimal;
    total: Decimal;
}
/**
 * Affordability output (per F-AFF-02 and C3 in `contracts.md`).
 *
 * `comfortable` and `stretch` are the price points at which the front-end
 * DTI 28% and back-end DTI 36% caps bind, respectively.
 * `max_by_loan_type` is the price ceiling the buyer can finance under each
 * loan-type's principal limit (with the same DTI ceiling applied — we
 * never report a max above the user's DTI capacity).
 *
 * `binding_constraint` names the gating rule for the *maximum* row so the
 * UI can render the operating-principle-#1 "show the math" tooltip.
 */
interface AffordabilityResult {
    buyer: Buyer;
    market_ctx: MarketContext;
    comfortable: Decimal;
    stretch: Decimal;
    max_by_loan_type: Record<string, Decimal>;
    binding_constraint: "dti_front" | "dti_back" | "loan_limit" | "cash_on_hand";
    comfortable_monthly: MonthlyCost;
    stretch_monthly: MonthlyCost;
}
/**
 * The minimal slice of `MarketSnapshot` `computePhase` needs.
 *
 * Field names mirror `market_snapshot` columns in `docs/datamodel.md` §6
 * verbatim. `s2l_4w` and `s2l_12w` are the 4-week and 12-week medians of
 * `sale_to_list_ratio` per `docs/design.md` §5.3.1.
 */
interface SnapshotForPhase {
    months_of_supply: Decimal;
    s2l_4w: Decimal;
    s2l_12w: Decimal;
    pct_with_price_drops: Decimal;
    median_dom: number;
    active_listings: number;
    sample_size: number;
    /** 0–100, integer, inherited from snapshot. */
    confidence_score: number;
}
/**
 * 12-week trailing context for `computePhase`.
 *
 * `baseline_dom` is the 12-week trailing median DOM; `inv_yoy` is active
 * listings YoY change as a fraction (e.g., 0.10 = +10%). `previous_phase`
 * is used for tie-breaking when the (buyer, seller) coordinate sits
 * exactly on a quadrant boundary.
 */
interface PhaseHistory {
    baseline_dom: number;
    inv_yoy: Decimal;
    previous_phase: MarketPhase;
}
/**
 * Per-input contributions surfaced to the UI on click. Required by
 * operating principle #1 (show the math) — the user must be able to see
 * exactly what input drove each pressure score.
 */
interface PhaseComponents {
    mos: Decimal;
    s2l_4w: Decimal;
    s2l_12w: Decimal;
    pdrop: Decimal;
    /** Signed; positive = DOM rising vs. baseline. */
    dom_trend: Decimal;
    inv_yoy: Decimal;
}
/**
 * Output of `computePhase` per `docs/design.md` §5.3.1.
 *
 * `clock_position` is a continuous 0.0–12.0 angle for the Market Clock
 * face. `buyer_pressure` and `seller_pressure` are 0–100 ints (we round
 * once at the boundary so the FE never has to re-derive them).
 */
interface PhaseResult {
    phase: MarketPhase;
    clock_position: Decimal;
    buyer_pressure: number;
    seller_pressure: number;
    components: PhaseComponents;
    confidence: ConfidenceTier;
}
/**
 * Inputs to `costOfWaiting` per `docs/design.md` §5.3.3.
 *
 * `appreciation_scenarios` and `rate_scenarios` are the three points along
 * each axis. Defaults are (-2%, +3%, +6%) annual appreciation and
 * (-50bp, flat, +50bp) rate move, matching the 9-cell grid the UI renders.
 *
 * `current_rate` is today's quoted rate. `current_rent` is what the buyer
 * pays today (used to size `rent_paid_during_wait`).
 *
 * `area_ctx` carries the same tax / insurance / PMI / HOA assumptions the
 * affordability module uses — so the "later" monthly payment is
 * apples-to-apples with the "now" payment.
 */
interface WaitParams {
    target_price: Decimal;
    /** 3, 6, 12, or 24. */
    wait_horizon_months: number;
    current_rate: Decimal;
    current_rent: Decimal;
    area_ctx: AreaContext;
    /** Three appreciation outcomes (annualized). Order is preserved in the
     *  output grid so UI rows are stable. */
    appreciation_scenarios: [Decimal, Decimal, Decimal];
    /** Three rate moves (absolute, decimal — e.g. -0.005 = -50bp). */
    rate_scenarios: [Decimal, Decimal, Decimal];
}
/**
 * One (appreciation × rate) cell in the 9-cell wait grid.
 *
 * `net_dollar_impact`: positive means waiting cost the buyer money,
 * negative means waiting saved money. UI is descriptive — see operating
 * principle #4.
 *
 * `break_even_rate_drop`: the absolute rate drop (decimal) required over
 * `wait_horizon_months` to make `net_dollar_impact == 0`. The UI renders
 * this as "rates would need to drop X bp to break even."
 */
interface WaitCell {
    appreciation_annual: Decimal;
    rate_change: Decimal;
    appreciation_change_dollars: Decimal;
    rent_paid_during_wait: Decimal;
    monthly_payment_now: Decimal;
    monthly_payment_later: Decimal;
    cumulative_savings_or_cost: Decimal;
    break_even_rate_drop: Decimal;
    net_dollar_impact: Decimal;
}
/**
 * The 3×3 wait grid plus its inputs.
 *
 * `cells` is row-major: outer index = appreciation scenario, inner index
 * = rate scenario. The TS port relies on this order — do not sort or
 * reshape downstream.
 */
interface WaitGrid {
    target_price: Decimal;
    wait_horizon_months: number;
    current_rate: Decimal;
    cells: WaitCell[][];
}
/**
 * Mirror of `docs/contracts.md` C1's `MetricValue` for the slice
 * `confidenceScore` consumes.
 *
 * Re-declared here (rather than imported from `packages/domain`) to honor
 * the constraint that `packages/finance/` has no dependencies beyond the
 * standard library — see `docs/design.md` §5.
 */
interface MetricValue {
    value: Decimal | number | null;
    sample_size: number | null;
    unit: string;
    /** The metric key from the per-metric thresholds table in
     *  `docs/design.md` §5.2 (e.g., `"median_sale_price"`). */
    metric_name: string;
}
/**
 * Output of `confidenceScore` per `docs/design.md` §3.3 + §5.2.
 *
 * `score` is 0–100, integer. `tier` is the bucketed view the UI typically
 * renders. `reasons` is an ordered list of short strings explaining
 * penalties (oldest-first), so the "show the math" tooltip can render them
 * verbatim.
 */
interface ConfidenceResult {
    score: number;
    tier: ConfidenceTier;
    reasons: string[];
}

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
declare function principalAndInterest(loanAmount: Decimal, annualRate: Decimal, termYears: number): Decimal;
/**
 * Compute the monthly cost breakdown for a target `price`.
 *
 * Per F-AFF-04, the breakdown components MUST sum to the total. The
 * `properties.test.ts` invariant `monthlyCost.components_sum_to_total`
 * enforces this property over a wide input range.
 */
declare function monthlyCost(price: Decimal, areaCtx: AreaContext): MonthlyCost;
/**
 * Compute affordability triplet for a buyer in a market.
 *
 * Returns `comfortable`, `stretch`, and `max_by_loan_type` per F-AFF-02.
 * Also returns the binding constraint name and the monthly-cost
 * breakdowns at the comfortable + stretch points so the UI can render
 * them without a second function call.
 */
declare function affordability(buyer: Buyer, marketCtx: MarketContext): AffordabilityResult;

/**
 * Market Phase computation per `docs/design.md` §5.3.1 — TS port of
 * `packages/finance/timing.py`.
 *
 * Implements the C3 contract:
 *
 *   computePhase(snapshot, history) -> PhaseResult
 *
 * The function is **deterministic and pure** — same inputs → same output,
 * no clock, no globals. Property tests in `test/properties.test.ts`
 * verify idempotence and the phase-boundary cases.
 */

/**
 * Compute the Market Phase for a snapshot. Per C3 the signature is:
 *
 *   (snapshot: SnapshotForPhase, history: PhaseHistory) -> PhaseResult
 *
 * Confidence handling:
 *
 * - Snapshot's integer `confidence_score` is bucketed into a tier with
 *   the cutoffs from `confidence.ts`.
 * - If the bucketed tier is "low", the returned phase is forced to
 *   "unknown" (components/pressures still surfaced for transparency).
 */
declare function computePhase(snapshot: SnapshotForPhase, history: PhaseHistory): PhaseResult;

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

/**
 * Compute the 9-cell cost-of-waiting grid.
 *
 * Per the C3 contract the signature is
 * `(buyer, area_id, params) -> WaitGrid`.
 *
 * `area_id` is part of the contract for forward compatibility with
 * Phase-3 area-specific defaults; Phase-1 reads only `params`.
 */
declare function costOfWaiting(buyer: Buyer, _areaId: string, params: WaitParams): WaitGrid;

/**
 * Confidence scoring for served metrics — TypeScript port of
 * `packages/finance/confidence.py`. Byte-equal output parity with the
 * Python implementation is verified in `test/golden.test.ts`.
 *
 * The scoring is **deterministic**: same inputs → same output, no clock,
 * no globals. The function returns both the integer 0–100 score and the
 * ordered list of `reasons` that explain the penalties.
 */

interface SampleThresholds {
    high: number;
    medium: number;
}
/** Per `docs/design.md` §5.2. */
declare const SAMPLE_THRESHOLDS: Record<string, SampleThresholds>;
/** Disagreement thresholds (relative, e.g. 0.05 = 5%) and their associated
 *  point penalties — both per `docs/design.md` §3.3. `null` means the
 *  metric is always shown side-by-side with no scalar penalty (e.g.,
 *  `school_rating`). */
declare const DISAGREEMENT_THRESHOLDS: Record<string, [Decimal, number] | null>;
/** Mortgage rate has its own absolute pp threshold (0.25 percentage points). */
declare const RATE_DISAGREEMENT_THRESHOLD_PP: Decimal;
declare const RATE_DISAGREEMENT_PENALTY = 10;
/** Staleness decay grace period in days. */
declare const STALENESS_GRACE_DAYS = 14;
/** Decay per day after grace expires. */
declare const STALENESS_DECAY_PER_DAY = 1;
/** Tier cutoffs (matching `phase_weights.py` documentation). */
declare const TIER_HIGH_CUTOFF = 75;
declare const TIER_MEDIUM_CUTOFF = 45;
/**
 * Compute confidence for a metric value.
 *
 * Per `docs/contracts.md` C3 the signature is fixed:
 *
 *     (metric, age_days, disagreement) -> ConfidenceResult
 *
 * Algorithm: start at 100, subtract sample-size penalty, staleness
 * penalty, and disagreement penalty. Clamp to [0, 100]. Bucket into tier.
 * Concatenate non-null reasons in detection order
 * (sample → staleness → disagreement).
 *
 * Deterministic: no clock, no random, no I/O.
 */
declare function confidenceScore(metric: MetricValue, ageDays: number, disagreement: DecimalLike | null): ConfidenceResult;

/**
 * Pinned constants for 2026 Bay Area real-estate finance.
 *
 * Hand-mirrored from `packages/finance/tax_rules.py` — citations and values
 * MUST match. Anyone updating one side must update the other in the same
 * commit; the golden-file parity tests catch silent drift.
 *
 * Per `docs/design.md` §5: this file is *only* constants and small lookup
 * helpers. No I/O, no parsing, no clock reads. Helpers operate purely on
 * their parameters.
 */

declare const EFFECTIVE_YEAR = 2026;
declare const LAST_UPDATED = "2026-05-11";
/** Baseline conforming (one-unit, single-family) limit, applied nation-wide. */
declare const CONFORMING_BASELINE_2026: Decimal;
/** High-balance ceiling (one-unit) for high-cost-area counties.
 *  Per FHFA: 150% of baseline, rounded to the nearest $50. */
declare const HIGH_BALANCE_CEILING_2026: Decimal;
/** Per-county one-unit conforming limit. Every Bay Area county is a
 *  "high-cost area" → the high-balance ceiling applies. We still
 *  enumerate them per-county so the structure mirrors the FHFA table; if
 *  a future year demotes a county we change one value here. */
declare const COUNTY_LOAN_LIMITS_2026: Record<County, Decimal>;
declare const FHA_HIGH_COST_CEILING_2026: Decimal;
declare const COUNTY_PROPERTY_TAX_RATES_2026: Record<County, Decimal>;
/** 2% per year on assessed value. */
declare const PROP_13_ANNUAL_CAP: Decimal;
/** 1% statewide base rate (ad valorem). */
declare const PROP_13_BASE_RATE: Decimal;
declare const SALT_CAP_2026: Decimal;
declare const PMI_DEFAULT_ANNUAL_RATE: Decimal;
/** PMI applies above this LTV at origination. */
declare const PMI_LTV_THRESHOLD: Decimal;
declare const DTI_FRONT_END: Decimal;
declare const DTI_BACK_END: Decimal;
declare const MIN_DOWN_PAYMENT_PCT: Record<LoanType, Decimal>;
/** Return the 2026 one-unit conforming loan limit for `county`.
 *  Throws for an unmodeled county — that is intentional; we'd rather fail
 *  loudly than silently default to the national baseline (which is wrong
 *  for every Bay Area county). */
declare function conformingLimit(county: County): Decimal;
/** Return the 2026 FHA loan limit for `county`. For all nine Bay Area
 *  counties this equals the FHA high-cost ceiling. */
declare function fhaLimit(county: County): Decimal;
/** Return the 2026 effective property-tax rate for `county`. Use the
 *  parcel's actual `current_tax_rate` when known; this is the fallback
 *  for area-typical estimation. */
declare function propertyTaxRate(county: County): Decimal;
/** Return the principal-balance ceiling for `loan_type` in `county`.
 *  Jumbo has no agency-imposed ceiling — see `JUMBO_NO_LIMIT`. */
declare function loanLimit(county: County, loanType: LoanType): Decimal;

/**
 * Weights for `compute_phase` — hand-mirrored from
 * `packages/finance/phase_weights.py`. Values must stay byte-equal.
 *
 * The Market Phase formula in `docs/design.md` §5.3.1 is:
 *
 *     buyer_pressure  = w1*(s2l - 1) + w2*max(0, 3 - mos) + w3*max(0, -dom_trend)
 *     seller_pressure = w4*pdrop + w5*max(0, mos - 3) + w6*max(0, dom_trend)
 *                        + w7*max(0, inv_yoy)
 *
 * The weights below are **Phase-1 reasonable defaults**; calibration
 * against historical Bay Area data is a Phase-3 task.
 *
 * Each weight is exported as `Decimal` (not `number`) so the entire
 * pressure-score arithmetic stays in `Decimal` and the parity with the
 * Python output is exact.
 */

/** w1 multiplies (s2l - 1). A 0.05 over-bid (s2l = 1.05) → +30 contribution. */
declare const W1_S2L: Decimal;
/** w2 multiplies max(0, 3 - mos). MOS < 3 = textbook seller's-market threshold.
 *  MOS of 1.5 → +30; MOS of 3.0 → 0. */
declare const W2_INV_PRESSURE: Decimal;
/** w3 multiplies max(0, -dom_trend) where dom_trend is the signed Δ in days
 *  vs. the 12-week baseline. A 10-day reduction → +30 contribution. */
declare const W3_DOM_FALLING: Decimal;
/** w4 multiplies pct_with_price_drops (0–1). 0.30 → +30 contribution. */
declare const W4_PDROP: Decimal;
/** w5 multiplies max(0, mos - 3). MOS of 4.5 → +30; MOS of 3.0 → 0. */
declare const W5_INV_OVERHANG: Decimal;
/** w6 multiplies max(0, dom_trend). A 10-day rise → +30 contribution. */
declare const W6_DOM_RISING: Decimal;
/** w7 multiplies max(0, inv_yoy). +0.30 YoY → +30 contribution. */
declare const W7_INV_YOY: Decimal;
declare const WEIGHTS: {
    w1_s2l: Decimal;
    w2_inv_pressure: Decimal;
    w3_dom_falling: Decimal;
    w4_pdrop: Decimal;
    w5_inv_overhang: Decimal;
    w6_dom_rising: Decimal;
    w7_inv_yoy: Decimal;
};
/** Pressure clamps. Both pressure scores are clamped to [0, 100] so the
 *  phase classifier and the UI gauge never see out-of-band values. */
declare const PRESSURE_MIN: Decimal;
declare const PRESSURE_MAX: Decimal;

export { type AffordabilityResult, type AreaContext, type Buyer, CONFORMING_BASELINE_2026, COUNTY_LOAN_LIMITS_2026, COUNTY_PROPERTY_TAX_RATES_2026, type ConfidenceResult, type ConfidenceTier, type County, DISAGREEMENT_THRESHOLDS, DTI_BACK_END, DTI_FRONT_END, Decimal, type DecimalLike, EFFECTIVE_YEAR, FHA_HIGH_COST_CEILING_2026, HIGH_BALANCE_CEILING_2026, LAST_UPDATED, type LoanType, MIN_DOWN_PAYMENT_PCT, type MarketContext, type MarketPhase, type MetricValue, type MonthlyCost, PMI_DEFAULT_ANNUAL_RATE, PMI_LTV_THRESHOLD, PRESSURE_MAX, PRESSURE_MIN, PROP_13_ANNUAL_CAP, PROP_13_BASE_RATE, type PhaseComponents, type PhaseHistory, type PhaseResult, RATE_DISAGREEMENT_PENALTY, RATE_DISAGREEMENT_THRESHOLD_PP, ROUND_HALF_EVEN, type RoundingMode, SALT_CAP_2026, SAMPLE_THRESHOLDS, STALENESS_DECAY_PER_DAY, STALENESS_GRACE_DAYS, type SnapshotForPhase, TIER_HIGH_CUTOFF, TIER_MEDIUM_CUTOFF, W1_S2L, W2_INV_PRESSURE, W3_DOM_FALLING, W4_PDROP, W5_INV_OVERHANG, W6_DOM_RISING, W7_INV_YOY, WEIGHTS, type WaitCell, type WaitGrid, type WaitParams, affordability, computePhase, confidenceScore, conformingLimit, costOfWaiting, fhaLimit, loanLimit, monthlyCost, principalAndInterest, propertyTaxRate };
