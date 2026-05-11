/**
 * Confidence scoring for served metrics — TypeScript port of
 * `packages/finance/confidence.py`. Byte-equal output parity with the
 * Python implementation is verified in `test/golden.test.ts`.
 *
 * The scoring is **deterministic**: same inputs → same output, no clock,
 * no globals. The function returns both the integer 0–100 score and the
 * ordered list of `reasons` that explain the penalties.
 */

import { Decimal, type DecimalLike, toDecimal } from "./decimal.js";
import type { ConfidenceResult, ConfidenceTier, MetricValue } from "./types.js";

interface SampleThresholds {
  high: number;
  medium: number;
}

/** Per `docs/design.md` §5.2. */
export const SAMPLE_THRESHOLDS: Record<string, SampleThresholds> = {
  median_sale_price: { high: 30, medium: 10 },
  median_list_price: { high: 30, medium: 10 },
  median_ppsf: { high: 30, medium: 10 },
  median_dom: { high: 20, medium: 8 },
  sale_to_list_ratio: { high: 30, medium: 10 },
  months_of_supply: { high: 5, medium: 2 },
  pct_with_price_drops: { high: 50, medium: 20 },
  school_premium: { high: 20, medium: 10 },
};

/** Disagreement thresholds (relative, e.g. 0.05 = 5%) and their associated
 *  point penalties — both per `docs/design.md` §3.3. `null` means the
 *  metric is always shown side-by-side with no scalar penalty (e.g.,
 *  `school_rating`). */
export const DISAGREEMENT_THRESHOLDS: Record<string, [Decimal, number] | null> = {
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
  pct_with_price_drops: [new Decimal("0.10"), 10],
};

/** Mortgage rate has its own absolute pp threshold (0.25 percentage points). */
export const RATE_DISAGREEMENT_THRESHOLD_PP = new Decimal("0.0025");
export const RATE_DISAGREEMENT_PENALTY = 10;

/** Staleness decay grace period in days. */
export const STALENESS_GRACE_DAYS = 14;
/** Decay per day after grace expires. */
export const STALENESS_DECAY_PER_DAY = 1;

/** Tier cutoffs (matching `phase_weights.py` documentation). */
export const TIER_HIGH_CUTOFF = 75;
export const TIER_MEDIUM_CUTOFF = 45;

function bucketScore(score: number): ConfidenceTier {
  if (score >= TIER_HIGH_CUTOFF) return "high";
  if (score >= TIER_MEDIUM_CUTOFF) return "medium";
  return "low";
}

function sampleSizePenalty(
  metricName: string,
  sampleSize: number | null,
): [number, string | null] {
  const thresholds = SAMPLE_THRESHOLDS[metricName];
  if (thresholds === undefined) {
    // Unknown metric — no per-metric threshold; we don't penalize on
    // sample size, but we do flag the omission via the reasons list.
    return [0, `no per-metric threshold defined for '${metricName}'`];
  }
  if (sampleSize === null) {
    // Without a sample size we can't bound the standard error.
    return [30, `sample size unknown for '${metricName}'`];
  }
  const { high, medium } = thresholds;
  if (sampleSize >= high) {
    return [0, null];
  }
  if (sampleSize >= medium) {
    return [
      15,
      `sample size ${sampleSize} is medium-confidence (need ${high}+ for high)`,
    ];
  }
  return [
    35,
    `sample size ${sampleSize} is below low-confidence threshold (${medium})`,
  ];
}

function stalenessPenalty(ageDays: number): [number, string | null] {
  if (ageDays <= STALENESS_GRACE_DAYS) {
    return [0, null];
  }
  const decay = (ageDays - STALENESS_GRACE_DAYS) * STALENESS_DECAY_PER_DAY;
  return [
    decay,
    `data is ${ageDays}d old (>${STALENESS_GRACE_DAYS}d grace; -${decay})`,
  ];
}

/** Format a Decimal threshold the way Python's `f"{x * 100:.1f}"` does:
 *  multiply by 100, then format to 1 decimal place. */
function formatThresholdPct(threshold: Decimal): string {
  // (threshold * 100) quantized to 1 decimal place.
  return threshold.mul(new Decimal("100")).quantize(new Decimal("0.1")).toString();
}

function disagreementPenalty(
  metricName: string,
  disagreement: DecimalLike | null,
): [number, string | null] {
  if (disagreement === null || disagreement === undefined) {
    return [0, null];
  }
  // Coerce to Decimal once. Mirrors Python's `Decimal(str(disagreement))`.
  const delta = toDecimal(typeof disagreement === "number" ? String(disagreement) : disagreement);
  if (metricName === "mortgage_rate") {
    if (delta.abs().gt(RATE_DISAGREEMENT_THRESHOLD_PP)) {
      return [
        RATE_DISAGREEMENT_PENALTY,
        `mortgage-rate sources disagree by ${delta.toString()} (>${RATE_DISAGREEMENT_THRESHOLD_PP.toString()}pp)`,
      ];
    }
    return [0, null];
  }
  const thresholdPair = DISAGREEMENT_THRESHOLDS[metricName];
  if (thresholdPair === undefined || thresholdPair === null) {
    // Either we deliberately don't penalize (e.g., school_rating) or the
    // metric isn't in the table; either way: zero penalty, no noise.
    return [0, null];
  }
  const [threshold, penalty] = thresholdPair;
  if (delta.abs().gt(threshold)) {
    const pct = delta.abs().mul(new Decimal("100")).quantize(new Decimal("0.1"));
    return [
      penalty,
      `sources disagree by ${pct.toString()}% (>${formatThresholdPct(threshold)}% threshold) on '${metricName}'`,
    ];
  }
  return [0, null];
}

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
export function confidenceScore(
  metric: MetricValue,
  ageDays: number,
  disagreement: DecimalLike | null,
): ConfidenceResult {
  if (ageDays < 0) {
    throw new Error(`age_days must be non-negative, got ${ageDays}`);
  }

  // Missing value short-circuits to 0/low.
  if (metric.value === null) {
    return {
      score: 0,
      tier: "low",
      reasons: [`no value reported for '${metric.metric_name}'`],
    };
  }

  let score = 100;
  const reasons: string[] = [];

  const [samplePenalty, sampleReason] = sampleSizePenalty(
    metric.metric_name,
    metric.sample_size,
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
  // (>100 unreachable: we start at 100 and only subtract non-negative
  // penalties — but defensively pinned for symmetry with Python.)
  if (score > 100) score = 100;

  return { score, tier: bucketScore(score), reasons };
}
