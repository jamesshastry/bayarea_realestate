/**
 * Pinned constants for 2026 Bay Area real-estate finance.
 *
 * Hand-mirrored from `packages/finance/tax_rules.py` — citations and values
 * MUST match. Anyone updating one side must update the other in the same
 * commit; the golden-file parity tests catch silent drift.
 *
 * Per `docs/design.md` §5: this file is *only* constants and small lookup
 * helpers. No I/O, no parsing, no clock reads. Helpers operate purely on
 * their parameters.
 */

import { Decimal } from "./decimal.js";
import type { County, LoanType } from "./types.js";

// ---------------------------------------------------------------------------
// Year + revision metadata
// ---------------------------------------------------------------------------

export const EFFECTIVE_YEAR = 2026;
export const LAST_UPDATED = "2026-05-11";

// ---------------------------------------------------------------------------
// Conforming + high-balance loan limits per county
// ---------------------------------------------------------------------------
//
// 2026 FHFA conforming loan limits.
//
// Source: FHFA "Conforming Loan Limit (CLL) Values" published annually in
// late November for the following calendar year. The 2026 values were
// published on 2025-11-25 at:
//   https://www.fhfa.gov/news/news-release/fhfa-announces-2026-conforming-loan-limits
//
// All nine Bay Area counties (Alameda, Contra Costa, Marin, Napa,
// San Francisco, San Mateo, Santa Clara, Solano, Sonoma) are designated
// "high-cost areas" by FHFA, which means the high-balance ceiling applies
// rather than the national baseline. The high-balance ceiling = 150% of
// the baseline conforming limit, rounded.
//
// **TODO(verify):** the 2026 *exact* baseline figure below is the
// author's projection from the FHFA's published methodology (the agency
// announces the precise number in late November of the prior year).
// Replace with the authoritative published value once the FHFA press
// release URL above resolves to the final FY2026 PDF.

/** Baseline conforming (one-unit, single-family) limit, applied nation-wide. */
export const CONFORMING_BASELINE_2026 = new Decimal("806500");

/** High-balance ceiling (one-unit) for high-cost-area counties.
 *  Per FHFA: 150% of baseline, rounded to the nearest $50. */
export const HIGH_BALANCE_CEILING_2026 = new Decimal("1209750");

/** Per-county one-unit conforming limit. Every Bay Area county is a
 *  "high-cost area" → the high-balance ceiling applies. We still
 *  enumerate them per-county so the structure mirrors the FHFA table; if
 *  a future year demotes a county we change one value here. */
export const COUNTY_LOAN_LIMITS_2026: Record<County, Decimal> = {
  alameda: HIGH_BALANCE_CEILING_2026,
  santa_clara: HIGH_BALANCE_CEILING_2026,
  contra_costa: HIGH_BALANCE_CEILING_2026,
  san_mateo: HIGH_BALANCE_CEILING_2026,
  san_francisco: HIGH_BALANCE_CEILING_2026,
  marin: HIGH_BALANCE_CEILING_2026,
  sonoma: HIGH_BALANCE_CEILING_2026,
  napa: HIGH_BALANCE_CEILING_2026,
  solano: HIGH_BALANCE_CEILING_2026,
};

// ---------------------------------------------------------------------------
// FHA limits (per HUD; lower than FHFA)
// ---------------------------------------------------------------------------
//
// 2026 FHA loan limits — high-cost-area ceiling is set at 150% of the
// FHFA conforming limit.
//
// Source: HUD Mortgagee Letter (annual; typically issued early December).
// 2026: https://www.hud.gov/hudprograms/sfh/lender/origination/mortgage-limits
//
// **TODO(verify):** confirm the 2026 HUD ML once published. FHA's
// high-cost ceiling formula is statutorily set (150% of FHFA conforming
// floor), so this should match HIGH_BALANCE_CEILING_2026 for the nine
// Bay Area counties.

export const FHA_HIGH_COST_CEILING_2026 = new Decimal("1209750");

// ---------------------------------------------------------------------------
// Per-county effective property tax rate
// ---------------------------------------------------------------------------
//
// Effective property tax rate = (Prop 13 1% base) + voter-approved bonds
// + special assessments. Figures below are typical *effective* rates in
// the 2025 tax roll (year-of-assessment), per each county's
// assessor-recorder office:
//
// - Alameda County: ~1.13–1.18% effective; we use the median.
//   https://www.acgov.org/auditor/tax/calc/index.htm
// - Santa Clara County: ~1.10–1.15% effective.
//   https://www.sccassessor.org/index.php/component/k2/item/40-property-tax-rates
// - Contra Costa: ~1.10–1.20%
//   https://www.contracosta.ca.gov/198/Tax-Collector
// - San Mateo: ~1.10–1.18%
//   https://www.smcgov.org/tax
// - San Francisco: ~1.18–1.22% (city-county; higher voter assessments)
//   https://sfassessor.org/property-information/property-tax-rates
// - Marin: ~1.10–1.15%
//   https://www.marincounty.org/depts/dr/divisions/property-tax-info
// - Sonoma: ~1.10–1.20%
// - Napa: ~1.05–1.15%
// - Solano: ~1.10–1.15%
//
// We pin a representative single number per county. Parcel-level data
// (when ingested in Phase 2+) overrides this — see `MonthlyCost`'s
// `tax` field, which uses the parcel's actual `current_tax_rate` when
// available.

export const COUNTY_PROPERTY_TAX_RATES_2026: Record<County, Decimal> = {
  alameda: new Decimal("0.01155"),
  santa_clara: new Decimal("0.01125"),
  contra_costa: new Decimal("0.01150"),
  san_mateo: new Decimal("0.01140"),
  san_francisco: new Decimal("0.01200"),
  marin: new Decimal("0.01125"),
  sonoma: new Decimal("0.01150"),
  napa: new Decimal("0.01100"),
  solano: new Decimal("0.01125"),
};

// ---------------------------------------------------------------------------
// Prop 13
// ---------------------------------------------------------------------------
//
// Proposition 13 (1978) caps annual increases in assessed value at 2%
// unless a change of ownership or new construction triggers reassessment.
// Per CA Constitution Art. XIIIA §2(b):
//   https://leginfo.legislature.ca.gov/faces/codes_displayText.xhtml?lawCode=CONS&division=&title=&part=&chapter=&article=XIIIA
//
// See `docs/glossary/prop-13.md` and `docs/glossary/prop-13-base-year.md`.

/** 2% per year on assessed value. */
export const PROP_13_ANNUAL_CAP = new Decimal("0.02");
/** 1% statewide base rate (ad valorem). */
export const PROP_13_BASE_RATE = new Decimal("0.01");

// ---------------------------------------------------------------------------
// SALT cap (federal)
// ---------------------------------------------------------------------------
//
// The state-and-local-tax (SALT) deduction is capped at $10,000 per
// return per IRC §164(b)(6), enacted by the Tax Cuts and Jobs Act of 2017.
// As of the 2026 filing year the cap is still $10K; future legislation
// could change it.
//
// Source: 26 USC 164(b)(6):
//   https://www.law.cornell.edu/uscode/text/26/164
//
// See `docs/glossary/salt.md`.

export const SALT_CAP_2026 = new Decimal("10000");

// ---------------------------------------------------------------------------
// PMI
// ---------------------------------------------------------------------------
//
// Private Mortgage Insurance applies when the loan-to-value ratio at
// origination exceeds 80% (i.e., down payment under 20%). Standard MI
// rates published in 2025 for a 740–759 FICO band run roughly 0.45–0.65%
// of the original loan amount per year.
//
// Sources:
//   - MGIC rate cards (2025): https://www.mgic.com/underwriting/rates
//   - Genworth rate cards (2025): https://miservicing.genworth.com/rates
//
// We use 0.55% as a reasonable mid-range default for Phase-1 modeling.
// When a per-buyer credit-band rate becomes available we'll plumb it
// through `AreaContext.pmi_annual_rate` (already a parameter).
//
// See `docs/glossary/pmi.md`.

export const PMI_DEFAULT_ANNUAL_RATE = new Decimal("0.0055");
/** PMI applies above this LTV at origination. */
export const PMI_LTV_THRESHOLD = new Decimal("0.80");

// ---------------------------------------------------------------------------
// DTI thresholds
// ---------------------------------------------------------------------------
//
// Per the GSE underwriting standard: front-end (housing-only) DTI 28%,
// back-end (housing + all monthly debts) DTI 36%. Some loan programs
// accept higher back-end (43% qualified-mortgage ceiling, up to 50% in
// manual underwriting), but for FTHB *comfort* framing we anchor on
// 28/36.
//
// Source: Fannie Mae Selling Guide B3-6 (Liabilities & DTI).
//   https://selling-guide.fanniemae.com/sel/b3-6
//
// See `docs/glossary/dti.md`.

export const DTI_FRONT_END = new Decimal("0.28");
export const DTI_BACK_END = new Decimal("0.36");

// ---------------------------------------------------------------------------
// Down payment minimums per loan type
// ---------------------------------------------------------------------------
//
// Conforming + high-balance: 3% (HomeReady / Home Possible) or 5%
// (standard) — we anchor on 5% for Phase 1, since the 3% products carry
// extra eligibility friction.
//
// Jumbo: typically 10–20% depending on lender; we anchor on 10% as the
// common FTHB-friendly minimum.
//
// FHA: 3.5% with FICO ≥ 580 (per HUD 4000.1).
//
// Sources cited inline below.

export const MIN_DOWN_PAYMENT_PCT: Record<LoanType, Decimal> = {
  // Fannie Mae Selling Guide B5-6: standard min 5%.
  conforming: new Decimal("0.05"),
  high_balance: new Decimal("0.05"),
  // Industry-typical jumbo minimum (no GSE backing).
  jumbo: new Decimal("0.10"),
  // HUD 4000.1 II.A.2: 3.5% with FICO ≥ 580.
  fha: new Decimal("0.035"),
};

// ---------------------------------------------------------------------------
// Helpers (pure)
// ---------------------------------------------------------------------------

/** Return the 2026 one-unit conforming loan limit for `county`.
 *  Throws for an unmodeled county — that is intentional; we'd rather fail
 *  loudly than silently default to the national baseline (which is wrong
 *  for every Bay Area county). */
export function conformingLimit(county: County): Decimal {
  const v = COUNTY_LOAN_LIMITS_2026[county];
  if (!v) throw new Error(`Unmodeled county: ${county}`);
  return v;
}

/** Return the 2026 FHA loan limit for `county`. For all nine Bay Area
 *  counties this equals the FHA high-cost ceiling. */
export function fhaLimit(county: County): Decimal {
  if (county in COUNTY_LOAN_LIMITS_2026) {
    return FHA_HIGH_COST_CEILING_2026;
  }
  throw new Error(`Unmodeled county: ${county}`);
}

/** Return the 2026 effective property-tax rate for `county`. Use the
 *  parcel's actual `current_tax_rate` when known; this is the fallback
 *  for area-typical estimation. */
export function propertyTaxRate(county: County): Decimal {
  const v = COUNTY_PROPERTY_TAX_RATES_2026[county];
  if (!v) throw new Error(`Unmodeled county: ${county}`);
  return v;
}

/**
 * Sentinel returned by `loanLimit` for the jumbo case where there is no
 * agency-imposed ceiling. The Python side returns `Decimal("Infinity")`;
 * we use a very large finite Decimal here because a true "infinity"
 * comparison would have to be plumbed everywhere, and the finance
 * modules only ever use this in `min(...)` comparisons against finite
 * prices below `_PRICE_CEILING` ($50M). Keep this above the search
 * ceiling so the comparison semantics match exactly.
 */
const JUMBO_NO_LIMIT = new Decimal("999999999999"); // ~$1e12 — safely "infinite" for FTHB sizes.

/** Return the principal-balance ceiling for `loan_type` in `county`.
 *  Jumbo has no agency-imposed ceiling — see `JUMBO_NO_LIMIT`. */
export function loanLimit(county: County, loanType: LoanType): Decimal {
  if (loanType === "conforming") {
    // Conforming alone uses the *baseline* (sub-high-balance) limit, so
    // the FTHB sees the cheaper-rate option separately from
    // high-balance. Mirrors how lenders quote.
    return CONFORMING_BASELINE_2026;
  }
  if (loanType === "high_balance") {
    return conformingLimit(county);
  }
  if (loanType === "fha") {
    return fhaLimit(county);
  }
  if (loanType === "jumbo") {
    return JUMBO_NO_LIMIT;
  }
  throw new Error(`Unknown loan_type: ${loanType as string}`);
}

/** Internal flag to recognize the jumbo "infinite" sentinel without
 *  exporting the magic number. */
export function isJumboSentinel(d: Decimal): boolean {
  return d.eq(JUMBO_NO_LIMIT);
}
