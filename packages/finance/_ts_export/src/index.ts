/**
 * `@bayre/finance` — TypeScript mirror of `packages/finance/` (Python).
 *
 * Per `docs/contracts.md` C3, this package exports the same five pure
 * functions as the Python implementation, with byte-equal JSON output
 * parity verified in CI against the shared golden file
 * `packages/finance/tests/golden/{inputs,outputs}.json`.
 *
 * No I/O, no clock, no random. Browser-bundleable: zero runtime
 * dependencies on other workspace packages.
 */

export { Decimal, ROUND_HALF_EVEN, type DecimalLike, type RoundingMode } from "./decimal.js";

export {
  affordability,
  monthlyCost,
  principalAndInterest,
} from "./affordability.js";

export { computePhase } from "./timing.js";

export { costOfWaiting } from "./cost_of_waiting.js";

export {
  confidenceScore,
  SAMPLE_THRESHOLDS,
  DISAGREEMENT_THRESHOLDS,
  RATE_DISAGREEMENT_THRESHOLD_PP,
  RATE_DISAGREEMENT_PENALTY,
  STALENESS_GRACE_DAYS,
  STALENESS_DECAY_PER_DAY,
  TIER_HIGH_CUTOFF,
  TIER_MEDIUM_CUTOFF,
} from "./confidence.js";

export {
  CONFORMING_BASELINE_2026,
  COUNTY_LOAN_LIMITS_2026,
  COUNTY_PROPERTY_TAX_RATES_2026,
  DTI_BACK_END,
  DTI_FRONT_END,
  EFFECTIVE_YEAR,
  FHA_HIGH_COST_CEILING_2026,
  HIGH_BALANCE_CEILING_2026,
  LAST_UPDATED,
  MIN_DOWN_PAYMENT_PCT,
  PMI_DEFAULT_ANNUAL_RATE,
  PMI_LTV_THRESHOLD,
  PROP_13_ANNUAL_CAP,
  PROP_13_BASE_RATE,
  SALT_CAP_2026,
  conformingLimit,
  fhaLimit,
  loanLimit,
  propertyTaxRate,
} from "./tax_rules.js";

export {
  W1_S2L,
  W2_INV_PRESSURE,
  W3_DOM_FALLING,
  W4_PDROP,
  W5_INV_OVERHANG,
  W6_DOM_RISING,
  W7_INV_YOY,
  WEIGHTS,
  PRESSURE_MIN,
  PRESSURE_MAX,
} from "./phase_weights.js";

export type {
  AffordabilityResult,
  AreaContext,
  Buyer,
  ConfidenceResult,
  ConfidenceTier,
  County,
  LoanType,
  MarketContext,
  MarketPhase,
  MetricValue,
  MonthlyCost,
  PhaseComponents,
  PhaseHistory,
  PhaseResult,
  SnapshotForPhase,
  WaitCell,
  WaitGrid,
  WaitParams,
} from "./types.js";
