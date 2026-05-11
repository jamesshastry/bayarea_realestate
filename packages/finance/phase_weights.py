"""Weights for ``timing.compute_phase``.

The Market Phase formula in ``docs/design.md`` §5.3.1 is:

    buyer_pressure  = w1*(s2l - 1) + w2*max(0, 3 - mos) + w3*max(0, -dom_trend)
    seller_pressure = w4*pdrop + w5*max(0, mos - 3) + w6*max(0, dom_trend)
                       + w7*max(0, inv_yoy)

The weights below are **Phase-1 reasonable defaults**. Calibration against
historical Bay Area data is a Phase-3 task — see
``docs/implementation-plan.md`` Phase 3 risks. Until then, these
deterministic values let the formula be tested for shape, monotonicity,
and idempotence even though the absolute pressure magnitudes are not yet
empirically tuned.

Each weight is chosen so that, in the *typical* Bay Area range for the
input it applies to, its contribution to the 0–100 pressure score is
roughly proportional to the input's diagnostic strength. The detailed
rationale per weight lives in inline comments.

These weights are exported as ``Decimal`` (not ``float``) so the entire
pressure-score arithmetic stays in ``Decimal`` and the TS port reproduces
byte-equal output.
"""

from __future__ import annotations

from decimal import Decimal

# Buyer-pressure weights ----------------------------------------------------

# w1 multiplies (s2l - 1). A 0.05 over-bid (s2l = 1.05) → +30 contribution.
# Bay Area s2l routinely sits in [0.95, 1.10]; +0.05 represents a clear
# bidding-war environment, so a strong but not saturating push.
W1_S2L = Decimal("600")

# w2 multiplies max(0, 3 - mos). MOS < 3 is the textbook seller's-market
# threshold. MOS of 1.5 → +30 contribution. MOS of 3.0 → 0.
W2_INV_PRESSURE = Decimal("20")

# w3 multiplies max(0, -dom_trend) where dom_trend is the signed Δ in days
# vs. the 12-week baseline. A 10-day reduction → +30 contribution.
W3_DOM_FALLING = Decimal("3")

# Seller-pressure weights ---------------------------------------------------

# w4 multiplies pct_with_price_drops (0–1). 0.30 (a third of listings cut
# price) → +30 contribution.
W4_PDROP = Decimal("100")

# w5 multiplies max(0, mos - 3). MOS of 4.5 → +30; MOS of 3.0 → 0.
W5_INV_OVERHANG = Decimal("20")

# w6 multiplies max(0, dom_trend). A 10-day rise → +30 contribution.
W6_DOM_RISING = Decimal("3")

# w7 multiplies max(0, inv_yoy) where inv_yoy is a fraction. +0.30 YoY
# (active listings up 30% YoY) → +30 contribution.
W7_INV_YOY = Decimal("100")

WEIGHTS = {
    "w1_s2l": W1_S2L,
    "w2_inv_pressure": W2_INV_PRESSURE,
    "w3_dom_falling": W3_DOM_FALLING,
    "w4_pdrop": W4_PDROP,
    "w5_inv_overhang": W5_INV_OVERHANG,
    "w6_dom_rising": W6_DOM_RISING,
    "w7_inv_yoy": W7_INV_YOY,
}

# Pressure clamps. Both pressure scores are clamped to [0, 100] so the
# phase classifier and the UI gauge never see out-of-band values.
PRESSURE_MIN = Decimal("0")
PRESSURE_MAX = Decimal("100")

# Confidence inheritance bands. ``compute_phase`` inherits the snapshot's
# integer 0–100 ``confidence_score`` and buckets it for the UI:
#
#   ≥ 75 → "high"
#   45–74 → "medium"
#   < 45  → "low"  (and the phase is forced to "unknown")
#
# These match the per-metric thresholds table in ``docs/design.md`` §5.2;
# the cutoffs are pinned in ``confidence.py`` (single source of truth) and
# imported by ``timing.py``.

__all__ = [
    "PRESSURE_MAX",
    "PRESSURE_MIN",
    "W1_S2L",
    "W2_INV_PRESSURE",
    "W3_DOM_FALLING",
    "W4_PDROP",
    "W5_INV_OVERHANG",
    "W6_DOM_RISING",
    "W7_INV_YOY",
    "WEIGHTS",
]
