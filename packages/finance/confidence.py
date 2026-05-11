"""Confidence scoring for served metrics.

Implements ``confidence_score(metric, age_days, disagreement)`` per
``docs/design.md`` §3.3 (disagreement thresholds) and §5.2 (per-metric
sample-size thresholds).

The scoring is **deterministic**: same inputs → same output, no clock,
no globals. The function returns both the integer 0–100 score and the
ordered list of ``reasons`` that explain the penalties. The UI's "show
the math" tooltip renders ``reasons`` verbatim — operating principle #1.

Disagreement thresholds (from ``docs/design.md`` §3.3):

    median_price       > 5%   → -15
    dom                > 30%  → -20
    inventory          > 10%  → -10
    school_rating      any    → "show both" (no scalar penalty here)
    mortgage_rate      > 0.25pp → -10 (also: defer to FRED)

Per-metric sample-size thresholds (from ``docs/design.md`` §5.2):

    median_sale_price       high ≥ 30, medium 10–29, low < 10
    median_ppsf             high ≥ 30, medium 10–29, low < 10
    median_dom              high ≥ 20, medium 8–19,  low < 8
    sale_to_list_ratio      high ≥ 30, medium 10–29, low < 10
    months_of_supply        high ≥ 5,  medium 2–4,   low < 2
    pct_with_price_drops    high ≥ 50, medium 20–49, low < 20
    school_premium          high ≥ 20, medium 10–19, low < 10
"""

from __future__ import annotations

from decimal import Decimal
from typing import TypedDict

from ._types import ConfidenceResult, ConfidenceTier, MetricValue


class _SampleThresholds(TypedDict):
    high: int
    medium: int


# Per ``docs/design.md`` §5.2.
SAMPLE_THRESHOLDS: dict[str, _SampleThresholds] = {
    "median_sale_price": {"high": 30, "medium": 10},
    "median_list_price": {"high": 30, "medium": 10},
    "median_ppsf": {"high": 30, "medium": 10},
    "median_dom": {"high": 20, "medium": 8},
    "sale_to_list_ratio": {"high": 30, "medium": 10},
    "months_of_supply": {"high": 5, "medium": 2},
    "pct_with_price_drops": {"high": 50, "medium": 20},
    "school_premium": {"high": 20, "medium": 10},
}

# Disagreement thresholds (relative, e.g. 0.05 = 5%) and their associated
# point penalties — both per ``docs/design.md`` §3.3. ``None`` means the
# metric is always shown side-by-side with no scalar penalty (e.g.,
# ``school_rating``).
DISAGREEMENT_THRESHOLDS: dict[str, tuple[Decimal, int] | None] = {
    "median_sale_price": (Decimal("0.05"), 15),
    "median_list_price": (Decimal("0.05"), 15),
    "median_ppsf": (Decimal("0.05"), 15),
    "median_dom": (Decimal("0.30"), 20),
    "active_listings": (Decimal("0.10"), 10),
    "inventory": (Decimal("0.10"), 10),
    "school_rating": None,
    # Mortgage-rate disagreement is in absolute percentage points; we
    # special-case it in ``confidence_score`` because the unit differs.
    "mortgage_rate": None,
    # Other Phase-1 metrics — keep the structure visible.
    "sale_to_list_ratio": (Decimal("0.05"), 10),
    "months_of_supply": (Decimal("0.10"), 10),
    "pct_with_price_drops": (Decimal("0.10"), 10),
}

# Mortgage rate has its own absolute pp threshold (0.25 percentage points).
RATE_DISAGREEMENT_THRESHOLD_PP = Decimal("0.0025")
RATE_DISAGREEMENT_PENALTY = 10

# Staleness decay. Per ``docs/datamodel.md`` §6:
#
#   confidence = clamp(0, 100, base
#                       - max(0, days_stale - 14)         # decay 1pt/day after 14d
#                       - min(40, 100 / sqrt(sample_size)))
#
# We expose the magic numbers as named constants so the test suite reads
# them rather than the literal values.
STALENESS_GRACE_DAYS = 14
STALENESS_DECAY_PER_DAY = 1

# Tier cutoffs (matching ``phase_weights.py`` documentation).
TIER_HIGH_CUTOFF = 75
TIER_MEDIUM_CUTOFF = 45


def _bucket_score(score: int) -> ConfidenceTier:
    """Map an integer 0–100 score to a tier label."""

    if score >= TIER_HIGH_CUTOFF:
        return "high"
    if score >= TIER_MEDIUM_CUTOFF:
        return "medium"
    return "low"


def _sample_size_penalty(metric_name: str, sample_size: int | None) -> tuple[int, str | None]:
    """Penalty + reason for the metric's sample size.

    Returns ``(penalty, reason)``. ``reason`` is ``None`` when no penalty
    applied, so the caller can skip appending it.
    """

    thresholds = SAMPLE_THRESHOLDS.get(metric_name)
    if thresholds is None:
        # Unknown metric — no per-metric threshold; we don't penalize on
        # sample size, but we do flag the omission to the caller via the
        # ``reasons`` list.
        return 0, f"no per-metric threshold defined for '{metric_name}'"
    if sample_size is None:
        # Without a sample size we cannot bound the standard error;
        # docs/design.md §5.2 requires us to de-emphasize.
        return 30, f"sample size unknown for '{metric_name}'"

    high = thresholds["high"]
    medium = thresholds["medium"]
    if sample_size >= high:
        return 0, None
    if sample_size >= medium:
        return (
            15,
            f"sample size {sample_size} is medium-confidence (need {high}+ for high)",
        )
    return 35, f"sample size {sample_size} is below low-confidence threshold ({medium})"


def _staleness_penalty(age_days: int) -> tuple[int, str | None]:
    """Penalty + reason for the metric's age in days."""

    if age_days <= STALENESS_GRACE_DAYS:
        return 0, None
    decay = (age_days - STALENESS_GRACE_DAYS) * STALENESS_DECAY_PER_DAY
    return decay, f"data is {age_days}d old (>{STALENESS_GRACE_DAYS}d grace; -{decay})"


def _disagreement_penalty(
    metric_name: str,
    disagreement: float | Decimal | None,
) -> tuple[int, str | None]:
    """Penalty + reason for inter-source disagreement.

    ``disagreement`` is the **relative** delta between the two best
    sources, except for ``mortgage_rate`` where it is in absolute
    percentage points.
    """

    if disagreement is None:
        return 0, None
    # Coerce float → Decimal once so all comparisons are Decimal-clean.
    delta = Decimal(str(disagreement))
    if metric_name == "mortgage_rate":
        if abs(delta) > RATE_DISAGREEMENT_THRESHOLD_PP:
            return (
                RATE_DISAGREEMENT_PENALTY,
                f"mortgage-rate sources disagree by {delta} (>{RATE_DISAGREEMENT_THRESHOLD_PP}pp)",
            )
        return 0, None
    threshold_pair = DISAGREEMENT_THRESHOLDS.get(metric_name)
    if threshold_pair is None:
        # Either we deliberately don't penalize (e.g., school_rating) or
        # the metric isn't in the table; either way: zero penalty, no
        # noise in reasons.
        return 0, None
    threshold, penalty = threshold_pair
    if abs(delta) > threshold:
        pct = (abs(delta) * Decimal("100")).quantize(Decimal("0.1"))
        return (
            penalty,
            f"sources disagree by {pct}% (>{threshold * 100:.1f}% threshold) on '{metric_name}'",
        )
    return 0, None


def confidence_score(
    metric: MetricValue,
    age_days: int,
    disagreement: float | Decimal | None,
) -> ConfidenceResult:
    """Compute confidence for a metric value.

    Per ``docs/contracts.md`` C3 the signature is fixed:
    ``(metric, age_days, disagreement) -> ConfidenceResult``.

    Algorithm: start at 100, subtract sample-size penalty, staleness
    penalty, and disagreement penalty. Clamp to [0, 100]. Bucket into
    tier. Concatenate non-None reasons in the order they were detected
    (sample → staleness → disagreement).

    The function is deterministic: no clock, no random, no I/O.
    """

    if age_days < 0:
        raise ValueError(f"age_days must be non-negative, got {age_days}")

    # If the metric value itself is missing, we short-circuit to 0/low so
    # the UI can render the missing-data state without further computation.
    if metric.value is None:
        return ConfidenceResult(
            score=0,
            tier="low",
            reasons=[f"no value reported for '{metric.metric_name}'"],
        )

    score = 100
    reasons: list[str] = []

    sample_penalty, sample_reason = _sample_size_penalty(metric.metric_name, metric.sample_size)
    score -= sample_penalty
    if sample_reason is not None:
        reasons.append(sample_reason)

    stale_penalty, stale_reason = _staleness_penalty(age_days)
    score -= stale_penalty
    if stale_reason is not None:
        reasons.append(stale_reason)

    disagreement_penalty, disagreement_reason = _disagreement_penalty(
        metric.metric_name, disagreement
    )
    score -= disagreement_penalty
    if disagreement_reason is not None:
        reasons.append(disagreement_reason)

    # Clamp.
    if score < 0:
        score = 0
    elif score > 100:  # pragma: no cover - score starts at 100; all penalties are non-negative
        score = 100

    return ConfidenceResult(score=score, tier=_bucket_score(score), reasons=reasons)


__all__ = [
    "DISAGREEMENT_THRESHOLDS",
    "RATE_DISAGREEMENT_PENALTY",
    "RATE_DISAGREEMENT_THRESHOLD_PP",
    "SAMPLE_THRESHOLDS",
    "STALENESS_DECAY_PER_DAY",
    "STALENESS_GRACE_DAYS",
    "TIER_HIGH_CUTOFF",
    "TIER_MEDIUM_CUTOFF",
    "confidence_score",
]
