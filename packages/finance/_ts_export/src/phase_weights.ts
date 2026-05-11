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

import { Decimal } from "./decimal.js";

// Buyer-pressure weights ----------------------------------------------------

/** w1 multiplies (s2l - 1). A 0.05 over-bid (s2l = 1.05) → +30 contribution. */
export const W1_S2L = new Decimal("600");

/** w2 multiplies max(0, 3 - mos). MOS < 3 = textbook seller's-market threshold.
 *  MOS of 1.5 → +30; MOS of 3.0 → 0. */
export const W2_INV_PRESSURE = new Decimal("20");

/** w3 multiplies max(0, -dom_trend) where dom_trend is the signed Δ in days
 *  vs. the 12-week baseline. A 10-day reduction → +30 contribution. */
export const W3_DOM_FALLING = new Decimal("3");

// Seller-pressure weights ---------------------------------------------------

/** w4 multiplies pct_with_price_drops (0–1). 0.30 → +30 contribution. */
export const W4_PDROP = new Decimal("100");

/** w5 multiplies max(0, mos - 3). MOS of 4.5 → +30; MOS of 3.0 → 0. */
export const W5_INV_OVERHANG = new Decimal("20");

/** w6 multiplies max(0, dom_trend). A 10-day rise → +30 contribution. */
export const W6_DOM_RISING = new Decimal("3");

/** w7 multiplies max(0, inv_yoy). +0.30 YoY → +30 contribution. */
export const W7_INV_YOY = new Decimal("100");

export const WEIGHTS = {
  w1_s2l: W1_S2L,
  w2_inv_pressure: W2_INV_PRESSURE,
  w3_dom_falling: W3_DOM_FALLING,
  w4_pdrop: W4_PDROP,
  w5_inv_overhang: W5_INV_OVERHANG,
  w6_dom_rising: W6_DOM_RISING,
  w7_inv_yoy: W7_INV_YOY,
};

/** Pressure clamps. Both pressure scores are clamped to [0, 100] so the
 *  phase classifier and the UI gauge never see out-of-band values. */
export const PRESSURE_MIN = new Decimal("0");
export const PRESSURE_MAX = new Decimal("100");
