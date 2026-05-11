"""``bayre-finance`` — pure-function trust-layer for the Bay Area FTHB tool.

Per ``docs/design.md`` §5 and ``docs/contracts.md`` C3, this package
exports four pure functions and the dataclasses they consume:

    affordability(buyer, market_ctx) -> AffordabilityResult
    monthly_cost(price, area_ctx) -> MonthlyCost
    compute_phase(snapshot, history) -> PhaseResult
    cost_of_waiting(buyer, area_id, params) -> WaitGrid
    confidence_score(metric, age_days, disagreement) -> ConfidenceResult

No I/O, no clock, no random, no globals. Coverage gate: ≥ 95% line
coverage on every module (enforced by the root ``pyproject.toml``).
"""

from __future__ import annotations

from ._types import (
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
)
from .affordability import affordability, monthly_cost
from .confidence import confidence_score
from .cost_of_waiting import cost_of_waiting
from .timing import compute_phase

__all__ = [
    "AffordabilityResult",
    "AreaContext",
    "Buyer",
    "ConfidenceResult",
    "ConfidenceTier",
    "County",
    "LoanType",
    "MarketContext",
    "MarketPhase",
    "MetricValue",
    "MonthlyCost",
    "PhaseComponents",
    "PhaseHistory",
    "PhaseResult",
    "SnapshotForPhase",
    "WaitCell",
    "WaitGrid",
    "WaitParams",
    "affordability",
    "compute_phase",
    "confidence_score",
    "cost_of_waiting",
    "monthly_cost",
]
