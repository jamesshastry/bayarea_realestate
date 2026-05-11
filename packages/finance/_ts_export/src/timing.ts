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

import { Decimal } from "./decimal.js";
import { TIER_HIGH_CUTOFF, TIER_MEDIUM_CUTOFF } from "./confidence.js";
import {
  PRESSURE_MAX,
  PRESSURE_MIN,
  W1_S2L,
  W2_INV_PRESSURE,
  W3_DOM_FALLING,
  W4_PDROP,
  W5_INV_OVERHANG,
  W6_DOM_RISING,
  W7_INV_YOY,
} from "./phase_weights.js";
import type {
  ConfidenceTier,
  MarketPhase,
  PhaseComponents,
  PhaseHistory,
  PhaseResult,
  SnapshotForPhase,
} from "./types.js";

const ZERO = new Decimal("0");
const THREE = new Decimal("3");
const TWELVE = new Decimal("12");
const HUNDRED = new Decimal("100");
const ONE = new Decimal("1");
const TWO = new Decimal("2");
const PCT_FIXED = new Decimal("0.01");

/** Clamp `value` to the inclusive range [low, high]. */
function clamp(value: Decimal, low: Decimal, high: Decimal): Decimal {
  if (value.lt(low)) return low;
  if (value.gt(high)) return high;
  return value;
}

/** Bucket an integer 0–100 score using the cutoffs from `confidence.ts`. */
function bucketConfidence(score: number): ConfidenceTier {
  if (score >= TIER_HIGH_CUTOFF) return "high";
  if (score >= TIER_MEDIUM_CUTOFF) return "medium";
  return "low";
}

/** Derive the six per-input contributions surfaced to the UI. */
function computeComponents(snapshot: SnapshotForPhase, history: PhaseHistory): PhaseComponents {
  // `Decimal(int - int)` in Python yields an integer-scale Decimal.
  // Subtract first as ints, then wrap — preserves the `"-12"` form
  // (no decimal point) the golden file expects.
  const domTrend = new Decimal(snapshot.median_dom - history.baseline_dom);
  return {
    mos: snapshot.months_of_supply,
    s2l_4w: snapshot.s2l_4w,
    s2l_12w: snapshot.s2l_12w,
    pdrop: snapshot.pct_with_price_drops,
    dom_trend: domTrend,
    inv_yoy: history.inv_yoy,
  };
}

/** Weighted sum per `docs/design.md` §5.3.1 (buyer side). */
function buyerPressure(components: PhaseComponents): Decimal {
  let s2lTerm = components.s2l_4w.sub(ONE).mul(W1_S2L);
  if (s2lTerm.lt(ZERO)) {
    s2lTerm = ZERO;
  }
  const mosShortage = THREE.sub(components.mos);
  const mosTerm = (mosShortage.gt(ZERO) ? mosShortage : ZERO).mul(W2_INV_PRESSURE);
  const negDomTrend = components.dom_trend.neg();
  const domTerm = (negDomTrend.gt(ZERO) ? negDomTrend : ZERO).mul(W3_DOM_FALLING);
  return clamp(s2lTerm.add(mosTerm).add(domTerm), PRESSURE_MIN, PRESSURE_MAX);
}

/** Weighted sum per `docs/design.md` §5.3.1 (seller side). */
function sellerPressure(components: PhaseComponents): Decimal {
  let pdropTerm = components.pdrop.mul(W4_PDROP);
  if (pdropTerm.lt(ZERO)) {
    // Defensive — pdrop is bounded [0, 1] upstream.
    pdropTerm = ZERO;
  }
  const mosOverhang = components.mos.sub(THREE);
  const overhangTerm = (mosOverhang.gt(ZERO) ? mosOverhang : ZERO).mul(W5_INV_OVERHANG);
  const domTrend = components.dom_trend;
  const domRisingTerm = (domTrend.gt(ZERO) ? domTrend : ZERO).mul(W6_DOM_RISING);
  const invYoy = components.inv_yoy;
  const invYoyTerm = (invYoy.gt(ZERO) ? invYoy : ZERO).mul(W7_INV_YOY);
  return clamp(
    pdropTerm.add(overhangTerm).add(domRisingTerm).add(invYoyTerm),
    PRESSURE_MIN,
    PRESSURE_MAX,
  );
}

/**
 * Project (buyer, seller) into a 0.0–12.0 clock position. Phase-1
 * implementation: a deterministic angle from the *signed difference*
 * (buyer - seller) — see `docs/design.md` §5.3.1 for the truer 2D
 * mapping deferred to Phase 3.
 */
function clockPosition(buyerP: Decimal, sellerP: Decimal): Decimal {
  // Signed difference in [-100, 100].
  const diff = buyerP.sub(sellerP);
  // Normalize to [0, 1]: 0 = bottom (6 o'clock), 1 = top (12 o'clock).
  const normalized = diff.add(HUNDRED).div(HUNDRED.mul(TWO));
  let position: Decimal;
  if (normalized.gte(new Decimal("0.5"))) {
    // Top half: from 12 to 3 as buyer pressure falls.
    // 1.0 → 12.0; 0.5 → 3.0. Linear, span of 9 over 0.5 input range.
    position = TWELVE.sub(ONE.sub(normalized).mul(new Decimal("18")));
  } else {
    // Bottom half: from 3 to 6 as seller pressure rises.
    // 0.5 → 3.0; 0.0 → 6.0. Span of 3 over 0.5 input range.
    position = THREE.add(new Decimal("0.5").sub(normalized).mul(new Decimal("6")));
  }
  if (position.lt(ZERO)) position = ZERO;
  if (position.gt(TWELVE)) position = TWELVE;
  return position.quantize(PCT_FIXED);
}

/**
 * Bucket a (buyer, seller) coordinate into a phase label.
 *
 * Quadrant rules (per the clock mnemonic in `docs/design.md` §5.3.1):
 *
 *   buyer >= 60 and seller <  40              → "peak"
 *   buyer >= 40 and seller >= 40 and rising   → "cooling"  (or recovery)
 *   buyer <  40 and seller >= 60              → "trough"
 *   buyer >= 40 and seller >= 40 and falling  → "recovery"
 *   otherwise: trend-aware default
 *
 * Tie-break: when the coordinate sits in the cooling/recovery middle
 * band, `history.previous_phase` disambiguates. From "trough" → next
 * non-trough is "recovery"; from "peak" or "cooling" → next is "cooling".
 */
function classifyPhase(
  buyerP: Decimal,
  sellerP: Decimal,
  history: PhaseHistory,
): MarketPhase {
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

  // Mixed band: use history to disambiguate.
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
  // No history. Use the dominant pressure to bias.
  if (buyerP.gt(sellerP)) {
    return "cooling";
  }
  if (sellerP.gt(buyerP)) {
    return "recovery";
  }
  return "cooling";
}

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
export function computePhase(
  snapshot: SnapshotForPhase,
  history: PhaseHistory,
): PhaseResult {
  if (snapshot.sample_size < 0) {
    throw new Error(
      `sample_size must be non-negative, got ${snapshot.sample_size}`,
    );
  }
  if (snapshot.confidence_score < 0 || snapshot.confidence_score > 100) {
    throw new Error(
      `confidence_score must be in [0, 100], got ${snapshot.confidence_score}`,
    );
  }

  const components = computeComponents(snapshot, history);
  const buyerP = buyerPressure(components);
  const sellerP = sellerPressure(components);
  const clock = clockPosition(buyerP, sellerP);

  const confidence = bucketConfidence(snapshot.confidence_score);
  let phase: MarketPhase;
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
    confidence,
  };
}
