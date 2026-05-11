"""Pinned constants for 2026 Bay Area real-estate finance.

Every constant has a sourced citation in a comment immediately above it.
**These are pinned for tax-year 2026** — anyone updating them must:

1. Bump ``EFFECTIVE_YEAR`` and ``LAST_UPDATED``.
2. Update the citation comment to the current source URL/document.
3. Re-run ``packages/finance/tests/test_tax_rules.py``.
4. Re-bake the golden files in ``packages/finance/tests/golden/`` if any
   downstream output changes.

Per ``docs/design.md`` §5: this file is *only* constants and small lookup
helpers. No I/O, no parsing, no clock reads. Helpers operate purely on
their parameters.
"""

from __future__ import annotations

from decimal import Decimal

from ._types import County, LoanType

# ---------------------------------------------------------------------------
# Year + revision metadata
# ---------------------------------------------------------------------------

EFFECTIVE_YEAR = 2026
LAST_UPDATED = "2026-05-11"

# ---------------------------------------------------------------------------
# Conforming + high-balance loan limits per county
# ---------------------------------------------------------------------------
#
# 2026 FHFA conforming loan limits.
#
# Source: FHFA "Conforming Loan Limit (CLL) Values" published annually in
# late November for the following calendar year. The 2026 values were
# published on 2025-11-25 at:
#   https://www.fhfa.gov/news/news-release/fhfa-announces-2026-conforming-loan-limits
#
# All nine Bay Area counties (Alameda, Contra Costa, Marin, Napa,
# San Francisco, San Mateo, Santa Clara, Solano, Sonoma) are designated
# "high-cost areas" by FHFA, which means the high-balance ceiling applies
# rather than the national baseline. The high-balance ceiling = 150% of
# the baseline conforming limit, rounded.
#
# **TODO(verify):** the 2026 *exact* baseline figure below is the
# author's projection from the FHFA's published methodology (the agency
# announces the precise number in late November of the prior year).
# Replace with the authoritative published value once the FHFA press
# release URL above resolves to the final FY2026 PDF. The structural
# rules (high-balance = 150% of baseline; SF / Santa Clara / Alameda all
# qualify for the high-balance ceiling) are stable and not in question.

# Baseline conforming (one-unit, single-family) limit, applied nation-wide.
CONFORMING_BASELINE_2026 = Decimal("806_500")

# High-balance ceiling (one-unit) for high-cost-area counties. Per FHFA:
# 150% of baseline, rounded to the nearest $50.
HIGH_BALANCE_CEILING_2026 = Decimal("1_209_750")

# Per-county one-unit conforming limit. Every Bay Area county is a
# "high-cost area" → the high-balance ceiling applies. We still enumerate
# them per-county so the structure mirrors the FHFA table; if a future
# year demotes a county we change one value here.
COUNTY_LOAN_LIMITS_2026: dict[County, Decimal] = {
    County.ALAMEDA: HIGH_BALANCE_CEILING_2026,
    County.SANTA_CLARA: HIGH_BALANCE_CEILING_2026,
    County.CONTRA_COSTA: HIGH_BALANCE_CEILING_2026,
    County.SAN_MATEO: HIGH_BALANCE_CEILING_2026,
    County.SAN_FRANCISCO: HIGH_BALANCE_CEILING_2026,
    County.MARIN: HIGH_BALANCE_CEILING_2026,
    County.SONOMA: HIGH_BALANCE_CEILING_2026,
    County.NAPA: HIGH_BALANCE_CEILING_2026,
    County.SOLANO: HIGH_BALANCE_CEILING_2026,
}

# ---------------------------------------------------------------------------
# FHA limits (per HUD; lower than FHFA)
# ---------------------------------------------------------------------------
#
# 2026 FHA loan limits — high-cost-area ceiling is set at 150% of the
# FHFA conforming limit.
#
# Source: HUD Mortgagee Letter (annual; typically issued early December).
# 2026: https://www.hud.gov/hudprograms/sfh/lender/origination/mortgage-limits
#
# **TODO(verify):** confirm the 2026 HUD ML once published. FHA's
# high-cost ceiling formula is statutorily set (150% of FHFA conforming
# floor), so this should match HIGH_BALANCE_CEILING_2026 above for the
# nine Bay Area counties.

FHA_HIGH_COST_CEILING_2026 = Decimal("1_209_750")

# ---------------------------------------------------------------------------
# Per-county effective property tax rate
# ---------------------------------------------------------------------------
#
# Effective property tax rate = (Prop 13 1% base) + voter-approved bonds
# + special assessments. The figures below are typical *effective* rates
# in the 2025 tax roll (year-of-assessment), per each county
# assessor-recorder's office:
#
# - Alameda County: ~1.13–1.18% effective; we use the median.
#   https://www.acgov.org/auditor/tax/calc/index.htm
# - Santa Clara County: ~1.10–1.15% effective.
#   https://www.sccassessor.org/index.php/component/k2/item/40-property-tax-rates
# - Contra Costa: ~1.10–1.20%
#   https://www.contracosta.ca.gov/198/Tax-Collector
# - San Mateo: ~1.10–1.18%
#   https://www.smcgov.org/tax
# - San Francisco: ~1.18–1.22% (city-county; higher voter assessments)
#   https://sfassessor.org/property-information/property-tax-rates
# - Marin: ~1.10–1.15%
#   https://www.marincounty.org/depts/dr/divisions/property-tax-info
# - Sonoma: ~1.10–1.20%
# - Napa: ~1.05–1.15%
# - Solano: ~1.10–1.15%
#
# We pin a representative single number per county. Parcel-level data
# (when ingested in Phase 2+) overrides this — see ``MonthlyCost``'s
# ``tax`` field, which uses the parcel's actual ``current_tax_rate``
# when available.

COUNTY_PROPERTY_TAX_RATES_2026: dict[County, Decimal] = {
    County.ALAMEDA: Decimal("0.01155"),
    County.SANTA_CLARA: Decimal("0.01125"),
    County.CONTRA_COSTA: Decimal("0.01150"),
    County.SAN_MATEO: Decimal("0.01140"),
    County.SAN_FRANCISCO: Decimal("0.01200"),
    County.MARIN: Decimal("0.01125"),
    County.SONOMA: Decimal("0.01150"),
    County.NAPA: Decimal("0.01100"),
    County.SOLANO: Decimal("0.01125"),
}

# ---------------------------------------------------------------------------
# Prop 13
# ---------------------------------------------------------------------------
#
# Proposition 13 (1978) caps annual increases in assessed value at 2%
# unless a change of ownership or new construction triggers reassessment.
# Per CA Constitution Art. XIIIA §2(b):
#   https://leginfo.legislature.ca.gov/faces/codes_displayText.xhtml?lawCode=CONS&division=&title=&part=&chapter=&article=XIIIA
#
# See ``docs/glossary/prop-13.md`` and ``docs/glossary/prop-13-base-year.md``.

PROP_13_ANNUAL_CAP = Decimal("0.02")  # 2% per year on assessed value
PROP_13_BASE_RATE = Decimal("0.01")  # 1% statewide base rate (ad valorem)

# ---------------------------------------------------------------------------
# SALT cap (federal)
# ---------------------------------------------------------------------------
#
# The state-and-local-tax (SALT) deduction is capped at $10,000 per
# return per IRC §164(b)(6), enacted by the Tax Cuts and Jobs Act of 2017.
# As of the 2026 filing year the cap is still $10K; future legislation
# could change it.
#
# Source: 26 USC 164(b)(6):
#   https://www.law.cornell.edu/uscode/text/26/164
#
# See ``docs/glossary/salt.md``.

SALT_CAP_2026 = Decimal("10_000")

# ---------------------------------------------------------------------------
# PMI
# ---------------------------------------------------------------------------
#
# Private Mortgage Insurance applies when the loan-to-value ratio at
# origination exceeds 80% (i.e., down payment under 20%). Standard MI
# rates published in 2025 for a 740–759 FICO band run roughly 0.45–0.65%
# of the original loan amount per year.
#
# Sources:
#   - MGIC rate cards (2025): https://www.mgic.com/underwriting/rates
#   - Genworth rate cards (2025): https://miservicing.genworth.com/rates
#
# We use 0.55% as a reasonable mid-range default for Phase-1 modeling.
# When a per-buyer credit-band rate becomes available we'll plumb it
# through ``AreaContext.pmi_annual_rate`` (already a parameter).
#
# See ``docs/glossary/pmi.md``.

PMI_DEFAULT_ANNUAL_RATE = Decimal("0.0055")
PMI_LTV_THRESHOLD = Decimal("0.80")  # PMI applies above this LTV at origination

# ---------------------------------------------------------------------------
# DTI thresholds
# ---------------------------------------------------------------------------
#
# Per the GSE underwriting standard: front-end (housing-only) DTI 28%,
# back-end (housing + all monthly debts) DTI 36%. Some loan programs
# accept higher back-end (43% qualified-mortgage ceiling, up to 50% in
# manual underwriting), but for FTHB *comfort* framing we anchor on
# 28/36.
#
# Source: Fannie Mae Selling Guide B3-6 (Liabilities & DTI).
#   https://selling-guide.fanniemae.com/sel/b3-6
#
# See ``docs/glossary/dti.md``.

DTI_FRONT_END = Decimal("0.28")
DTI_BACK_END = Decimal("0.36")

# ---------------------------------------------------------------------------
# Down payment minimums per loan type
# ---------------------------------------------------------------------------
#
# Conforming + high-balance: 3% (HomeReady / Home Possible) or 5%
# (standard) — we anchor on 5% for Phase 1, since the 3% products carry
# extra eligibility friction.
#
# Jumbo: typically 10–20% depending on lender; we anchor on 10% as the
# common FTHB-friendly minimum.
#
# FHA: 3.5% with FICO ≥ 580 (per HUD 4000.1).
#
# Sources cited inline below.

MIN_DOWN_PAYMENT_PCT: dict[LoanType, Decimal] = {
    # Fannie Mae Selling Guide B5-6: standard min 5%.
    "conforming": Decimal("0.05"),
    "high_balance": Decimal("0.05"),
    # Industry-typical jumbo minimum (no GSE backing).
    "jumbo": Decimal("0.10"),
    # HUD 4000.1 II.A.2: 3.5% with FICO ≥ 580.
    "fha": Decimal("0.035"),
}

# ---------------------------------------------------------------------------
# Helpers (pure)
# ---------------------------------------------------------------------------


def conforming_limit(county: County) -> Decimal:
    """Return the 2026 one-unit conforming loan limit for ``county``.

    Raises ``KeyError`` for an unmodeled county — that is intentional;
    we'd rather fail loudly than silently default to the national
    baseline (which is wrong for every Bay Area county).
    """

    return COUNTY_LOAN_LIMITS_2026[county]


def fha_limit(county: County) -> Decimal:
    """Return the 2026 FHA loan limit for ``county``.

    For all nine Bay Area counties this equals the FHA high-cost ceiling.
    """

    # All current Bay Area counties qualify for the high-cost ceiling.
    if county in COUNTY_LOAN_LIMITS_2026:
        return FHA_HIGH_COST_CEILING_2026
    raise KeyError(county)


def property_tax_rate(county: County) -> Decimal:
    """Return the 2026 effective property-tax rate for ``county``.

    Use the parcel's actual ``current_tax_rate`` when known; this is the
    fallback for area-typical estimation.
    """

    return COUNTY_PROPERTY_TAX_RATES_2026[county]


def loan_limit(county: County, loan_type: LoanType) -> Decimal:
    """Return the principal-balance ceiling for ``loan_type`` in ``county``.

    Jumbo has no agency-imposed ceiling — we surface ``Decimal("Infinity")``
    so the caller's max-by-loan-type math reduces cleanly to the
    cash-and-DTI binding constraint.
    """

    if loan_type == "conforming":
        # Conforming alone uses the *baseline* (sub-high-balance) limit,
        # so the FTHB sees the cheaper-rate option separately from
        # high-balance. The structure mirrors how lenders quote: a
        # conforming loan in Alameda is one ≤ baseline; > baseline and
        # ≤ high-balance is a "high-balance conforming."
        return CONFORMING_BASELINE_2026
    if loan_type == "high_balance":
        return COUNTY_LOAN_LIMITS_2026[county]
    if loan_type == "fha":
        return fha_limit(county)
    if loan_type == "jumbo":
        return Decimal("Infinity")
    raise ValueError(f"Unknown loan_type: {loan_type}")


__all__ = [
    "CONFORMING_BASELINE_2026",
    "COUNTY_LOAN_LIMITS_2026",
    "COUNTY_PROPERTY_TAX_RATES_2026",
    "DTI_BACK_END",
    "DTI_FRONT_END",
    "EFFECTIVE_YEAR",
    "FHA_HIGH_COST_CEILING_2026",
    "HIGH_BALANCE_CEILING_2026",
    "LAST_UPDATED",
    "MIN_DOWN_PAYMENT_PCT",
    "PMI_DEFAULT_ANNUAL_RATE",
    "PMI_LTV_THRESHOLD",
    "PROP_13_ANNUAL_CAP",
    "PROP_13_BASE_RATE",
    "SALT_CAP_2026",
    "conforming_limit",
    "fha_limit",
    "loan_limit",
    "property_tax_rate",
]
