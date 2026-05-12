/**
 * Glue between live snapshot data and the @bayre/finance pure functions.
 *
 * Phase 1 teaser: given a city's median sale price, compute the monthly-cost
 * breakdown using sensible defaults. The full affordability calculator (which
 * takes user income / DTI inputs) lands as a follow-up — this just shows
 * "what does the median home in this city cost per month."
 *
 * Defaults are deliberately conservative; show-the-math values are exposed in
 * the UI so users can see what we assumed.
 */

import {
  Decimal,
  COUNTY_PROPERTY_TAX_RATES_2026,
  monthlyCost,
  type AreaContext,
  type County,
  type MonthlyCost,
} from "@bayre/finance";

// Maps the human county name from `geographic_area.name` to the County enum
// the finance package uses. Keep in sync with packages/finance/_ts_export/src/types.ts.
const COUNTY_NAME_TO_KEY: Record<string, County> = {
  "Alameda County": "alameda",
  "Santa Clara County": "santa_clara",
  "Contra Costa County": "contra_costa",
  "San Mateo County": "san_mateo",
  "San Francisco": "san_francisco",
  "Marin County": "marin",
  "Sonoma County": "sonoma",
  "Napa County": "napa",
  "Solano County": "solano",
};

/**
 * Default Phase 1 buyer assumptions — deliberately neutral so the median-cost
 * calc is interpretable. Real `affordability()` UI will let users override.
 */
export const DEFAULTS = {
  /** Mortgage rate (annual). 6.5% as a sane stand-in until the FRED adapter
   *  is wired and we can read MORTGAGE30US live. */
  rateAnnual: new Decimal("0.065"),
  termYears: 30,
  /** Down-payment fraction of the price. 20% avoids PMI by default. */
  downPaymentPct: new Decimal("0.20"),
  /** Annual homeowner's insurance — typical Bay Area SFH baseline. The
   *  wildfire surcharge (FHSZ-based) layers on top in Phase 5. */
  insuranceAnnual: new Decimal("1800"),
  /** Mello-Roos default = 0/yr; new-construction Tri-Valley overrides this
   *  manually for now (Dublin / Pleasanton-east). The Phase 2 assessor adapter
   *  populates this per parcel. */
  melloRoosAnnual: new Decimal("0"),
  /** Most Bay Area SFH have no HOA; condo defaults will diverge in Phase 2. */
  hoaMonthly: new Decimal("0"),
} as const;

export function countyKeyFromName(name: string): County | null {
  return COUNTY_NAME_TO_KEY[name] ?? null;
}

/**
 * Compute the monthly-cost breakdown for a city's median home using DEFAULTS.
 * Returns null when the county doesn't map (e.g. snapshot for an out-of-Bay-
 * Area metro).
 */
export function medianMonthlyCost(
  medianPrice: Decimal,
  countyName: string,
): MonthlyCost | null {
  const county = countyKeyFromName(countyName);
  if (county === null) return null;

  const downPayment = medianPrice.mul(DEFAULTS.downPaymentPct);
  const propertyTaxRate =
    COUNTY_PROPERTY_TAX_RATES_2026[county] ?? new Decimal("0.0125");

  const ctx: AreaContext = {
    county,
    property_tax_rate: propertyTaxRate,
    mello_roos_annual: DEFAULTS.melloRoosAnnual,
    hoa_monthly: DEFAULTS.hoaMonthly,
    insurance_annual: DEFAULTS.insuranceAnnual,
    wildfire_surcharge_multiplier: new Decimal("1"),
    rate: DEFAULTS.rateAnnual,
    term_years: DEFAULTS.termYears,
    down_payment: downPayment,
    pmi_annual_rate: new Decimal("0.0055"),
  };

  return monthlyCost(medianPrice, ctx);
}
