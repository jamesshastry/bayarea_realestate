"""Frozen dataclasses for the finance package.

Field names are STABLE — they are mirrored verbatim in the TypeScript port
(``packages/finance/_ts_export/``) and are asserted byte-equal against
``tests/golden/outputs.json``. Renaming a field here is a contract change.

Money is always ``Decimal``. We never use ``float`` for currency. Percentages
and ratios use ``Decimal`` too so the ``Decimal`` arithmetic chain is never
broken (which would silently re-introduce float drift).

Per ``docs/design.md`` §5: pure functions only — no I/O, no clock, no random.
Every input the user might supply, including ``as_of_date``, is a field on a
dataclass below.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Literal

# ---------------------------------------------------------------------------
# Common enums / literal aliases
# ---------------------------------------------------------------------------

LoanType = Literal["conforming", "high_balance", "jumbo", "fha"]
"""Loan-type discriminator used in ``AffordabilityResult.max_by_loan_type``.

The set is fixed by 2026 California FTHB economics (see
``docs/glossary/jumbo.md``). VA loans are intentionally omitted from the
core grid because they are limited to a small slice of FTHBs; product can
add a separate VA path without breaking the C3 contract.
"""

MarketPhase = Literal["peak", "cooling", "trough", "recovery", "unknown"]
"""Market-clock phase per ``docs/datamodel.md`` §6a.

``"unknown"`` is returned when sample size or confidence is too low to
classify reliably (per ``docs/design.md`` §5.3.1).
"""

ConfidenceTier = Literal["low", "medium", "high"]
"""Bucketed confidence tier per ``docs/design.md`` §5.2."""


class County(StrEnum):
    """California counties relevant to Phase-1 conforming-limit rules.

    The 2026 conforming + high-balance limits in ``tax_rules.py`` are pinned
    per county; we enumerate only the counties Phase 1 cares about. Adding a
    new county is a config change in ``tax_rules.py`` AND adding a member
    here — both are tested in ``tests/test_tax_rules.py``.
    """

    ALAMEDA = "alameda"
    SANTA_CLARA = "santa_clara"
    CONTRA_COSTA = "contra_costa"
    SAN_MATEO = "san_mateo"
    SAN_FRANCISCO = "san_francisco"
    MARIN = "marin"
    SONOMA = "sonoma"
    NAPA = "napa"
    SOLANO = "solano"


# ---------------------------------------------------------------------------
# Affordability inputs / outputs
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Buyer:
    """A first-time-home-buyer's financial profile.

    Money fields are gross USD, ``Decimal``. ``credit_score_band`` matches
    the FICO bands stored in ``buyer.credit_score_band`` per
    ``docs/datamodel.md`` §8.1 (e.g., ``"740-779"``).

    ``rate`` is the APR as a ``Decimal`` (e.g., ``Decimal("0.0675")`` for
    6.75%). ``term_years`` is the loan term in whole years (15 or 30 in
    Phase 1).
    """

    annual_income: Decimal
    monthly_debts: Decimal
    down_payment: Decimal
    rate: Decimal
    term_years: int
    credit_score_band: str = "740-779"
    # Tracked separately so the splitting toggle (F-AFF-13) can persist them
    # later. Phase 1 uses only the sum.
    base_income: Decimal | None = None
    bonus_income: Decimal | None = None
    rsu_income: Decimal | None = None


@dataclass(frozen=True)
class MarketContext:
    """Per-area market context the affordability calc needs.

    ``county`` drives the conforming / high-balance / jumbo cutoffs. The
    effective tax + insurance + PMI rates are sourced from
    ``packages/finance/tax_rules.py`` so the function call site does not
    need to know any constants.
    """

    county: County
    # Median list/sale price for the area, used for sanity-check warnings
    # only (not in any monetary computation).
    area_median_price: Decimal | None = None


@dataclass(frozen=True)
class AreaContext:
    """Per-area inputs for the ``monthly_cost`` breakdown.

    ``mello_roos_annual`` is the *parcel-known* annual amount when we have
    it (per ``docs/glossary/mello-roos.md``); when unknown the caller passes
    an area-typical estimate. Either way we never silently zero it out.
    """

    county: County
    property_tax_rate: Decimal  # e.g., Decimal("0.01125") for 1.125%
    mello_roos_annual: Decimal  # 0 if none
    hoa_monthly: Decimal  # 0 if none
    insurance_annual: Decimal
    # Wildfire surcharge multiplier applied on top of insurance — 1.0 means
    # no surcharge (per ``docs/design.md`` §5.1 affordability table).
    wildfire_surcharge_multiplier: Decimal = Decimal("1.0")
    # Loan parameters needed for the P&I and PMI lines.
    rate: Decimal = Decimal("0.0675")
    term_years: int = 30
    down_payment: Decimal = Decimal("0")
    # PMI rate as an annual fraction of the original loan balance (per
    # ``docs/glossary/pmi.md``); applied while LTV > 80%.
    pmi_annual_rate: Decimal = Decimal("0.0055")


@dataclass(frozen=True)
class MonthlyCost:
    """Monthly cost decomposition for a price.

    Conservation: ``p_and_i + tax + mello + hoa + insurance + pmi == total``
    is asserted by Hypothesis tests (``tests/test_affordability.py``).
    """

    price: Decimal
    p_and_i: Decimal
    tax: Decimal
    mello: Decimal
    hoa: Decimal
    insurance: Decimal
    pmi: Decimal
    total: Decimal


@dataclass(frozen=True)
class AffordabilityResult:
    """Affordability compute output (per F-AFF-02 and C3 in contracts.md).

    ``comfortable`` and ``stretch`` are the price points at which the
    front-end DTI 28% and back-end DTI 36% caps bind, respectively.
    ``max_by_loan_type`` is the price ceiling the buyer can finance under
    each loan-type's principal limit (with the same DTI ceiling applied —
    we never report a max above the user's DTI capacity).

    ``binding_constraint`` names the gating rule for the *maximum* row so
    the UI can render the operating-principle-#1 "show the math" tooltip.
    """

    buyer: Buyer
    market_ctx: MarketContext
    comfortable: Decimal
    stretch: Decimal
    max_by_loan_type: dict[str, Decimal]
    binding_constraint: Literal["dti_front", "dti_back", "loan_limit", "cash_on_hand"]
    # The monthly costs at the ``comfortable`` and ``stretch`` price points,
    # for the F-AFF-04 breakdown.
    comfortable_monthly: MonthlyCost
    stretch_monthly: MonthlyCost


# ---------------------------------------------------------------------------
# Timing (Market-Clock) inputs / outputs
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SnapshotForPhase:
    """The minimal slice of ``MarketSnapshot`` ``compute_phase`` needs.

    Field names mirror ``market_snapshot`` columns in
    ``docs/datamodel.md`` §6 verbatim.

    ``s2l_4w`` and ``s2l_12w`` are the 4-week and 12-week medians of
    ``sale_to_list_ratio`` per ``docs/design.md`` §5.3.1.
    """

    months_of_supply: Decimal
    s2l_4w: Decimal
    s2l_12w: Decimal
    pct_with_price_drops: Decimal  # 0–1
    median_dom: int
    active_listings: int
    sample_size: int
    confidence_score: int  # 0–100, inherited from snapshot


@dataclass(frozen=True)
class PhaseHistory:
    """12-week trailing context for ``compute_phase``.

    ``baseline_dom`` is the 12-week trailing median DOM; ``inv_yoy`` is
    active listings YoY change as a fraction (e.g., ``0.10`` = +10%).
    ``previous_phase`` is used for tie-breaking when the (buyer, seller)
    coordinate sits exactly on a quadrant boundary (rare but deterministic).
    """

    baseline_dom: int
    inv_yoy: Decimal
    previous_phase: MarketPhase = "unknown"


@dataclass(frozen=True)
class PhaseComponents:
    """The per-input contributions surfaced to the UI on click.

    Required by operating principle #1 (show the math) — the user must be
    able to see exactly what input drove each pressure score.
    """

    mos: Decimal
    s2l_4w: Decimal
    s2l_12w: Decimal
    pdrop: Decimal
    dom_trend: Decimal  # signed; positive = DOM rising vs. baseline
    inv_yoy: Decimal


@dataclass(frozen=True)
class PhaseResult:
    """Output of ``compute_phase`` per ``docs/design.md`` §5.3.1.

    ``clock_position`` is a continuous 0.0–12.0 angle for the Market Clock
    face. ``buyer_pressure`` and ``seller_pressure`` are 0–100 ints (we
    round once at the boundary so the TS port never has to re-derive
    them).
    """

    phase: MarketPhase
    clock_position: Decimal  # 0.0–12.0
    buyer_pressure: int  # 0–100
    seller_pressure: int  # 0–100
    components: PhaseComponents
    confidence: ConfidenceTier


# ---------------------------------------------------------------------------
# Cost-of-waiting inputs / outputs
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WaitParams:
    """Inputs to ``cost_of_waiting.compute`` per ``docs/design.md`` §5.3.3.

    ``appreciation_scenarios`` and ``rate_scenarios`` are the three points
    along each axis. Defaults are ``(-2%, +3%, +6%)`` annual appreciation
    and ``(-50bp, flat, +50bp)`` rate move, matching the 9-cell grid the
    UI renders.

    ``current_rate`` is today's quoted rate. ``current_rent`` is what the
    buyer pays today (used to size ``rent_paid_during_wait``).

    ``area_ctx`` carries the same tax / insurance / PMI / HOA assumptions
    the affordability module uses — so the "later" monthly payment is
    apples-to-apples with the "now" payment.
    """

    target_price: Decimal
    wait_horizon_months: int  # 3, 6, 12, or 24
    current_rate: Decimal
    current_rent: Decimal
    area_ctx: AreaContext
    # Three appreciation outcomes (annualized). Order is preserved in the
    # output grid so UI rows are stable.
    appreciation_scenarios: tuple[Decimal, Decimal, Decimal] = (
        Decimal("-0.02"),
        Decimal("0.03"),
        Decimal("0.06"),
    )
    # Three rate moves (absolute, in decimal terms — e.g., -0.005 = -50bp).
    rate_scenarios: tuple[Decimal, Decimal, Decimal] = (
        Decimal("-0.005"),
        Decimal("0.000"),
        Decimal("0.005"),
    )


@dataclass(frozen=True)
class WaitCell:
    """One (appreciation × rate) cell in the 9-cell wait grid.

    ``net_dollar_impact``: positive means waiting cost the buyer money,
    negative means waiting saved money. UI is descriptive — see operating
    principle #4.

    ``break_even_rate_drop``: the absolute rate drop (decimal) required
    over ``wait_horizon_months`` to make ``net_dollar_impact == 0``. The
    UI renders this as "rates would need to drop X bp to break even."
    """

    appreciation_annual: Decimal
    rate_change: Decimal
    appreciation_change_dollars: Decimal
    rent_paid_during_wait: Decimal
    monthly_payment_now: Decimal
    monthly_payment_later: Decimal
    cumulative_savings_or_cost: Decimal
    break_even_rate_drop: Decimal
    net_dollar_impact: Decimal


@dataclass(frozen=True)
class WaitGrid:
    """The 3×3 wait grid plus its inputs.

    ``cells`` is row-major: outer index = appreciation scenario, inner
    index = rate scenario. The TS port relies on this order — do not
    sort or reshape downstream.
    """

    target_price: Decimal
    wait_horizon_months: int
    current_rate: Decimal
    cells: list[list[WaitCell]] = field(default_factory=lambda: [])


# ---------------------------------------------------------------------------
# Confidence inputs / outputs
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MetricValue:
    """Mirror of ``docs/contracts.md`` C1's ``MetricValue`` for the slice
    ``confidence_score`` consumes.

    We re-declare it here (rather than importing from ``packages/domain``)
    to honor the constraint that ``packages/finance/`` has no dependencies
    beyond the standard library — see ``docs/design.md`` §5.
    """

    value: Decimal | int | None
    sample_size: int | None
    unit: str
    metric_name: str
    """The metric key from the per-metric thresholds table in
    ``docs/design.md`` §5.2 (e.g., ``"median_sale_price"``)."""


@dataclass(frozen=True)
class ConfidenceResult:
    """Output of ``confidence.confidence_score`` per ``docs/design.md`` §3.3
    + §5.2.

    ``score`` is 0–100, integer. ``tier`` is the bucketed view the UI
    typically renders. ``reasons`` is an ordered list of short strings
    explaining penalties (oldest-first), so the "show the math" tooltip
    can render them verbatim.
    """

    score: int
    tier: ConfidenceTier
    reasons: list[str] = field(default_factory=lambda: [])


# ---------------------------------------------------------------------------
# Re-export marker
# ---------------------------------------------------------------------------

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
]


# Decimal date-stamp pattern: every public function takes ``as_of_date`` as
# an explicit parameter. We export the type alias so callers don't need to
# import ``datetime`` themselves.
AsOfDate = date
