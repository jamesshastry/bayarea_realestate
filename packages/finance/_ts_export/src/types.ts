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

import type { Decimal } from "./decimal.js";

// ---------------------------------------------------------------------------
// Common enums / literal aliases
// ---------------------------------------------------------------------------

/** Loan-type discriminator used in `AffordabilityResult.max_by_loan_type`.
 *  The set is fixed by 2026 California FTHB economics — see
 *  `docs/glossary/jumbo.md`. */
export type LoanType = "conforming" | "high_balance" | "jumbo" | "fha";

/** Market-clock phase per `docs/datamodel.md` §6a. `"unknown"` when sample
 *  size or confidence is too low to classify reliably. */
export type MarketPhase = "peak" | "cooling" | "trough" | "recovery" | "unknown";

/** Bucketed confidence tier per `docs/design.md` §5.2. */
export type ConfidenceTier = "low" | "medium" | "high";

/** California counties relevant to Phase-1 conforming-limit rules. The 2026
 *  conforming + high-balance limits in `tax_rules.ts` are pinned per county;
 *  we enumerate only the counties Phase 1 cares about. Adding a new county
 *  is a config change in `tax_rules.ts` AND adding a member here. */
export type County =
  | "alameda"
  | "santa_clara"
  | "contra_costa"
  | "san_mateo"
  | "san_francisco"
  | "marin"
  | "sonoma"
  | "napa"
  | "solano";

// ---------------------------------------------------------------------------
// Affordability inputs / outputs
// ---------------------------------------------------------------------------

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
export interface Buyer {
  annual_income: Decimal;
  monthly_debts: Decimal;
  down_payment: Decimal;
  rate: Decimal;
  term_years: number;
  credit_score_band: string;
  // Tracked separately so the splitting toggle (F-AFF-13) can persist
  // them later. Phase 1 uses only the sum.
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
export interface MarketContext {
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
export interface AreaContext {
  county: County;
  property_tax_rate: Decimal;
  mello_roos_annual: Decimal;
  hoa_monthly: Decimal;
  insurance_annual: Decimal;
  // Wildfire surcharge multiplier applied on top of insurance — 1.0 means
  // no surcharge (per `docs/design.md` §5.1 affordability table).
  wildfire_surcharge_multiplier: Decimal;
  // Loan parameters needed for the P&I and PMI lines.
  rate: Decimal;
  term_years: number;
  down_payment: Decimal;
  // PMI rate as an annual fraction of the original loan balance (per
  // `docs/glossary/pmi.md`); applied while LTV > 80%.
  pmi_annual_rate: Decimal;
}

/**
 * Monthly cost decomposition for a price.
 *
 * Conservation: `p_and_i + tax + mello + hoa + insurance + pmi == total`
 * is asserted by `properties.test.ts`.
 */
export interface MonthlyCost {
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
export interface AffordabilityResult {
  buyer: Buyer;
  market_ctx: MarketContext;
  comfortable: Decimal;
  stretch: Decimal;
  max_by_loan_type: Record<string, Decimal>;
  binding_constraint: "dti_front" | "dti_back" | "loan_limit" | "cash_on_hand";
  comfortable_monthly: MonthlyCost;
  stretch_monthly: MonthlyCost;
}

// ---------------------------------------------------------------------------
// Timing (Market-Clock) inputs / outputs
// ---------------------------------------------------------------------------

/**
 * The minimal slice of `MarketSnapshot` `computePhase` needs.
 *
 * Field names mirror `market_snapshot` columns in `docs/datamodel.md` §6
 * verbatim. `s2l_4w` and `s2l_12w` are the 4-week and 12-week medians of
 * `sale_to_list_ratio` per `docs/design.md` §5.3.1.
 */
export interface SnapshotForPhase {
  months_of_supply: Decimal;
  s2l_4w: Decimal;
  s2l_12w: Decimal;
  pct_with_price_drops: Decimal; // 0–1
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
export interface PhaseHistory {
  baseline_dom: number;
  inv_yoy: Decimal;
  previous_phase: MarketPhase;
}

/**
 * Per-input contributions surfaced to the UI on click. Required by
 * operating principle #1 (show the math) — the user must be able to see
 * exactly what input drove each pressure score.
 */
export interface PhaseComponents {
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
export interface PhaseResult {
  phase: MarketPhase;
  clock_position: Decimal; // 0.0–12.0
  buyer_pressure: number; // 0–100
  seller_pressure: number; // 0–100
  components: PhaseComponents;
  confidence: ConfidenceTier;
}

// ---------------------------------------------------------------------------
// Cost-of-waiting inputs / outputs
// ---------------------------------------------------------------------------

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
export interface WaitParams {
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
export interface WaitCell {
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
export interface WaitGrid {
  target_price: Decimal;
  wait_horizon_months: number;
  current_rate: Decimal;
  cells: WaitCell[][];
}

// ---------------------------------------------------------------------------
// Confidence inputs / outputs
// ---------------------------------------------------------------------------

/**
 * Mirror of `docs/contracts.md` C1's `MetricValue` for the slice
 * `confidenceScore` consumes.
 *
 * Re-declared here (rather than imported from `packages/domain`) to honor
 * the constraint that `packages/finance/` has no dependencies beyond the
 * standard library — see `docs/design.md` §5.
 */
export interface MetricValue {
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
export interface ConfidenceResult {
  score: number;
  tier: ConfidenceTier;
  reasons: string[];
}
