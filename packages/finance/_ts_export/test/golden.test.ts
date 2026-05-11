/**
 * Golden-file parity tests.
 *
 * Loads the *Python-produced* `inputs.json` + `outputs.json` from
 * `packages/finance/tests/golden/`, runs each row through the TypeScript
 * implementation, and asserts byte-equal JSON output.
 *
 * Per `docs/contracts.md` C3, this is the single source of truth for
 * Python ↔ TS parity. CI fails on any drift.
 *
 * The encoder below mirrors the Python `_encode` in
 * `packages/finance/tests/test_golden.py`:
 *   - `Decimal` → string via `Decimal.toString()` (matches Python's
 *     `format(Decimal, "f")`).
 *   - dataclass / interface → object with sorted keys at every level
 *     (the Python file is `json.dumps(..., sort_keys=True)`).
 *   - tuple / list → list of encoded items.
 */

import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import {
  Decimal,
  affordability,
  computePhase,
  confidenceScore,
  costOfWaiting,
  monthlyCost,
  type AreaContext,
  type Buyer,
  type County,
  type MarketContext,
  type MarketPhase,
  type MetricValue,
  type PhaseHistory,
  type SnapshotForPhase,
  type WaitParams,
} from "../src/index.js";

// ---------------------------------------------------------------------------
// Paths — golden files live two directories up, in the Python finance
// package. Don't copy them here: the parity contract is that we read the
// SAME file the Python tests produce.
// ---------------------------------------------------------------------------

const __dirname = dirname(fileURLToPath(import.meta.url));
const GOLDEN_DIR = resolve(__dirname, "..", "..", "tests", "golden");
const INPUTS_PATH = resolve(GOLDEN_DIR, "inputs.json");
const OUTPUTS_PATH = resolve(GOLDEN_DIR, "outputs.json");

// ---------------------------------------------------------------------------
// JSON encoding — Decimal → string, sort keys, recurse arrays/objects.
// Mirrors Python's _encode + json.dumps(..., sort_keys=True).
// ---------------------------------------------------------------------------

function encode(obj: unknown): unknown {
  if (obj === null || obj === undefined) return null;
  if (obj instanceof Decimal) return obj.toString();
  if (Array.isArray(obj)) return obj.map(encode);
  if (typeof obj === "object") {
    const out: Record<string, unknown> = {};
    const keys = Object.keys(obj as Record<string, unknown>).sort();
    for (const k of keys) {
      out[k] = encode((obj as Record<string, unknown>)[k]);
    }
    return out;
  }
  if (typeof obj === "bigint") return String(obj);
  return obj;
}

/** Round-trip through `JSON.stringify` to canonicalize key order and
 *  number formatting — same effect as Python's
 *  `json.dumps(..., sort_keys=True)` on already-sorted dicts. */
function canonical(obj: unknown): string {
  return JSON.stringify(encode(obj));
}

// ---------------------------------------------------------------------------
// Input deserialization — mirrors Python `_build_*` helpers in
// `packages/finance/tests/test_golden.py`.
// ---------------------------------------------------------------------------

function toDec(v: unknown): Decimal {
  if (v === null || v === undefined) {
    throw new Error("expected a Decimal-castable value, got null/undefined");
  }
  return new Decimal(typeof v === "string" ? v : String(v));
}

function buildBuyer(spec: Record<string, unknown>): Buyer {
  return {
    annual_income: toDec(spec.annual_income),
    monthly_debts: toDec(spec.monthly_debts),
    down_payment: toDec(spec.down_payment),
    rate: toDec(spec.rate),
    term_years: Number(spec.term_years),
    credit_score_band: typeof spec.credit_score_band === "string" ? spec.credit_score_band : "740-779",
    base_income: null,
    bonus_income: null,
    rsu_income: null,
  };
}

function buildMarket(spec: Record<string, unknown>): MarketContext {
  return {
    county: spec.county as County,
    area_median_price: null,
  };
}

function buildArea(spec: Record<string, unknown>): AreaContext {
  return {
    county: spec.county as County,
    property_tax_rate: toDec(spec.property_tax_rate),
    mello_roos_annual: toDec(spec.mello_roos_annual),
    hoa_monthly: toDec(spec.hoa_monthly),
    insurance_annual: toDec(spec.insurance_annual),
    wildfire_surcharge_multiplier: toDec(spec.wildfire_surcharge_multiplier),
    rate: toDec(spec.rate),
    term_years: Number(spec.term_years),
    down_payment: toDec(spec.down_payment),
    // Python `AreaContext` defaults `pmi_annual_rate` to Decimal("0.0055")
    // when not supplied — golden inputs never override it.
    pmi_annual_rate: new Decimal("0.0055"),
  };
}

function buildSnapshot(spec: Record<string, unknown>): SnapshotForPhase {
  return {
    months_of_supply: toDec(spec.months_of_supply),
    s2l_4w: toDec(spec.s2l_4w),
    s2l_12w: toDec(spec.s2l_12w),
    pct_with_price_drops: toDec(spec.pct_with_price_drops),
    median_dom: Number(spec.median_dom),
    active_listings: Number(spec.active_listings),
    sample_size: Number(spec.sample_size),
    confidence_score: Number(spec.confidence_score),
  };
}

function buildHistory(spec: Record<string, unknown>): PhaseHistory {
  return {
    baseline_dom: Number(spec.baseline_dom),
    inv_yoy: toDec(spec.inv_yoy),
    previous_phase: (spec.previous_phase as MarketPhase | undefined) ?? "unknown",
  };
}

function buildWaitParams(spec: Record<string, unknown>): WaitParams {
  return {
    target_price: toDec(spec.target_price),
    wait_horizon_months: Number(spec.wait_horizon_months),
    current_rate: toDec(spec.current_rate),
    current_rent: toDec(spec.current_rent),
    area_ctx: buildArea(spec.area_ctx as Record<string, unknown>),
    // Python `WaitParams` defaults — golden inputs never override.
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
}

function buildMetric(spec: Record<string, unknown>): MetricValue {
  const raw = spec.value;
  let value: Decimal | number | null;
  if (raw === null || raw === undefined) {
    value = null;
  } else if (typeof raw === "number" && Number.isInteger(raw)) {
    // Python preserves int as int (no decimal scale); `int` round-trips
    // as a number without scale. We don't re-emit `value` in any of the
    // golden outputs, so this is only used for typing fidelity.
    value = raw;
  } else {
    value = new Decimal(String(raw));
  }
  return {
    value,
    sample_size: spec.sample_size === null || spec.sample_size === undefined
      ? null
      : Number(spec.sample_size),
    unit: String(spec.unit),
    metric_name: String(spec.metric_name),
  };
}

// ---------------------------------------------------------------------------
// Dispatcher
// ---------------------------------------------------------------------------

interface Row {
  function: string;
  input: Record<string, unknown>;
}

interface Output {
  function: string;
  output: unknown;
}

function runRow(row: Row): unknown {
  const fn = row.function;
  const input = row.input;
  if (fn === "affordability") {
    return affordability(
      buildBuyer(input.buyer as Record<string, unknown>),
      buildMarket(input.market_ctx as Record<string, unknown>),
    );
  }
  if (fn === "monthly_cost") {
    return monthlyCost(
      toDec(input.price),
      buildArea(input.area_ctx as Record<string, unknown>),
    );
  }
  if (fn === "compute_phase") {
    return computePhase(
      buildSnapshot(input.snapshot as Record<string, unknown>),
      buildHistory(input.history as Record<string, unknown>),
    );
  }
  if (fn === "cost_of_waiting") {
    return costOfWaiting(
      buildBuyer(input.buyer as Record<string, unknown>),
      String(input.area_id),
      buildWaitParams(input.params as Record<string, unknown>),
    );
  }
  if (fn === "confidence_score") {
    const d = input.disagreement;
    const disagreement = d === null || d === undefined ? null : new Decimal(String(d));
    return confidenceScore(
      buildMetric(input.metric as Record<string, unknown>),
      Number(input.age_days),
      disagreement,
    );
  }
  throw new Error(`Unknown function in row: ${fn}`);
}

const inputs: Row[] = JSON.parse(readFileSync(INPUTS_PATH, "utf8"));
const outputs: Output[] = JSON.parse(readFileSync(OUTPUTS_PATH, "utf8"));

describe("golden-file parity (Python ↔ TS)", () => {
  it("inputs and outputs file lengths match (100 rows each)", () => {
    expect(inputs.length).toBe(100);
    expect(outputs.length).toBe(100);
    expect(inputs.map((r) => r.function)).toEqual(outputs.map((r) => r.function));
  });

  for (let i = 0; i < inputs.length; i++) {
    const row = inputs[i]!;
    const expected = outputs[i]!;
    it(`row ${i} (${row.function}) matches Python output byte-for-byte`, () => {
      const actual = runRow(row);
      const actualJson = canonical(actual);
      const expectedJson = canonical(expected.output);
      expect(actualJson).toBe(expectedJson);
    });
  }
});
