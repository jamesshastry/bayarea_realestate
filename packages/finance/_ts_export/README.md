# `@bayre/finance`

Hand-ported TypeScript mirror of [`packages/finance/`](../) — the pure-function
trust layer for the Bay Area FTHB tool. Implements the five C3-contracted
finance functions (per [`docs/contracts.md`](../../../docs/contracts.md)) so
the Next.js client can compute affordability, market phase,
cost-of-waiting, and confidence client-side without an API round-trip.

## Public API

```ts
import {
  affordability,
  monthlyCost,
  computePhase,
  costOfWaiting,
  confidenceScore,
  Decimal,
} from "@bayre/finance";
```

| Function | Mirrors | Signature (TS) |
|----------|---------|----------------|
| `affordability` | `affordability.py::affordability` | `(buyer, marketCtx) -> AffordabilityResult` |
| `monthlyCost` | `affordability.py::monthly_cost` | `(price, areaCtx) -> MonthlyCost` |
| `computePhase` | `timing.py::compute_phase` | `(snapshot, history) -> PhaseResult` |
| `costOfWaiting` | `cost_of_waiting.py::cost_of_waiting` | `(buyer, areaId, params) -> WaitGrid` |
| `confidenceScore` | `confidence.py::confidence_score` | `(metric, ageDays, disagreement) -> ConfidenceResult` |

Internal TS helper names are camelCase (e.g. `monthlyCost`,
`computePhase`); **the JSON output keys still match Python's snake_case**
(`p_and_i`, `clock_position`, `max_by_loan_type`, …) — this is the C3
parity contract.

## Money is `Decimal`, never `number`

All money fields are wrapped in the in-tree `Decimal` class
([`src/decimal.ts`](src/decimal.ts)). This is a hand-rolled minimal
implementation of the IBM-Decimal arithmetic semantics Python's
`decimal.Decimal` uses, sufficient for byte-equal output parity with the
Python implementation. Default rounding mode is **`ROUND_HALF_EVEN`**
(banker's rounding).

Why a hand-rolled Decimal instead of `decimal.js` / `big.js`:
the off-the-shelf libraries don't preserve the Python-style
*(coefficient, exponent)* representation across arithmetic, so e.g.
`Decimal("1.0").toString()` collapses to `"1"` — which would silently
break golden-file parity. Keeping the implementation in-tree (~250 LOC)
also keeps `@bayre/finance` zero-runtime-dep so it can ship in any
browser bundle.

## Parity enforcement

[`test/golden.test.ts`](test/golden.test.ts) loads the *Python-produced*
`inputs.json` + `outputs.json` from
[`packages/finance/tests/golden/`](../tests/golden/), runs each row
through the TS implementation, and asserts byte-equal JSON output.

```bash
pnpm --filter @bayre/finance test
```

CI (`.github/workflows/ci.yml`) runs the same command. **Any drift
between Python and TS — even a single cent in a quantize — fails the
build.** When the Python finance package changes in a way that
intentionally alters output, both sides must be updated and the golden
files re-baked in the same PR.

[`test/properties.test.ts`](test/properties.test.ts) runs `fast-check`
property tests mirroring the Python `Hypothesis` invariants:
monotonicity (affordability), conservation (monthly cost), idempotence
(compute phase), shape (cost-of-waiting grid). These guard the TS
implementation against bugs that happen to coincide with the golden
fixture inputs.

## Build

```bash
pnpm --filter @bayre/finance build      # tsup → dist/
pnpm --filter @bayre/finance typecheck  # tsc --noEmit
```

The package emits ESM only (`"type": "module"`, `"main": "dist/index.js"`).
Node ≥ 20.11.

## Out of scope

- No I/O, no `fetch`, no `Date.now()`. Every `as_of_date` the user
  cares about is a payload field, never read from a clock.
- No imports from other workspace packages. The package is meant to be
  importable from a browser bundle; one of its values is the absence of
  surprise transitive deps.
