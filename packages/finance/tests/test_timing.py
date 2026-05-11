"""Unit + Hypothesis property tests for ``finance.timing.compute_phase``.

Property invariants asserted:
- Idempotence: calling twice with identical inputs returns the same
  result (no hidden state).
- Pressure clamping: 0 ≤ buyer_pressure, seller_pressure ≤ 100.
- Phase boundary: low confidence forces phase = "unknown".
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from finance._types import PhaseHistory, SnapshotForPhase
from finance.timing import compute_phase


def _snapshot(
    *,
    mos: Decimal = Decimal("2.0"),
    s2l_4w: Decimal = Decimal("1.02"),
    s2l_12w: Decimal = Decimal("1.01"),
    pdrop: Decimal = Decimal("0.10"),
    median_dom: int = 18,
    active_listings: int = 100,
    sample_size: int = 50,
    confidence: int = 85,
) -> SnapshotForPhase:
    return SnapshotForPhase(
        months_of_supply=mos,
        s2l_4w=s2l_4w,
        s2l_12w=s2l_12w,
        pct_with_price_drops=pdrop,
        median_dom=median_dom,
        active_listings=active_listings,
        sample_size=sample_size,
        confidence_score=confidence,
    )


def _history(
    *,
    baseline_dom: int = 20,
    inv_yoy: Decimal = Decimal("0.0"),
    previous_phase: str = "unknown",
) -> PhaseHistory:
    return PhaseHistory(
        baseline_dom=baseline_dom,
        inv_yoy=inv_yoy,
        previous_phase=previous_phase,  # type: ignore[arg-type]
    )


def test_compute_phase_basic_shape() -> None:
    result = compute_phase(_snapshot(), _history())
    assert 0 <= result.buyer_pressure <= 100
    assert 0 <= result.seller_pressure <= 100
    assert Decimal("0") <= result.clock_position <= Decimal("12")
    assert result.confidence in {"low", "medium", "high"}
    # Component values plumbed through.
    assert result.components.mos == Decimal("2.0")
    assert result.components.s2l_4w == Decimal("1.02")


def test_compute_phase_low_confidence_forces_unknown() -> None:
    """Per ``docs/datamodel.md`` §6a, low-confidence snapshots must be
    classified ``"unknown"`` regardless of where the pressures sit."""

    result = compute_phase(_snapshot(confidence=20), _history())
    assert result.phase == "unknown"
    assert result.confidence == "low"


def test_compute_phase_strong_buyer_pressure_classified_peak() -> None:
    """Tight inventory + over-bid + falling DOM → classic seller's market
    → "peak" phase (high buyer pressure, low seller pressure)."""

    snap = _snapshot(
        mos=Decimal("0.8"),  # very tight
        s2l_4w=Decimal("1.10"),  # 10% over-bid
        s2l_12w=Decimal("1.07"),
        pdrop=Decimal("0.02"),
        median_dom=10,
    )
    hist = _history(baseline_dom=25, inv_yoy=Decimal("-0.20"))
    result = compute_phase(snap, hist)
    assert result.buyer_pressure > result.seller_pressure
    assert result.phase == "peak"


def test_compute_phase_strong_seller_pressure_classified_trough() -> None:
    """Inventory glut + price drops + DOM rising → buyer's market →
    "trough"."""

    snap = _snapshot(
        mos=Decimal("6.0"),
        s2l_4w=Decimal("0.95"),
        s2l_12w=Decimal("0.96"),
        pdrop=Decimal("0.45"),
        median_dom=60,
    )
    hist = _history(baseline_dom=25, inv_yoy=Decimal("0.50"))
    result = compute_phase(snap, hist)
    assert result.seller_pressure > result.buyer_pressure
    assert result.phase == "trough"


def test_compute_phase_history_disambiguates_mid_band() -> None:
    """When pressures are roughly balanced, ``previous_phase`` decides
    cooling vs. recovery."""

    # A "still cooling" snapshot: seller pressure remains high enough
    # (pdrop = 0.40 → seller_p ≈ 40) that the cooling-state retention
    # rule fires.
    snap_cooling = _snapshot(
        mos=Decimal("3.0"),
        s2l_4w=Decimal("1.00"),
        s2l_12w=Decimal("1.00"),
        pdrop=Decimal("0.40"),
        median_dom=22,
    )
    coming_from_cooling = _history(previous_phase="cooling")
    # Previous cooling AND seller pressure still elevated → stay in
    # cooling.
    assert compute_phase(snap_cooling, coming_from_cooling).phase == "cooling"

    # A genuinely mid-band snapshot for the other history disambiguations.
    snap_mid = _snapshot(
        mos=Decimal("3.0"),
        s2l_4w=Decimal("1.00"),
        s2l_12w=Decimal("1.00"),
        pdrop=Decimal("0.20"),
        median_dom=22,
    )
    coming_down_from_peak = _history(previous_phase="peak")
    coming_up_from_trough = _history(previous_phase="trough")
    coming_from_recovery = _history(previous_phase="recovery")
    no_history = _history(previous_phase="unknown")

    assert compute_phase(snap_mid, coming_down_from_peak).phase == "cooling"
    assert compute_phase(snap_mid, coming_up_from_trough).phase == "recovery"
    # From recovery without strong buyer dominance we stay in recovery.
    assert compute_phase(snap_mid, coming_from_recovery).phase == "recovery"
    # No history: classifier picks based on dominant pressure or default.
    out = compute_phase(snap_mid, no_history).phase
    assert out in {"cooling", "recovery"}


def test_compute_phase_recovery_steps_to_peak_when_buyer_dominates() -> None:
    """From the recovery phase, only a clearly buyer-dominant signal
    should step us to peak."""

    snap = _snapshot(
        mos=Decimal("1.0"),
        s2l_4w=Decimal("1.10"),
        s2l_12w=Decimal("1.05"),
        pdrop=Decimal("0.05"),
        median_dom=12,
    )
    hist = _history(previous_phase="recovery", baseline_dom=22, inv_yoy=Decimal("-0.10"))
    result = compute_phase(snap, hist)
    assert result.phase == "peak"


def test_compute_phase_cooling_steps_to_recovery_when_seller_releases() -> None:
    """From cooling, low buyer + low seller → recovery."""

    snap = _snapshot(
        mos=Decimal("3.5"),
        s2l_4w=Decimal("1.00"),
        s2l_12w=Decimal("1.00"),
        pdrop=Decimal("0.05"),
        median_dom=22,
    )
    hist = _history(previous_phase="cooling", baseline_dom=22, inv_yoy=Decimal("0.0"))
    result = compute_phase(snap, hist)
    assert result.phase == "recovery"


def test_compute_phase_recovery_to_peak_with_moderate_buyer_dominance() -> None:
    """Recovery → "peak" happens at line 211 of timing.py: previous
    phase was recovery, buyer pressure exceeds seller by > 20 BUT buyer
    isn't strong enough to hit the early >= 60 corner case."""

    snap = _snapshot(
        mos=Decimal("2.0"),
        s2l_4w=Decimal("1.05"),  # +30 buyer
        s2l_12w=Decimal("1.04"),
        pdrop=Decimal("0.05"),
        median_dom=20,
    )
    hist = _history(previous_phase="recovery", baseline_dom=20, inv_yoy=Decimal("0.0"))
    res = compute_phase(snap, hist)
    # buyer ~ 30, seller ~ 5 → diff > 20 → "peak"
    assert res.phase == "peak"


def test_compute_phase_no_history_balanced_returns_cooling_default() -> None:
    """When there's no history and buyer == seller (both ~0), the
    fallthrough at the end of ``_classify_phase`` returns "cooling"."""

    snap = _snapshot(
        mos=Decimal("3.0"),
        s2l_4w=Decimal("1.00"),
        s2l_12w=Decimal("1.00"),
        pdrop=Decimal("0.0"),
        median_dom=20,
    )
    hist = _history(previous_phase="unknown", baseline_dom=20, inv_yoy=Decimal("0"))
    res = compute_phase(snap, hist)
    # buyer = 0, seller = 0 → fallthrough returns "cooling"
    assert res.phase == "cooling"
    assert res.buyer_pressure == 0
    assert res.seller_pressure == 0


def test_compute_phase_clamp_handles_extreme_values() -> None:
    """Clamp triggers on the low side when the seller-pressure formula
    is negated by carefully chosen inputs (proxied here via the
    public path for coverage of the clamp branch)."""

    # We can't pass *negative* pdrop directly (UI-validated upstream),
    # but we can ensure the clamp branch is exercised by the seller
    # pressure path: setting pdrop = 0 produces seller_p = 0, hitting
    # the clamp's "value < low" only if low > 0 — which it isn't.
    # Instead, push the buyer pressure to the upper clamp via huge s2l.
    snap = _snapshot(
        mos=Decimal("0.1"),
        s2l_4w=Decimal("2.00"),  # absurd over-bid → s2l_term = 600
        s2l_12w=Decimal("1.50"),
        pdrop=Decimal("0.0"),
        median_dom=1,
    )
    hist = _history(baseline_dom=200, inv_yoy=Decimal("-1.0"))
    res = compute_phase(snap, hist)
    assert res.buyer_pressure == 100


def test_compute_phase_idempotent() -> None:
    snap = _snapshot()
    hist = _history()
    a = compute_phase(snap, hist)
    b = compute_phase(snap, hist)
    assert a == b


def test_compute_phase_rejects_negative_sample_size() -> None:
    with pytest.raises(ValueError, match="sample_size"):
        compute_phase(_snapshot(sample_size=-1), _history())


def test_compute_phase_rejects_out_of_range_confidence() -> None:
    with pytest.raises(ValueError, match="confidence_score"):
        compute_phase(_snapshot(confidence=150), _history())
    with pytest.raises(ValueError, match="confidence_score"):
        compute_phase(_snapshot(confidence=-5), _history())


def test_compute_phase_clock_position_top_when_buyer_dominates() -> None:
    """If buyer pressure is at 100 and seller is at 0 we should be at
    clock 12 (or near it)."""

    snap = _snapshot(
        mos=Decimal("0.5"),
        s2l_4w=Decimal("1.20"),
        s2l_12w=Decimal("1.15"),
        pdrop=Decimal("0.0"),
        median_dom=5,
    )
    hist = _history(baseline_dom=30, inv_yoy=Decimal("-0.30"))
    result = compute_phase(snap, hist)
    assert result.clock_position >= Decimal("11")


def test_compute_phase_clock_position_bottom_when_seller_dominates() -> None:
    """Strong seller pressure → clock position near 6 (bottom of the
    Phase-1 right-semicircle mapping).

    Per ``timing._clock_position`` the right-semicircle mapping covers
    [3, 6] for the bottom half. Maximum seller dominance lands at 6.0.
    """

    snap = _snapshot(
        mos=Decimal("8.0"),
        s2l_4w=Decimal("0.90"),
        s2l_12w=Decimal("0.92"),
        pdrop=Decimal("0.60"),
        median_dom=80,
    )
    hist = _history(baseline_dom=20, inv_yoy=Decimal("0.80"))
    result = compute_phase(snap, hist)
    assert result.clock_position >= Decimal("5")
    assert result.clock_position <= Decimal("6")


@settings(max_examples=80, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    mos=st.decimals(min_value=Decimal("0"), max_value=Decimal("12"), places=2),
    s2l_4w=st.decimals(min_value=Decimal("0.7"), max_value=Decimal("1.3"), places=3),
    s2l_12w=st.decimals(min_value=Decimal("0.7"), max_value=Decimal("1.3"), places=3),
    pdrop=st.decimals(min_value=Decimal("0"), max_value=Decimal("1"), places=3),
    dom=st.integers(min_value=1, max_value=200),
    baseline_dom=st.integers(min_value=1, max_value=200),
    inv_yoy=st.decimals(min_value=Decimal("-1"), max_value=Decimal("3"), places=2),
    confidence=st.integers(min_value=0, max_value=100),
)
def test_compute_phase_pressures_always_clamped(
    mos: Decimal,
    s2l_4w: Decimal,
    s2l_12w: Decimal,
    pdrop: Decimal,
    dom: int,
    baseline_dom: int,
    inv_yoy: Decimal,
    confidence: int,
) -> None:
    snap = _snapshot(
        mos=mos,
        s2l_4w=s2l_4w,
        s2l_12w=s2l_12w,
        pdrop=pdrop,
        median_dom=dom,
        confidence=confidence,
    )
    hist = _history(baseline_dom=baseline_dom, inv_yoy=inv_yoy)
    result = compute_phase(snap, hist)
    assert 0 <= result.buyer_pressure <= 100
    assert 0 <= result.seller_pressure <= 100
    assert Decimal("0") <= result.clock_position <= Decimal("12")
    assert result.phase in {"peak", "cooling", "trough", "recovery", "unknown"}
    if confidence < 45:
        assert result.phase == "unknown"


@settings(max_examples=40, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    mos=st.decimals(min_value=Decimal("0"), max_value=Decimal("12"), places=2),
    s2l=st.decimals(min_value=Decimal("0.8"), max_value=Decimal("1.2"), places=3),
    pdrop=st.decimals(min_value=Decimal("0"), max_value=Decimal("1"), places=3),
)
def test_compute_phase_idempotent_property(mos: Decimal, s2l: Decimal, pdrop: Decimal) -> None:
    snap = _snapshot(mos=mos, s2l_4w=s2l, s2l_12w=s2l, pdrop=pdrop)
    hist = _history()
    a = compute_phase(snap, hist)
    b = compute_phase(snap, hist)
    assert a == b
