/**
 * Property tests using fast-check, mirroring the Hypothesis invariants on
 * the Python side (`packages/finance/tests/test_*.py`):
 *
 *   - affordability: monotonicity (more income → ≥ same affordability).
 *   - monthly_cost: conservation (components sum to total).
 *   - compute_phase: idempotence (deterministic given inputs).
 *   - cost_of_waiting: 9 cells in row-major order.
 *
 * These run against the TS implementation only — the golden-file test
 * separately enforces parity with the Python output. Together they
 * triangulate "the TS is correct AND it agrees with Python".
 */

import { describe, expect, it } from "vitest";
import fc from "fast-check";

import {
  Decimal,
  affordability,
  computePhase,
  costOfWaiting,
  monthlyCost,
  type AreaContext,
  type Buyer,
  type MarketContext,
  type PhaseHistory,
  type SnapshotForPhase,
  type WaitParams,
} from "../src/index.js";

// ---------------------------------------------------------------------------
// Arbitraries
// ---------------------------------------------------------------------------

/** Build a Decimal from a JS number deterministically (avoids float drift
 *  by routing through a fixed-precision string). */
function dec(n: number, dp = 4): Decimal {
  // toFixed pads exact decimals; we trust the dp choice per call site.
  return new Decimal(n.toFixed(dp));
}

const buyerArb: fc.Arbitrary<Buyer> = fc.record({
  income: fc.integer({ min: 50_000, max: 1_000_000 }),
  monthlyDebts: fc.integer({ min: 0, max: 5_000 }),
  down: fc.integer({ min: 10_000, max: 1_500_000 }),
  rate: fc.integer({ min: 300, max: 1_000 }), // 3.00% – 10.00%, scaled by 1e4
  termYears: fc.constantFrom(15, 30),
}).map(({ income, monthlyDebts, down, rate, termYears }) => ({
  annual_income: new Decimal(String(income)),
  monthly_debts: new Decimal(String(monthlyDebts)),
  down_payment: new Decimal(String(down)),
  rate: new Decimal((rate / 10_000).toFixed(4)),
  term_years: termYears,
  credit_score_band: "740-779",
  base_income: null,
  bonus_income: null,
  rsu_income: null,
}));

const marketArb: fc.Arbitrary<MarketContext> = fc.record({
  county: fc.constantFrom(
    "alameda",
    "santa_clara",
    "contra_costa",
    "san_mateo",
    "san_francisco",
    "marin",
    "sonoma",
    "napa",
    "solano",
  ) as fc.Arbitrary<MarketContext["county"]>,
}).map((r) => ({ county: r.county, area_median_price: null }));

const areaArb: fc.Arbitrary<AreaContext> = fc.record({
  county: marketArb.map((m) => m.county),
  taxRate: fc.integer({ min: 1000, max: 1300 }), // 1.00% – 1.30% scaled 1e5
  mello: fc.integer({ min: 0, max: 5_000 }),
  hoa: fc.integer({ min: 0, max: 800 }),
  insurance: fc.integer({ min: 1_500, max: 8_000 }),
  rate: fc.integer({ min: 300, max: 1_000 }),
  termYears: fc.constantFrom(15, 30),
  down: fc.integer({ min: 10_000, max: 1_500_000 }),
}).map((r) => ({
  county: r.county,
  property_tax_rate: new Decimal((r.taxRate / 100_000).toFixed(5)),
  mello_roos_annual: new Decimal(String(r.mello)),
  hoa_monthly: new Decimal(String(r.hoa)),
  insurance_annual: new Decimal(String(r.insurance)),
  wildfire_surcharge_multiplier: new Decimal("1.0"),
  rate: new Decimal((r.rate / 10_000).toFixed(4)),
  term_years: r.termYears,
  down_payment: new Decimal(String(r.down)),
  pmi_annual_rate: new Decimal("0.0055"),
}));

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("monthly_cost: components sum to total", () => {
  it("p_and_i + tax + mello + hoa + insurance + pmi == total for any input", () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 200_000, max: 5_000_000 }),
        areaArb,
        (price, area) => {
          const result = monthlyCost(new Decimal(String(price)), area);
          const sum = result.p_and_i
            .add(result.tax)
            .add(result.mello)
            .add(result.hoa)
            .add(result.insurance)
            .add(result.pmi);
          // Conservation up to a single-cent rounding tolerance, mirroring
          // the Python invariant.
          const diff = sum.sub(result.total).abs();
          if (diff.gt(new Decimal("0.01"))) {
            throw new Error(
              `Conservation violated: components=${sum.toString()} total=${result.total.toString()}`,
            );
          }
          return true;
        },
      ),
      { numRuns: 100 },
    );
  });
});

describe("affordability: monotone in income", () => {
  it("doubling income never *decreases* the comfortable price", () => {
    fc.assert(
      fc.property(
        buyerArb,
        marketArb,
        (buyer, market) => {
          const lo = affordability(buyer, market);
          const doubled: Buyer = {
            ...buyer,
            annual_income: buyer.annual_income.mul(new Decimal("2")),
          };
          const hi = affordability(doubled, market);
          return hi.comfortable.gte(lo.comfortable);
        },
      ),
      { numRuns: 50 },
    );
  });
});

describe("compute_phase: idempotent", () => {
  it("calling twice with identical inputs returns identical outputs", () => {
    const snapshotArb: fc.Arbitrary<SnapshotForPhase> = fc.record({
      mos: fc.integer({ min: 1, max: 100 }), // 0.1 – 10.0 scaled 1e1
      s2l_4w: fc.integer({ min: 90, max: 120 }), // 0.90 – 1.20 scaled 1e2
      s2l_12w: fc.integer({ min: 90, max: 120 }),
      pdrop: fc.integer({ min: 0, max: 60 }), // 0.00 – 0.60 scaled 1e2
      median_dom: fc.integer({ min: 5, max: 100 }),
      active_listings: fc.integer({ min: 10, max: 1000 }),
      sample_size: fc.integer({ min: 0, max: 500 }),
      confidence_score: fc.integer({ min: 0, max: 100 }),
    }).map((r) => ({
      months_of_supply: dec(r.mos / 10, 1),
      s2l_4w: dec(r.s2l_4w / 100, 2),
      s2l_12w: dec(r.s2l_12w / 100, 2),
      pct_with_price_drops: dec(r.pdrop / 100, 2),
      median_dom: r.median_dom,
      active_listings: r.active_listings,
      sample_size: r.sample_size,
      confidence_score: r.confidence_score,
    }));

    const historyArb: fc.Arbitrary<PhaseHistory> = fc.record({
      baseline_dom: fc.integer({ min: 5, max: 100 }),
      inv_yoy: fc.integer({ min: -50, max: 100 }),
      previous_phase: fc.constantFrom("unknown", "peak", "cooling", "trough", "recovery") as fc.Arbitrary<
        PhaseHistory["previous_phase"]
      >,
    }).map((r) => ({
      baseline_dom: r.baseline_dom,
      inv_yoy: dec(r.inv_yoy / 100, 2),
      previous_phase: r.previous_phase,
    }));

    fc.assert(
      fc.property(snapshotArb, historyArb, (snap, hist) => {
        const a = computePhase(snap, hist);
        const b = computePhase(snap, hist);
        // Compare key fields; nested Decimals must compare via toString.
        return (
          a.phase === b.phase &&
          a.confidence === b.confidence &&
          a.buyer_pressure === b.buyer_pressure &&
          a.seller_pressure === b.seller_pressure &&
          a.clock_position.toString() === b.clock_position.toString()
        );
      }),
      { numRuns: 100 },
    );
  });
});

describe("cost_of_waiting: 9 cells in row-major order", () => {
  it("returns exactly 3 rows × 3 columns and preserves scenario order", () => {
    const params: WaitParams = {
      target_price: new Decimal("1200000"),
      wait_horizon_months: 12,
      current_rate: new Decimal("0.0675"),
      current_rent: new Decimal("3500"),
      area_ctx: {
        county: "alameda",
        property_tax_rate: new Decimal("0.01155"),
        mello_roos_annual: new Decimal("0"),
        hoa_monthly: new Decimal("0"),
        insurance_annual: new Decimal("3500"),
        wildfire_surcharge_multiplier: new Decimal("1.0"),
        rate: new Decimal("0.0675"),
        term_years: 30,
        down_payment: new Decimal("150000"),
        pmi_annual_rate: new Decimal("0.0055"),
      },
      appreciation_scenarios: [
        new Decimal("-0.02"),
        new Decimal("0.03"),
        new Decimal("0.06"),
      ],
      rate_scenarios: [
        new Decimal("-0.005"),
        new Decimal("0.000"),
        new Decimal("0.005"),
      ],
    };

    const buyer: Buyer = {
      annual_income: new Decimal("300000"),
      monthly_debts: new Decimal("0"),
      down_payment: new Decimal("150000"),
      rate: new Decimal("0.0675"),
      term_years: 30,
      credit_score_band: "740-779",
      base_income: null,
      bonus_income: null,
      rsu_income: null,
    };

    const grid = costOfWaiting(buyer, "alameda::fremont", params);
    expect(grid.cells.length).toBe(3);
    for (let i = 0; i < 3; i++) {
      const row = grid.cells[i]!;
      expect(row.length).toBe(3);
      for (let j = 0; j < 3; j++) {
        const cell = row[j]!;
        expect(cell.appreciation_annual.toString()).toBe(
          params.appreciation_scenarios[i]!.toString(),
        );
        expect(cell.rate_change.toString()).toBe(
          params.rate_scenarios[j]!.toString(),
        );
      }
    }
  });
});
