"""Market Phase computation per ``docs/design.md`` §5.3.1.

Implements the C3 contract:

    compute_phase(snapshot: SnapshotForPhase, history: PhaseHistory) -> PhaseResult

The function is **deterministic and pure** — same inputs → same output,
no clock, no globals. Hypothesis property tests in
``packages/finance/tests/test_timing.py`` verify idempotence and the
phase-boundary cases.

Algorithm summary:

1. Compute the six derived components:
   ``mos``, ``s2l_4w``, ``s2l_12w``, ``pdrop``, ``dom_trend``, ``inv_yoy``.
2. Combine them into ``buyer_pressure`` and ``seller_pressure`` per the
   weighted formula in ``phase_weights.py``.
3. Clamp both pressures to [0, 100].
4. Project the (buyer, seller) coordinate onto the Market Clock face:
   - 12 o'clock = peak buyer pressure, low seller pressure
   - 3 o'clock = pressures inverting (cooling)
   - 6 o'clock = peak seller pressure, low buyer pressure (trough)
   - 9 o'clock = pressures inverting back (recovery)
5. Bucket into a phase label based on which quadrant the coordinate sits
   in, with a deterministic tie-break using ``history.previous_phase``.
6. Inherit confidence tier from the snapshot.

If the snapshot's confidence_score is below the low cutoff (45), the
phase is forced to ``"unknown"`` per ``docs/datamodel.md`` §6a.
"""

from __future__ import annotations

from decimal import ROUND_HALF_EVEN, Decimal

from ._types import (
    ConfidenceTier,
    MarketPhase,
    PhaseComponents,
    PhaseHistory,
    PhaseResult,
    SnapshotForPhase,
)
from .confidence import TIER_HIGH_CUTOFF, TIER_MEDIUM_CUTOFF
from .phase_weights import (
    PRESSURE_MAX,
    PRESSURE_MIN,
    W1_S2L,
    W2_INV_PRESSURE,
    W3_DOM_FALLING,
    W4_PDROP,
    W5_INV_OVERHANG,
    W6_DOM_RISING,
    W7_INV_YOY,
)

_ZERO = Decimal("0")
_THREE = Decimal("3")
_TWELVE = Decimal("12")
_HUNDRED = Decimal("100")


def _clamp(value: Decimal, low: Decimal, high: Decimal) -> Decimal:
    """Clamp ``value`` to the inclusive range ``[low, high]``."""

    if value < low:  # pragma: no cover - upstream callers guard sign before calling
        return low
    if value > high:
        return high
    return value


def _bucket_confidence(score: int) -> ConfidenceTier:
    """Bucket an integer 0–100 score using the cutoffs from ``confidence.py``."""

    if score >= TIER_HIGH_CUTOFF:
        return "high"
    if score >= TIER_MEDIUM_CUTOFF:
        return "medium"
    return "low"


def _compute_components(snapshot: SnapshotForPhase, history: PhaseHistory) -> PhaseComponents:
    """Derive the six per-input components surfaced to the UI."""

    dom_trend = Decimal(snapshot.median_dom - history.baseline_dom)
    return PhaseComponents(
        mos=snapshot.months_of_supply,
        s2l_4w=snapshot.s2l_4w,
        s2l_12w=snapshot.s2l_12w,
        pdrop=snapshot.pct_with_price_drops,
        dom_trend=dom_trend,
        inv_yoy=history.inv_yoy,
    )


def _buyer_pressure(components: PhaseComponents) -> Decimal:
    """Weighted sum per ``docs/design.md`` §5.3.1 (buyer side)."""

    s2l_term = (components.s2l_4w - Decimal("1")) * W1_S2L
    if s2l_term < 0:
        s2l_term = _ZERO

    mos_term = max(_ZERO, _THREE - components.mos) * W2_INV_PRESSURE
    dom_term = max(_ZERO, -components.dom_trend) * W3_DOM_FALLING

    return _clamp(s2l_term + mos_term + dom_term, PRESSURE_MIN, PRESSURE_MAX)


def _seller_pressure(components: PhaseComponents) -> Decimal:
    """Weighted sum per ``docs/design.md`` §5.3.1 (seller side)."""

    pdrop_term = components.pdrop * W4_PDROP
    if pdrop_term < 0:  # pragma: no cover - pdrop is bounded [0, 1] upstream
        pdrop_term = _ZERO

    overhang_term = max(_ZERO, components.mos - _THREE) * W5_INV_OVERHANG
    dom_rising_term = max(_ZERO, components.dom_trend) * W6_DOM_RISING
    inv_yoy_term = max(_ZERO, components.inv_yoy) * W7_INV_YOY

    return _clamp(
        pdrop_term + overhang_term + dom_rising_term + inv_yoy_term,
        PRESSURE_MIN,
        PRESSURE_MAX,
    )


def _clock_position(buyer_p: Decimal, seller_p: Decimal) -> Decimal:
    """Project (buyer, seller) into a 0.0–12.0 clock position.

    Concept: the clock face is a 2D mapping where:
      - high buyer / low seller     → 12 (top)
      - balanced (both ~ equal)     → 3 (right)  if inv_yoy positive trend,
                                       9 (left)  if recovering
      - low buyer / high seller     → 6 (bottom)

    Phase-1 implementation: a deterministic angle from the *signed
    difference* (buyer - seller). We map the difference [-100, 100] to
    a clock angle in a continuous, monotone way:

      diff = +100 (max buyer dominance)  → 12.0
      diff =   0                         →  3.0  (default; cooling/recovery
                                                  disambiguation handled by
                                                  the phase classifier below)
      diff = -100 (max seller dominance) →  6.0

    A truer 2D mapping (full angle from the centroid) is a Phase-3
    calibration task. The Phase-1 mapping is sufficient for the UI to
    show monotone movement and for tests to assert idempotence.
    """

    # Signed difference in [-100, 100].
    diff = buyer_p - seller_p
    # Map to [0, 1] where 0 = bottom (6 o'clock) and 1 = top (12 o'clock).
    normalized = (diff + _HUNDRED) / (_HUNDRED * Decimal("2"))
    # Clock angle: 12 at top, 6 at bottom, with the right semicircle
    # spanned by 12→3→6 and the left semicircle by 12→9→6. We collapse
    # to the right semicircle for the Phase-1 default — the recovery
    # quadrant is selected by the phase classifier below using
    # ``previous_phase``.
    # 12 o'clock = 0.0 mod 12, 6 o'clock = 6.0.
    # Map normalized=1 → 12.0 → 0.0 (or equivalently 12.0); normalized=0 → 6.0.
    # We return values in [0.0, 12.0], wrapping naturally.
    if normalized >= Decimal("0.5"):
        # Top half: from 12 (top) to 3 (right) as buyer pressure falls.
        # normalized 1.0 → 12.0; 0.5 → 3.0.
        # Linear: position = 12 - (1 - normalized) * 18 ... but we want
        # 1.0 → 12 and 0.5 → 3, span of 9.
        position = _TWELVE - (Decimal("1") - normalized) * Decimal("18")
    else:
        # Bottom half: from 3 to 6 as seller pressure rises.
        # 0.5 → 3.0; 0.0 → 6.0. span of 3 over 0.5 input range.
        position = _THREE + (Decimal("0.5") - normalized) * Decimal("6")

    # Clamp to [0, 12].
    if position < _ZERO:  # pragma: no cover - mapping confines output to [0, 12] by construction
        position = _ZERO
    elif (
        position > _TWELVE
    ):  # pragma: no cover - mapping confines output to [0, 12] by construction
        position = _TWELVE
    return position.quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)


def _classify_phase(buyer_p: Decimal, seller_p: Decimal, history: PhaseHistory) -> MarketPhase:
    """Bucket a (buyer, seller) coordinate into a phase label.

    Quadrant rules (per the clock mnemonic in ``docs/design.md`` §5.3.1):
      buyer >= 60 and seller <  40            → "peak"
      buyer >= 40 and seller >= 40 and rising → "cooling"  (or recovery)
      buyer <  40 and seller >= 60            → "trough"
      buyer >= 40 and seller >= 40 and falling → "recovery"
      otherwise: trend-aware default

    Tie-break: when the coordinate sits in the cooling/recovery middle
    band, ``history.previous_phase`` disambiguates. If we were in
    ``"trough"``, the next non-trough is ``"recovery"``; if ``"peak"``
    or ``"cooling"``, the next is ``"cooling"``.
    """

    # Strong corner cases.
    if buyer_p >= Decimal("60") and seller_p < Decimal("40"):
        return "peak"
    if seller_p >= Decimal("60") and buyer_p < Decimal("40"):
        return "trough"

    # Mixed band: use history to disambiguate.
    if history.previous_phase == "trough":
        return "recovery"
    if history.previous_phase == "recovery":
        # Stay in recovery until buyer clearly dominates.
        if buyer_p > seller_p + Decimal("20"):
            return "peak"
        return "recovery"
    if history.previous_phase == "peak":
        # From peak we can only step to cooling unless we crash to trough.
        return "cooling"
    if history.previous_phase == "cooling":
        # Stay in cooling until seller pressure releases.
        if seller_p < Decimal("30") and buyer_p < Decimal("40"):
            return "recovery"
        return "cooling"
    # No history. Use the dominant pressure to bias.
    if buyer_p > seller_p:
        return "cooling"  # inflection from above
    if seller_p > buyer_p:
        return "recovery"  # inflection from below
    return "cooling"


def compute_phase(snapshot: SnapshotForPhase, history: PhaseHistory) -> PhaseResult:
    """Compute the Market Phase for a snapshot.

    Per C3 the signature is fixed:
    ``(snapshot: SnapshotForPhase, history: PhaseHistory) -> PhaseResult``.

    Confidence handling:
    - Snapshot's integer ``confidence_score`` is bucketed into a
      ``ConfidenceTier`` ("high" / "medium" / "low") with the cutoffs
      from ``confidence.py``.
    - If the bucketed tier is "low", the returned phase is forced to
      ``"unknown"`` (and the components / pressures are still surfaced
      for transparency).
    """

    if snapshot.sample_size < 0:
        raise ValueError(f"sample_size must be non-negative, got {snapshot.sample_size}")
    if snapshot.confidence_score < 0 or snapshot.confidence_score > 100:
        raise ValueError(f"confidence_score must be in [0, 100], got {snapshot.confidence_score}")

    components = _compute_components(snapshot, history)
    buyer_p = _buyer_pressure(components)
    seller_p = _seller_pressure(components)
    clock = _clock_position(buyer_p, seller_p)

    confidence = _bucket_confidence(snapshot.confidence_score)
    if confidence == "low":
        phase: MarketPhase = "unknown"
    else:
        phase = _classify_phase(buyer_p, seller_p, history)

    return PhaseResult(
        phase=phase,
        clock_position=clock,
        buyer_pressure=int(buyer_p.to_integral_value(rounding=ROUND_HALF_EVEN)),
        seller_pressure=int(seller_p.to_integral_value(rounding=ROUND_HALF_EVEN)),
        components=components,
        confidence=confidence,
    )


__all__ = [
    "compute_phase",
]
