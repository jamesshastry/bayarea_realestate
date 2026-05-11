"""Threshold-table coverage for ``finance.confidence.confidence_score``."""

from __future__ import annotations

from decimal import Decimal

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from finance._types import MetricValue
from finance.confidence import (
    SAMPLE_THRESHOLDS,
    STALENESS_DECAY_PER_DAY,
    STALENESS_GRACE_DAYS,
    TIER_HIGH_CUTOFF,
    TIER_MEDIUM_CUTOFF,
    confidence_score,
)


def _metric(
    *,
    name: str = "median_sale_price",
    value: Decimal | int | None = Decimal("1_500_000"),
    sample_size: int | None = 50,
    unit: str = "USD",
) -> MetricValue:
    return MetricValue(value=value, sample_size=sample_size, unit=unit, metric_name=name)


def test_full_score_when_fresh_high_sample_no_disagreement() -> None:
    result = confidence_score(_metric(), age_days=0, disagreement=None)
    assert result.score == 100
    assert result.tier == "high"
    assert result.reasons == []


def test_missing_value_returns_zero_low() -> None:
    result = confidence_score(_metric(value=None), age_days=0, disagreement=None)
    assert result.score == 0
    assert result.tier == "low"
    assert any("no value reported" in r for r in result.reasons)


def test_unknown_sample_size_penalty() -> None:
    result = confidence_score(_metric(sample_size=None), age_days=0, disagreement=None)
    # 100 - 30 = 70 → "medium"
    assert result.score == 70
    assert result.tier == "medium"


def test_below_low_threshold_sample_penalty() -> None:
    result = confidence_score(_metric(sample_size=5), age_days=0, disagreement=None)
    # 100 - 35 = 65
    assert result.score == 65
    assert result.tier == "medium"


def test_medium_threshold_sample_penalty() -> None:
    # median_sale_price: medium 10–29.
    result = confidence_score(_metric(sample_size=15), age_days=0, disagreement=None)
    assert result.score == 85
    assert result.tier == "high"


@pytest.mark.parametrize(
    "metric_name",
    list(SAMPLE_THRESHOLDS.keys()),
)
def test_every_metric_in_threshold_table_high_band_returns_full_score(
    metric_name: str,
) -> None:
    high = SAMPLE_THRESHOLDS[metric_name]["high"]
    result = confidence_score(
        _metric(name=metric_name, sample_size=high), age_days=0, disagreement=None
    )
    assert result.score == 100


def test_unknown_metric_name_does_not_penalize_but_warns() -> None:
    result = confidence_score(_metric(name="brand_new_metric"), age_days=0, disagreement=None)
    assert result.score == 100
    assert any("no per-metric threshold" in r for r in result.reasons)


def test_staleness_grace_then_decay() -> None:
    """Within grace: no decay. Outside: 1pt per day."""

    fresh = confidence_score(_metric(), age_days=STALENESS_GRACE_DAYS, disagreement=None)
    assert fresh.score == 100

    stale = confidence_score(_metric(), age_days=STALENESS_GRACE_DAYS + 10, disagreement=None)
    assert stale.score == 100 - 10 * STALENESS_DECAY_PER_DAY


def test_staleness_clamped_at_zero() -> None:
    very_stale = confidence_score(_metric(), age_days=500, disagreement=None)
    assert very_stale.score == 0
    assert very_stale.tier == "low"


def test_staleness_rejects_negative_age() -> None:
    with pytest.raises(ValueError, match="age_days"):
        confidence_score(_metric(), age_days=-1, disagreement=None)


def test_disagreement_above_threshold_for_median_price_penalizes_15() -> None:
    result = confidence_score(_metric(), age_days=0, disagreement=Decimal("0.08"))
    assert result.score == 85
    assert any("sources disagree" in r for r in result.reasons)


def test_disagreement_below_threshold_no_penalty() -> None:
    result = confidence_score(_metric(), age_days=0, disagreement=Decimal("0.04"))
    assert result.score == 100


def test_disagreement_for_dom_uses_30_pct_threshold_and_20_pt_penalty() -> None:
    metric = _metric(name="median_dom", value=18, sample_size=25)
    # 35% disagreement on DOM → -20.
    result = confidence_score(metric, age_days=0, disagreement=Decimal("0.35"))
    assert result.score == 80


def test_disagreement_for_school_rating_no_penalty() -> None:
    metric = _metric(name="school_rating", value=8, sample_size=100, unit="rating")
    result = confidence_score(metric, age_days=0, disagreement=Decimal("5.0"))
    assert result.score == 100


def test_disagreement_for_mortgage_rate_uses_pp_threshold() -> None:
    metric = _metric(name="mortgage_rate", value=Decimal("0.0675"), sample_size=1, unit="ratio")
    # 0.50pp disagreement on rate → -10.
    result = confidence_score(metric, age_days=0, disagreement=Decimal("0.005"))
    # The metric isn't in the SAMPLE_THRESHOLDS table either, so we get
    # the "no per-metric threshold" warning AND the rate penalty.
    assert result.score == 90
    assert any("mortgage-rate sources disagree" in r for r in result.reasons)


def test_disagreement_for_mortgage_rate_below_threshold_no_penalty() -> None:
    metric = _metric(name="mortgage_rate", value=Decimal("0.0675"), sample_size=1, unit="ratio")
    # 0.10pp — under 0.25pp threshold.
    result = confidence_score(metric, age_days=0, disagreement=Decimal("0.001"))
    assert result.score == 100


def test_disagreement_with_unknown_metric_is_ignored() -> None:
    metric = _metric(name="weird_new_metric", value=1, sample_size=1)
    result = confidence_score(metric, age_days=0, disagreement=Decimal("0.50"))
    # Unknown metric: no sample threshold (no penalty) and no disagree
    # threshold (no penalty). Just the warning reason.
    assert result.score == 100


def test_disagreement_accepts_float_input() -> None:
    """``disagreement`` may be ``float`` (per the C3 typed signature) but
    we coerce to Decimal once for clean comparisons."""

    result = confidence_score(_metric(), age_days=0, disagreement=0.08)
    assert result.score == 85


def test_combined_penalties_clamped_to_zero() -> None:
    """Stack every available penalty and verify the score floors at 0."""

    metric = _metric(sample_size=2)
    result = confidence_score(metric, age_days=300, disagreement=Decimal("0.99"))
    assert result.score == 0
    assert result.tier == "low"


def test_tier_cutoffs() -> None:
    # Score exactly at the high cutoff → high.
    metric = _metric()
    result_high = confidence_score(metric, age_days=STALENESS_GRACE_DAYS, disagreement=None)
    assert result_high.score == 100
    assert result_high.tier == "high"

    # Score just below high cutoff → medium.
    result_medium_edge = confidence_score(
        metric,
        age_days=STALENESS_GRACE_DAYS + (100 - TIER_HIGH_CUTOFF),
        disagreement=None,
    )
    assert result_medium_edge.score == TIER_HIGH_CUTOFF
    assert result_medium_edge.tier == "high"

    # One step further: 74 → medium.
    result_medium = confidence_score(
        metric,
        age_days=STALENESS_GRACE_DAYS + (100 - TIER_HIGH_CUTOFF) + 1,
        disagreement=None,
    )
    assert result_medium.score == TIER_HIGH_CUTOFF - 1
    assert result_medium.tier == "medium"

    # Score below the medium cutoff → low.
    result_low = confidence_score(
        metric,
        age_days=STALENESS_GRACE_DAYS + (100 - TIER_MEDIUM_CUTOFF) + 1,
        disagreement=None,
    )
    assert result_low.score == TIER_MEDIUM_CUTOFF - 1
    assert result_low.tier == "low"


@settings(max_examples=80, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    age=st.integers(min_value=0, max_value=400),
    sample=st.integers(min_value=0, max_value=300),
    disagreement=st.one_of(
        st.none(),
        st.decimals(min_value=Decimal("0"), max_value=Decimal("0.5"), places=4),
    ),
)
def test_confidence_score_in_range(age: int, sample: int, disagreement: Decimal | None) -> None:
    metric = _metric(sample_size=sample)
    result = confidence_score(metric, age_days=age, disagreement=disagreement)
    assert 0 <= result.score <= 100
    assert result.tier in {"low", "medium", "high"}


def test_confidence_score_is_deterministic() -> None:
    metric = _metric()
    a = confidence_score(metric, age_days=20, disagreement=Decimal("0.06"))
    b = confidence_score(metric, age_days=20, disagreement=Decimal("0.06"))
    assert a == b
