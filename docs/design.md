# Design

> Status: Draft v1 · Owner: project lead · Last updated: 2026-05-10
> Read `requirements.md` for the **what** and `datamodel.md` for the **nouns**. This document covers the **how**: architecture, components, data flow, deployment, and the patterns that make the requirements feasible.

---

## 1. Architectural philosophy

The product splits cleanly into three layers, each with very different change cadence:

| Layer | Cadence | Failure mode if rushed |
|-------|---------|------------------------|
| **Data ingestion** | Sources change quarterly; parsers break monthly | Bad data silently shown as fact |
| **Computation** | Calculations stable; tax / loan rules update yearly | Wrong financial output → user trust gone |
| **Presentation** | UX iterates weekly | Confusion, but recoverable |

The architecture below isolates these so a Redfin schema change doesn't ship a wrong mortgage payment, and a UI redesign doesn't break the snapshot pipeline.

### Top-level diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                         External sources                            │
│   Redfin CSVs · CDE · GreatSchools · Assessors · FRED · Mapbox      │
└──────┬──────────────┬───────────────┬────────────────┬──────────────┘
       │              │               │                │
       ▼              ▼               ▼                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                  Adapter layer  (one file per source)                │
│   redfin_csv.py   greatschools.py   alameda_assessor.py   ...        │
│              │ Capability { MEDIAN_PRICE, SCHOOL_ZONE, … }           │
└──────┬───────┴──────────────────────────────────────────────────────┘
       │ raw payloads → S3/R2 (Bronze, immutable)
       ▼
┌─────────────────────────────────────────────────────────────────────┐
│                   Normalize → Silver (Parquet)                       │
│              typed, deduped, schema-versioned                        │
└──────┬───────────────────────────────────────────────────────────────┘
       ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    ETL (Dagster)                                     │
│   • Resolver (multi-source conflict resolution)                      │
│   • SnapshotComputer (writes MarketSnapshot rows)                    │
│   • ZoneAttributor (parcel ↔ attendance zone backfill)               │
└──────┬───────────────────────────────────────────────────────────────┘
       ▼
┌─────────────────────────────────────────────────────────────────────┐
│        Postgres 16 + PostGIS + pgcrypto + pg_partman    (Gold)       │
│   geographic_area · school · parcel · listing · sale (mat. view)     │
│   market_snapshot · buyer · scenario · alert · source_fetch          │
└──────┬───────────────────────────────────────────────────────────────┘
       ▼
┌─────────────────────────────────────────────────────────────────────┐
│   API   FastAPI + Pydantic v2 + SQLAlchemy 2.0 + GeoAlchemy2         │
│   Routes: /areas, /schools, /finance, /scenarios, /map/tiles         │
│   `packages/finance/` is pure functions — 95% coverage gate          │
└──────┬───────────────────────────────────────────────────────────────┘
       ▼
┌─────────────────────────────────────────────────────────────────────┐
│   Web   Next.js 15 (App Router) · RSC for SEO · Mapbox GL JS         │
│   Anonymous-first; localStorage for affordability inputs             │
│   `packages/finance` ported to TS for client-side recompute          │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 2. Module boundaries (monorepo layout)

```
bayarea-realestate/
├── apps/
│   ├── web/                      Next.js frontend (TypeScript)
│   └── api/                      FastAPI backend (Python)
├── packages/
│   ├── domain/                   Pydantic models + auto-generated TS types
│   ├── adapters/                 One file per data source
│   │   ├── _base.py              DataSourceAdapter Protocol, Capability enum
│   │   ├── redfin_csv.py
│   │   ├── greatschools.py
│   │   ├── cde_schools.py
│   │   ├── alameda_assessor.py
│   │   ├── santa_clara_assessor.py
│   │   ├── fred_rates.py
│   │   ├── fema_flood.py
│   │   ├── calfire_fhsz.py
│   │   └── mapbox_isochrone.py
│   ├── etl/                      Dagster jobs and assets
│   │   ├── jobs/weekly_market.py
│   │   ├── jobs/monthly_assessor.py
│   │   ├── jobs/zone_attribution.py
│   │   └── resolvers/snapshot_resolver.py
│   ├── geometry/                 PostGIS helpers, isochrone caching
│   ├── finance/                  PURE FUNCTIONS — 95% coverage gate
│   │   ├── affordability.py
│   │   ├── tco.py
│   │   ├── rent_vs_buy.py
│   │   ├── confidence.py
│   │   ├── tax_rules.py          (Prop 13, SALT, county rates, jumbo limits)
│   │   └── _ts_export/           generated TS port (build step)
│   └── observability/            Structured logging, OTel setup
├── data/
│   ├── bronze/                   Sample fixtures only (S3 in prod)
│   ├── silver/                   Parquet fixtures
│   └── seeds/                    Boundary files, school IDs (committed)
├── infra/
│   ├── migrations/               Alembic
│   ├── terraform/                Eventual
│   └── github-actions/           Workflows
└── docs/                         (this directory)
```

### Why these boundaries

- **`packages/finance/` is the trust layer.** It must be importable without a database, network, or framework. Pure functions. This is what gets 95% coverage and what gets ported to TypeScript for the client. If any function in here needs I/O, the design is wrong.
- **`packages/adapters/` isolates fragility.** Every source-specific HTML quirk lives in one file. The rest of the system doesn't know whether a number came from Redfin or from Movoto.
- **`apps/api` and `apps/web` are thin.** Routes wire packages together; pages render. Real logic lives in packages so it's reusable, testable, and not framework-coupled.

---

## 3. Data layer — adapter pattern

The current `scrape.py` hardcodes "Redfin > Movoto > Zillow" priority in `build_city_record`. That doesn't scale to 10 sources × 50 metros × multiple capabilities. The replacement:

### 3.1 Adapter Protocol

```python
class Capability(str, Enum):
    MEDIAN_PRICE = "median_price"
    INVENTORY = "inventory"
    DOM = "dom"
    SALE_TO_LIST = "sale_to_list"
    PPSF = "ppsf"
    BY_PROPERTY_TYPE = "by_property_type"
    BY_BEDROOMS = "by_bedrooms"
    BY_SCHOOL_ZONE = "by_school_zone"
    SCHOOL_RATING = "school_rating"
    PARCEL_TAX = "parcel_tax"
    MELLO_ROOS = "mello_roos"
    RENT = "rent"
    MORTGAGE_RATE = "mortgage_rate"
    FLOOD_RISK = "flood_risk"
    WILDFIRE_RISK = "wildfire_risk"

class DataSourceAdapter(Protocol):
    name: str
    license: Literal["public_domain", "attribution", "commercial", "internal_only"]
    capabilities: set[Capability]

    def can_fetch(self, area: GeographicArea, capability: Capability) -> bool: ...
    def fetch(self, area: GeographicArea, period: Period) -> RawSnapshot: ...
    def reliability(self, capability: Capability) -> float: ...     # 0.0 - 1.0
```

### 3.2 Resolver

```python
class SnapshotResolver:
    """For each (area, capability), pick the best source by reliability,
    falling back gracefully and logging disagreements."""

    def resolve(
        self, area: GeographicArea, capabilities: set[Capability], period: Period
    ) -> ResolvedSnapshot:
        candidates = [a for a in self.adapters if a.can_fetch(area, c)]
        # ... rank by reliability(c), fetch top N, compare, log disagreements > threshold
```

### 3.3 Source disagreement thresholds (resolves an open follow-up from `requirements.md`)

| Capability | Disagreement threshold (relative) | Action |
|------------|-----------------------------------|--------|
| MEDIAN_PRICE | > 5% | Log + lower confidence_score by 15 |
| DOM | > 30% | Log + lower confidence_score by 20 |
| INVENTORY | > 10% | Log + lower confidence_score by 10 |
| SCHOOL_RATING | any (different methodologies) | Show both, no single "winner" |
| MORTGAGE_RATE | > 0.25 pp | Log; defer to FRED |
| FLOOD/WILDFIRE | any | Show authoritative source only (FEMA / Cal Fire) |

These live in `packages/finance/confidence.py` so they're tested.

### 3.4 Source priority for FTHB use case

| Source | Used for | Freshness tier (per requirements NF-DAT-06) | License |
|--------|----------|---------------------------------------------|---------|
| **Redfin Data Center CSVs** | weekly market stats, SFH/condo/townhome split, ZIP-level | Weekly (Thu 1pm ET → ours by Thu 7pm ET, 4-week rolling windows) | Attribution |
| **CDE (CA Dept. of Education)** | school metadata, district boundaries, official scores | Annual / on-publication | Public domain |
| **GreatSchools** | school ratings | Quarterly | Commercial (paid tier required if monetized) |
| **County assessors (Alameda, SCC)** | parcel data, tax base year, special assessments, Mello-Roos | Monthly / on-publication; per-county format | Public domain |
| **Census TIGER** | all administrative boundaries | Annual | Public domain |
| **FEMA NFHL** | flood zones | On-update (rare) | Public domain |
| **Cal Fire FHSZ** | wildfire severity zones | On-update (rare); affects insurance | Public domain |
| **FRED (St. Louis Fed)** | mortgage rates, conforming limits, macro series | Daily (mortgage), annual (limits) | Public domain |
| **Mapbox (Directions / Isochrone)** | commute analysis | On-demand; cached | Commercial; free tier OK for MVP |
| **MLS via Bridge / SimplyRETS / Repliers (RESO Web API + EntityEvent)** | live listings, price changes, status flips, sub-minute push | **Realtime (sub-minute via webhooks)** — Phase 6 only | Per-MLS IDX rules; $300–1500/mo per MLS |

**Realtime-tier note (Phase 6):** RESO's [EntityEvent resource](https://www.reso.org/blog/entityevent-resource/) (RCP-028) is the modern standard — append-only event log with monotonic sequence numbers + webhook push. The Phase 2 architecture (event-driven snapshot pipeline, signal table, subscription table) is designed so a Phase-6 MLS adapter slots in by emitting `MarketSignal` rows with the same shape as our internal signals — no rewrite of alert evaluation, dispatch, or UI.

---

## 4. ETL — Dagster

Dagster (over Prefect / cron) for three reasons: asset-based mental model fits "MarketSnapshot is an asset materialized from sources," lineage UI is invaluable when debugging "why is Fremont's number wrong," and asset-level retries handle source-specific flakiness.

### 4.1 Asset graph

```
[external sources]                  [seed boundaries]
       │                                    │
       ▼                                    ▼
raw_redfin_weekly         ────►   geographic_areas
raw_greatschools                       │
raw_assessor_alameda                   ▼
raw_assessor_scc          ────►   normalized_parcels
raw_fred_rates                         │
raw_fema_flood                         ▼
raw_calfire_fhsz          ────►   normalized_listings
       │                               │
       ▼                               ▼
   silver_*  ────────►   resolved_snapshots  ────►  market_snapshot (Postgres)
                                │
                                ▼
                       confidence_scored_snapshots
```

### 4.2 Schedules

| Job | Cadence | Freshness tier | Notes |
|-----|---------|----------------|-------|
| `weekly_market` | Thursday 18:00 UTC (1pm ET +5h buffer; Redfin publishes 1pm ET) | Weekly | Redfin CSV → snapshots; meets NF-DAT-06 weekly SLA (≤ 6h) |
| `daily_rates` | Weekdays 22:00 UTC (close +1h) | Near-realtime / daily | FRED 30Y, conforming limits change detection |
| `intraday_rates` | Hourly during market hours | Near-realtime | Detect rate moves > 0.05pp → emit `rate_threshold` signal |
| `monthly_assessor` | 1st of month, 02:00 UTC | Monthly | County data is slow-moving |
| `quarterly_schools` | Jan/Apr/Jul/Oct | Quarterly | School ratings refresh |
| `annual_boundaries` | Jul 15 | Annual | TIGER + CDE district refresh |
| `zone_attribution_backfill` | On-demand after boundary changes | Event-driven | Recomputes parcel ↔ zone mapping |
| `signal_detector` | Triggered on every snapshot write | Event-driven | Writes to `market_signal` (see §4.4) |
| `alert_matcher` | Subscribes to `market_signal` insert | Event-driven | Honors dedupe + snooze |
| `email_digest` | Hourly (immediate), 8:00 user-local (daily), Mon 8:00 (weekly) | Per user pref | Aggregates dispatched alerts |

### 4.3 Failure isolation

Per requirement NF-REL-02: if Redfin fetch fails for one city, other cities still process. If GreatSchools is down, schools-related snapshots are stale-tagged but the rest of the dashboard works. Dagster's per-asset retry + sensor-based alerting handles this naturally.

### 4.4 Event-driven snapshot pipeline (per NF-DAT-07)

Polling-based alert evaluation is forbidden. Instead, every snapshot recompute emits one or more `MarketSignal` events to a queue; alert evaluation subscribes.

```
ETL job writes market_snapshot row
  └─► trigger(snapshot_id) — Postgres LISTEN/NOTIFY (MVP) or Redis Streams (Phase 4+)
       └─► SignalDetector
            ├─ phase_transition?  (Market Phase changed vs. last snapshot)
            ├─ mos_threshold?     (months_of_supply crossed 3.0)
            ├─ s2l_threshold?     (sale_to_list crossed 1.0)
            ├─ dom_threshold?     (median_dom changed by > 5d)
            └─ rate_threshold?    (FRED 30Y crossed 0.05pp move)
       └─► writes to market_signal table
            └─► AlertMatcher subscribes
                 └─► finds AlertSubscription rows matching (area, signal_kind, threshold)
                      └─► honors dedupe window + snooze
                           └─► AlertDispatcher
                                ├─ in_app  → WebSocket / SSE push to active session
                                ├─ web_push → service worker
                                └─ email   → Resend / Postmark (immediate, daily, weekly digest)
                                     └─► writes alert_dispatch row (open + click tracked)
```

**Why this shape:**

- **One signal table** = one cohesive append-only audit log of "what changed" — drives both the user's "What changed" feed (F-RT-05) and the alert pipeline.
- **Phase 6 MLS slot-in:** when the MLS adapter is added, it writes the *same* `market_signal` shape (kind: `new_listing`, `price_drop`, `status_flip`). Alert matching, dispatch, and UI need no changes.
- **Dedupe + snooze are evaluator concerns**, not subscription concerns — keeps subscription config simple.
- **Latency budget** (per NF-PRF-05): signal generated → alert dispatched ≤ 5 min P95 (in-app/push), ≤ 15 min P95 (immediate email). Achievable with LISTEN/NOTIFY at MVP scale; move to Redis Streams when subscriber count exceeds ~10K.

---

## 5. Computation layer — `packages/finance/`

This is the most-tested code in the project. Conventions:

- **Pure functions only.** Inputs are dataclasses; outputs are dataclasses. No I/O, no clock, no random. Pass `as_of_date` as a parameter, never read `today()`.
- **Decimals, not floats**, for money. Python `Decimal` with `ROUND_HALF_EVEN`.
- **Explicit assumptions object.** Every function takes an `Assumptions` parameter (rate, term, appreciation, etc.) — never reads from globals. This is what makes scenarios comparable.
- **TypeScript port is generated.** A build step runs against the Pydantic models + a small Python-to-TS transpiler for the function bodies, or (more pragmatically) we hand-port the small set of functions and pin them with golden-file tests so the two implementations can't drift.

### 5.1 Function inventory (cross-references `datamodel.md` §9)

| Function | Inputs | Output | Notes |
|----------|--------|--------|-------|
| `affordability(buyer, market_ctx)` | Buyer financials + jumbo limits + rate | `{comfortable, stretch, max_by_loan_type}` | DTI math is well-defined; loan-type limits from `tax_rules.py` |
| `monthly_cost(price, area_ctx)` | Price + area tax rate + mello/HOA est | `{p_and_i, tax, mello, hoa, insurance, pmi, total}` | Insurance has wildfire surcharge by FHSZ class |
| `tco(price, area_ctx, horizon, scenario)` | + horizon | `{total, equivalent_monthly, equity_built, tax_shield_used}` | SALT cap applied per-year, not in aggregate |
| `rent_vs_buy(price, rent, scenario)` | + rent + appreciation scenario | `{breakeven_years, wealth_diff_5y, ...}` | Three appreciation curves (low/base/high) |
| `school_premium(school_id, period)` | + comparison area_id | `{premium_pct, premium_dollars, sample_size, baseline_area}` | Returns null if sample size < threshold |
| `area_fit_score(scenario, area, snapshot)` | Scenario weights + area facts | `{score: 0-100, breakdown}` | Weighted multi-criteria; never a black box |
| `confidence_score(sample_size, age_days, disagreement)` | per-metric thresholds | `{score: 0-100, reasons}` | Resolves NF-DAT-01–05 |

### 5.2 Per-metric confidence thresholds (resolves the open follow-up from datamodel review)

| Metric | Min sample for high confidence | Acceptable for medium | Below = low |
|--------|-------------------------------|------------------------|--------------|
| `median_sale_price` | ≥ 30 sales | 10–29 | < 10 |
| `median_ppsf` | ≥ 30 | 10–29 | < 10 |
| `median_dom` | ≥ 20 | 8–19 | < 8 |
| `sale_to_list_ratio` | ≥ 30 | 10–29 | < 10 |
| `months_of_supply` | ≥ 5 active listings | 2–4 | < 2 |
| `pct_with_price_drops` | ≥ 50 listings observed | 20–49 | < 20 |
| `school_premium` | ≥ 20 sales in zone AND ≥ 20 in baseline | half | below half |

Below-threshold metrics MUST be hidden or visually de-emphasized per NF-DAT-03.

### 5.3 Pillar F (market timing) — full specification

Wait-And-See (P6) is a priority cohort and timing is operating principle #10. Specifically:

- A standalone `/timing` page per metro and per area, not just a card on the area page.
- **Market Phase classification** (per F-TIM-02), modeled on [Realtor.com's Market Clock](https://www.realtor.com/research/market-clock-report-2026q1) but computed at city + school-zone granularity (not metro-only).
- **Cost-of-Waiting calculator** (per F-TIM-03) that integrates with the user's affordability inputs.
- **Fragmentation visualization** (per F-TIM-06) showing all areas in a metro on one clock face.
- Macro overlay layer: Fed funds rate, 30Y mortgage rate, big tech layoff events, NVDA earnings dates. All optional toggles.
- Honest framing per principle #4: "Indicators, not predictions."

#### 5.3.1 Market Phase computation

Each `MarketSnapshot` row, after insert, is scored by `packages/finance/timing.py::compute_phase`:

```
Inputs (from snapshot + 4-week and 12-week trend):
  mos              months_of_supply
  s2l_4w, s2l_12w  sale_to_list_ratio (4-wk and 12-wk medians)
  pdrop            pct_with_price_drops
  dom_trend        median_dom Δ vs. 12-wk baseline
  inv_yoy          active_listings YoY change

Composite scores (each 0-100, normalized):
  buyer_pressure  = w1*(s2l - 1) + w2*max(0, 3 - mos) + w3*max(0, -dom_trend)
  seller_pressure = w4*pdrop + w5*max(0, mos - 3) + w6*max(0, dom_trend) + w7*max(0, inv_yoy)

Phase determined by the (buyer_pressure, seller_pressure) coordinate:
  Peak (12 o'clock):     buyer_pressure high, seller_pressure low, trending flat
  Cooling (3 o'clock):   seller_pressure rising, buyer_pressure falling
  Trough (6 o'clock):    seller_pressure high, buyer_pressure low
  Recovery (9 o'clock):  buyer_pressure rising, seller_pressure falling

Output:
  {
    phase: "peak" | "cooling" | "trough" | "recovery",
    clock_position: 0-12 (continuous),
    buyer_pressure: 0-100,
    seller_pressure: 0-100,
    components: { mos, s2l, pdrop, dom_trend, inv_yoy },
    confidence: low | medium | high (inherits snapshot confidence)
  }
```

Weights `w1..w7` are tuned against historical data and pinned in `tax_rules.py`'s sibling `phase_weights.py`. The formula MUST be visible to users on click (operating principle #1 — show the math).

#### 5.3.2 Phase transition signal

When `compute_phase(current).phase != compute_phase(previous).phase`, emit a `MarketSignal` row of kind `phase_transition` with the from/to phases and triggering components. This drives the alert pipeline (§4.4) and the "What changed" feed (F-RT-05).

#### 5.3.3 Cost-of-Waiting calculator

`packages/finance/cost_of_waiting.py::compute`:

```
Inputs:
  buyer (from affordability)
  area_id
  target_price (default: median for area)
  wait_horizon_months: 3 | 6 | 12 | 24
  appreciation_scenario: { low: -2%, base: +3%, high: +6% } annual
  rate_scenario: { drop_50bp, flat, rise_50bp }
  current_rent

Output (for each (appreciation × rate) combo):
  appreciation_change_dollars
  rent_paid_during_wait
  monthly_payment_now    (at current rate)
  monthly_payment_later  (at rate scenario)
  cumulative_savings_or_cost
  break_even_rate_drop   (the rate drop required to make waiting net-zero)
  net_dollar_impact      (positive = waiting cost you money)
```

Output is descriptive, never prescriptive. UI presents 9 scenarios in a grid; user reads what scenarios make waiting favorable vs. acting now.

---

## 6. API layer — FastAPI

### 6.1 Surface

```
GET  /v1/areas/search?q=fremont&kind=city&metro=bay-area
GET  /v1/areas/{id}
GET  /v1/areas/{id}/snapshot?period=2026-04&type=sfh
GET  /v1/areas/{id}/timeseries?metric=median_price&type=sfh&from=2020-01
GET  /v1/areas/{id}/schools
GET  /v1/areas/{id}/timing                # current Market Phase + components
POST /v1/areas/{id}/timing/cost-of-waiting { buyer, target_price?, horizon_months }
GET  /v1/areas/{id}/feed?since=...        # "what changed" feed (last N signals)
GET  /v1/metros/{id}/timing/fragmentation # all areas plotted on clock face

GET  /v1/schools/{id}
GET  /v1/schools/{id}/zone-snapshot

POST /v1/finance/affordability             { income, down, debt, ... }
POST /v1/finance/monthly-cost              { price, area_id, scenario }
POST /v1/finance/tco                       { price, area_id, scenario, horizon }
POST /v1/finance/rent-vs-buy               { ... }

POST /v1/scenarios                         (auth)
GET  /v1/scenarios/{id}                    (auth)
PUT  /v1/scenarios/{id}                    (auth)
DELETE /v1/scenarios/{id}                  (auth)

POST /v1/alerts/subscriptions              (auth) — create subscription
GET  /v1/alerts/subscriptions              (auth) — list user's subscriptions
PUT  /v1/alerts/subscriptions/{id}         (auth) — update threshold/snooze
DELETE /v1/alerts/subscriptions/{id}       (auth)
GET  /v1/alerts/dispatches?since=...       (auth) — alert history for user
GET  /v1/alerts/preferences                (auth) — channels, digest cadence
PUT  /v1/alerts/preferences                (auth)
GET  /v1/alerts/stream                     (auth, SSE) — live in-app push

GET  /v1/map/tiles/areas.mvt/{z}/{x}/{y}?metric=median_price&type=sfh
GET  /v1/map/tiles/timing.mvt/{z}/{x}/{y} # phase choropleth

GET  /v1/sources                           # data attribution page
GET  /v1/status                            # public status page (per NF-DAT-08)
GET  /v1/status/sources/{name}             # per-source ingest health detail
GET  /v1/health                            # liveness probe
```

### 6.2 Conventions

- **Versioned path** (`/v1/`). New version introduced when responses break compatibility, not on every change.
- **OpenAPI generated.** Frontend types come from `openapi-typescript` so API ↔ web is type-checked end-to-end.
- **Cursor pagination** on every list endpoint, never offset-based.
- **Cache-Control headers** by route: snapshots `max-age=3600`, timeseries `max-age=86400`, finance POSTs `no-store` (vary by user input).
- **No PII in URLs.** Scenario IDs are UUIDs but never sequential.

### 6.3 Auth

- NextAuth.js on the web side, JWT validated by FastAPI middleware.
- Magic link primary; OAuth (Google) secondary. No password storage.
- Session cookie HTTP-only, SameSite=Lax, Secure.

---

## 7. Frontend — Next.js 15 (App Router)

### 7.1 Page architecture

```
app/
├── (marketing)/                  Static marketing pages
├── [metro]/                      Bay Area, Sacramento, etc.
│   ├── page.tsx                  Metro overview
│   ├── cities/[city]/page.tsx    City overview
│   ├── cities/[city]/neighborhoods/[hood]/page.tsx
│   ├── schools/[school]/page.tsx
│   ├── zips/[zip]/page.tsx
│   ├── timing/page.tsx           Pillar F (P6 priority)
│   ├── compare/page.tsx          2–4 areas side-by-side
│   └── map/page.tsx              Interactive choropleth
├── education/                    SEO-driven explainers
│   ├── mello-roos/page.tsx
│   ├── prop-13/page.tsx
│   └── ...
├── account/                      Auth-gated
│   ├── scenarios/page.tsx
│   ├── alerts/page.tsx
│   └── settings/page.tsx
└── api/                          Edge functions (rare; mostly proxy to FastAPI)
```

### 7.2 Rendering strategy

| Page type | Strategy | Why |
|-----------|----------|-----|
| Area pages | RSC + ISR (revalidate every snapshot refresh) | SEO + fast |
| Education hub | Static (build-time) | SEO; rarely changes |
| Affordability widget | Client component (after first server fetch of context) | Live recompute |
| Map | Client component (Mapbox GL JS) | Interactive |
| Account / Scenarios | Server actions + client mutations | Auth required |

### 7.3 State management

Deliberately minimal:

- **URL is state** for area selection, comparisons, filters. Bookmarkable.
- **localStorage** for affordability inputs (anonymous mode).
- **Server state** for scenarios, alerts (TanStack Query).
- **No Redux / global stores.** If a piece of state isn't in URL, localStorage, or server, it's a code smell.

### 7.4 Why not stay static

Current `generate_dashboard.py` ships a single self-contained HTML. Migration triggers:

- Personalized affordability needs per-user state → at minimum localStorage, server-side when authed
- 100+ areas × multiple periods makes inline JSON too large
- Map drill-in requires vector tiles or geo queries
- Auth, alerts, comparisons need a backend

The current MVP (`scrape.py` + `generate_dashboard.py` + `dashboard/index.html`) is treated as a **throwaway prototype** — see §10.7.6. There is no migration: Phase 2 is greenfield Next.js with no URL preservation requirement. The MVP serves as data-ingest reference and visual-aesthetic inspiration only.

---

## 8. Map architecture

A non-trivial part of the product — school-zone choropleth is the killer Family Forming feature.

### 8.1 Tile strategy

- **Vector tiles** (Mapbox MVT) generated by `tippecanoe` from the GeographicArea polygons.
- **Pre-baked at ETL time**, not on-demand.
- **Stored in R2 / S3** with a long Cache-Control TTL.
- **Refreshed when boundaries or snapshots change**, with a content-hashed URL so CDN invalidation isn't needed.

### 8.2 Styling

The choropleth metric is the user's choice (price, $/sqft, DOM, school rating). Color binning uses **quantiles within the visible viewport**, not absolute thresholds — otherwise a Bay Area-tuned scale is useless in Sacramento.

### 8.3 Interaction

- Click a school zone → drill to school page
- Hover → tooltip with snapshot summary
- Affordability filter (when set) overlays the green/yellow/red badge per area

---

## 9. Deployment topology

### 9.1 Recommended (Vercel + Railway + Neon, solo-friendly)

| Component | Choice | Rationale |
|-----------|--------|-----------|
| Web | **Vercel** (Next.js App Router) | Purpose-built for Next.js by the Next.js team. RSC, ISR (`revalidateTag`), Server Actions, edge functions all work out of the box. |
| API | **Next.js Route Handlers** on Vercel Functions | Eliminates a separate FastAPI service in the request path; one runtime, one deploy. TS port of `packages/finance/` becomes the *primary* implementation; Python is reference + ETL. |
| Scheduled jobs | **Vercel Cron Jobs** | Runs the daily FRED rate sync, weekly Redfin pull trigger, hourly intraday-rate check — no second service needed for thin schedules. Heavy ETL stays on Railway. |
| Python finance package | **Local dev + ETL only** | Python is no longer in the request path post-Phase 2; remains for ETL workers and as the golden-file source-of-truth |
| Database | **Neon Postgres + PostGIS** (us-west-2) | Branchable, scale-to-zero; matches user's region. Use **pooled** connection (`-pooler` host) for runtime, **direct** for migrations. Vercel + Neon is a documented quickstart pattern. |
| Realtime push | **Server-Sent Events** via Vercel Edge Functions | Edge runtime supports streaming; sufficient for one-way alert push without a WebSocket service |
| Pub/sub for signals | **Postgres LISTEN/NOTIFY** (MVP) → **Upstash Redis** (Phase 4+) | Avoid new infra at MVP; Upstash has an HTTP API that works from Vercel Functions without persistent connections |
| ETL worker | **Self-hosted Dagster on Railway** ($5/mo) | Vercel is *not* a fit for long-running pipelines (Dagster scheduler, multi-minute jobs, retries). Keep ETL deliberately separate; it writes to Neon, the web app reads from Neon. |
| Object storage | **Cloudflare R2** | No egress fees; map tiles + Bronze raw payloads |
| Maps | **Mapbox** | Free tier covers MVP |
| Email | **Resend** | Transactional + digest; Next.js-friendly SDK |
| Web push | **VAPID standard** via `web-push` npm | Browser-native; no vendor lock |
| Monitoring | **Sentry** (errors) + **Axiom** (logs) | Generous free tiers; Vercel-friendly |

#### 9.1.1 Architecture rationale

Three things drove this topology:

1. **Single runtime simplifies ops.** Next.js Route Handlers on Vercel Functions means there's no second service in the request path. The auto-generated OpenAPI client → frontend type chain disappears (types are shared in one TS codebase).
2. **Python's role narrows but doesn't disappear.** Python remains the language for ETL (Dagster's strength) and for `packages/finance/` *reference implementation + golden-file source-of-truth*. The TypeScript port becomes the **primary** runtime implementation. Decision D2 (TS port strategy) is now load-bearing.
3. **Two deploy targets, not three.** Vercel for web+API, Railway for ETL. Neon, R2, Upstash, Mapbox, Resend, Sentry, Axiom are all platform-as-a-service add-ons with no servers to manage.

#### 9.1.2 Connection string conventions (Neon-specific)

```
DATABASE_URL          # pooled  → host contains "-pooler"  → use in Vercel Functions / app code
DATABASE_URL_DIRECT   # direct  → no "-pooler" segment     → use in Alembic migrations only
```

Why split: serverless functions create new connections per invocation; only the pooled endpoint can absorb the burst. But Alembic / `pg_partman` / `CREATE TYPE` ENUMs require a direct connection — pgBouncer's transaction-mode pooling breaks them. Both env vars are present in `.env.example`.

#### 9.1.3 Region choice

Neon project is in **us-west-2 (Oregon)**. To minimize round-trip latency:
- Vercel Functions: pin to `pdx1` (Portland) or `sfo1` (San Francisco) regions in `vercel.json`.
- Railway ETL worker: deploy to a US-West region.
- R2 buckets: pick `WNAM` (West North America).

A 200ms cross-region round trip on every Postgres query is enough to blow `NF-PRF-01` (page load ≤ 2s); region pinning is cheap insurance.

### 9.2 Cost guardrails (per requirement NF-COST-01)

Phase 0–2 budget ≤ $50/mo:
- Vercel Hobby: $0 (100GB bandwidth, 100k function invocations, 1 cron at daily cadence)
- Neon Free → Launch: $0–19 (free covers MVP; Launch when you need branches/storage)
- Railway ETL worker: $5
- R2: ~$0 at MVP volumes
- Sentry / Axiom / Upstash Redis: $0 (free tiers)
- Mapbox: $0 (free tier)
- Resend: $0 (3k emails/mo free)

Phase 3+ likely adds Mapbox usage charges (still typically < $25/mo) and Vercel Pro ($20) once function invocations or cron cadence exceed Hobby tier.

### 9.3 Environments

- `local` — Docker Compose with Postgres + Postgres + minio (S3 stand-in)
- `preview` — per-PR via Vercel previews + Neon branch
- `production` — main branch auto-deploy

No "staging" environment. Preview branches per PR are good enough at this scale.

---

## 10. Cross-cutting concerns

### 10.1 Observability (per NF-OBS-01–03)

- **Logs:** structured JSON, OpenTelemetry traces, exported to Axiom.
- **Metrics:** RED method (rate, errors, duration) per route + per ETL asset.
- **Events:** every page render emits `{page_type, area_id, latency, freshness}` for the data quality dashboard.
- **Source disagreement aggregation:** weekly digest emailed to project lead summarizing per-source per-metric drift.

### 10.2 Caching strategy

| Layer | What | TTL |
|-------|------|-----|
| Browser | HTML / images | per route headers |
| CDN (Vercel) | RSC payloads | 1h with `revalidateTag` invalidation |
| API in-memory (LRU) | snapshot lookups | 5 min |
| Postgres | (none beyond default) | — |
| R2 | map tiles | content-hashed; effectively forever |

### 10.3 Security (per NF-SEC-01–05)

- **Column-level encryption** on `buyer.*_enc` fields via pgcrypto + per-row key derived from a KMS-managed master key.
- **No third-party analytics on financial-input pages** (NF-SEC-05). Use first-party Plausible elsewhere.
- **CSP** strict; only Mapbox + Sentry in script-src.
- **Rate limit** on POST /finance/* endpoints to prevent abuse (50/min/IP).
- **Account deletion job** runs daily; purges soft-deleted buyers older than 30 days.

### 10.4 Compliance (per NF-CMP-01–04)

- "Not financial advice" disclaimers rendered as a shared `<Disclaimer />` component injected at the top of `/affordability`, `/tco`, `/rent-vs-buy`, and inside the `<Scenario>` viewer.
- Fair Housing review: any new filter or ranking goes through a review checklist (no demographic proxies, no "neighborhood quality" rankings).
- License field on every `DataSource` row; render attribution on `/sources` page.
- A `data-license` attribute on every chart/widget for audit.

### 10.5 Accessibility (per NF-A11Y-01–03)

- WCAG 2.1 AA target.
- Every chart has a `role="img"` + `aria-label` summary AND a "show data table" toggle.
- Affordability badges: color + text + icon (✓ / ⚠ / ✗), never color alone.

### 10.6 Error budget & on-call

- 99.5% monthly availability budget = 3.6h. Allocated:
  - 1h to planned migrations
  - 1.5h to dependency outages (Vercel/Neon/Mapbox SLOs)
  - 1h to our own bugs
- Anything more triggers a postmortem. (Practical: at MVP scale this is aspirational; document the budget so the discipline is in place when traffic grows.)

### 10.7 Design system

The product has unusual UI demands: dense financial tables, interactive Market Clock face, choropleth maps, scenario comparison matrices, alert feeds, "show the math" expandable cells. Off-the-shelf component libraries built for SaaS dashboards leave half the UI custom anyway. Two requirements drove the choice:

1. **Code ownership.** Every cell may need a custom interaction (hover-to-expand math, tooltip with source attribution, freshness badge). A library that hides component internals (Material UI, Ant Design) creates fight-the-framework friction at scale.
2. **Dark-mode-first parity.** The current dashboard already uses a dark "Wall Street terminal" palette and that's the right vibe for a financial decision tool. Light mode is secondary, not equal.

#### 10.7.1 The stack

| Layer | Choice | Why |
|-------|--------|-----|
| **Component primitives** | **shadcn/ui** (built on Radix UI + Tailwind CSS) | Copy-paste components — they live *in your repo*, not in `node_modules`. Full ownership; trivially restyled. Radix gives WCAG-compliant headless primitives (combobox, popover, dialog) for free. |
| **Utility CSS** | **Tailwind CSS v4** | Native CSS layer support; pairs naturally with shadcn; design tokens in CSS custom properties (matches the current dashboard's `:root` variable approach). |
| **Icons** | **lucide-react** | shadcn's default; single tree-shakable package; matches the visual weight of the existing dashboard's monochrome aesthetic. |
| **Charts (most surfaces)** | **Tremor** (built on Recharts) + custom Visx for advanced viz | Tremor ships financial-tuned chart presets (sparkline, area, bar, scatter) with sensible defaults; Visx (Airbnb) for the Market Clock face and fragmentation viz where Tremor can't reach. |
| **Maps** | **Mapbox GL JS** + **react-map-gl** | Vector tiles, fast choropleths, well-supported. (No leaflet — vector tile rendering matters for school-zone choropleth at multiple zoom levels.) |
| **Forms** | **react-hook-form** + **zod** | Affordability/scenario forms have many fields with cross-field validation. RHF's uncontrolled inputs avoid re-render storms; zod validates and infers TS types. |
| **Tables** | **TanStack Table v8** | Headless table primitives; pairs with shadcn `<Table>` styles. Comparison view + signal feed + dispatch history all need sortable/filterable tables. |
| **Toast / notifications** | **sonner** | shadcn-recommended; minimal, accessible. |
| **Data fetching** | **TanStack Query** (server-state) + native `fetch` for RSC | Cache + refetch + SSE subscription for in-app alerts. |
| **Date/time** | **date-fns** + **date-fns-tz** | Tree-shakable; user-local digest scheduling needs proper TZ handling. |

#### 10.7.2 Why not the obvious alternatives

| Option | Why considered | Why rejected |
|--------|----------------|--------------|
| **Material UI (MUI)** | Familiar, comprehensive | Visual identity reads "enterprise dashboard"; opinionated theming makes the dark "terminal" aesthetic harder; bundle size penalty |
| **Mantine** | Batteries included, beautiful defaults | Component internals less hackable than shadcn; their theming engine duplicates Tailwind |
| **Ant Design** | Most complete component set | Dated visual language; bundle size; Chinese-business aesthetic ill-suited to consumer FTHB product |
| **Chakra UI** | Accessibility-first | Maintenance status uncertain post-v3; Tailwind+shadcn has eclipsed it |
| **Tailwind UI (paid)** | High-quality patterns | Useful as reference; not necessary when shadcn covers primitives |
| **Recharts alone** | Simpler | Hits a wall on Market Clock face, fragmentation viz; need Visx for that |

#### 10.7.3 Theming approach

CSS custom properties define **semantic** tokens, not raw colors. This matches the current dashboard's pattern (`--bg`, `--surface`, `--tx`, `--green`, `--amber`) and makes dark/light pairs trivial:

```css
@layer base {
  :root {
    /* Surfaces */
    --bg: oklch(15% 0 0);            /* page bg */
    --surface: oklch(19% 0 0);       /* card bg */
    --border: oklch(28% 0 0);

    /* Text */
    --tx: oklch(90% 0.02 80);        /* high emphasis */
    --tx-muted: oklch(60% 0.02 80);

    /* Semantic — money & confidence */
    --positive: oklch(75% 0.18 145); /* green: gains, comfortable */
    --negative: oklch(70% 0.21 25);  /* red: losses, unaffordable */
    --warning: oklch(82% 0.16 75);   /* amber: stretch, low confidence */
    --info: oklch(70% 0.15 230);     /* blue: neutral context */

    /* Market Phase (per F-TIM-02) — distinct from money colors */
    --phase-peak: oklch(70% 0.21 25);
    --phase-cooling: oklch(82% 0.16 75);
    --phase-trough: oklch(75% 0.18 145);
    --phase-recovery: oklch(70% 0.15 230);

    /* Freshness tier (per NF-DAT-06) */
    --tier-realtime: oklch(75% 0.18 145);
    --tier-near-realtime: oklch(70% 0.15 200);
    --tier-daily: oklch(75% 0.10 250);
    --tier-stale: oklch(60% 0.10 30);
  }

  [data-theme="light"] {
    --bg: oklch(98% 0 0);
    --surface: oklch(100% 0 0);
    --border: oklch(90% 0 0);
    --tx: oklch(20% 0.02 80);
    --tx-muted: oklch(50% 0.02 80);
    /* semantic colors stay perceptually similar via OKLCH */
  }
}
```

OKLCH (vs. HSL or hex) gives perceptually-uniform color shifts — important when generating accessible color pairs for dark/light without hand-tuning each shade.

#### 10.7.4 Component inventory (Phase 2 baseline)

These map 1:1 to recurring patterns in the requirements; they're the "Lego set" that all pages are built from:

| Component | Primitive source | Used in |
|-----------|------------------|---------|
| `<MetricCell value, source, asOf, confidence />` | shadcn Tooltip + custom | Every number, everywhere — operating principle #1 |
| `<FreshnessBadge tier, asOf />` | shadcn Badge | Every metric (NF-DAT-01) |
| `<AffordabilityBadge level />` | shadcn Badge + icon | City cards, comparison table |
| `<MarketPhaseBadge phase, clockPosition />` | Custom + shadcn Tooltip | Area pages, fragmentation viz |
| `<MarketClockFace areas[] />` | Visx custom | Fragmentation page (F-TIM-06) |
| `<ChoroplethMap metric, areas />` | Mapbox GL + react-map-gl | `/map` (F-GEO-06) |
| `<ScenarioComparisonGrid scenarios[] />` | TanStack Table + shadcn Table | `/account/scenarios/compare` |
| `<CostOfWaitingMatrix scenarios />` | Custom grid | Timing page (F-TIM-03) |
| `<WhatChangedFeed signals[] />` | shadcn Card + Tremor sparkline | Saved-area page (F-RT-05) |
| `<DisclaimerNote />` | shadcn Alert | Affordability, TCO, rent-vs-buy (NF-CMP-01) |
| `<SourceAttribution sources[] />` | shadcn Popover | Footer + on-demand on every metric |
| `<TimeseriesChart metric, area, overlays />` | Tremor LineChart + Visx annotations | Area pages, timing page |
| `<EducationTooltip term />` | shadcn HoverCard linking to MDX | Inline glossary (F-EDU-02, F-EDU-04) |
| `<DataNotice variant />` | shadcn Alert + icon | Every error/missing/stale/disagree/low-conf state (F-DATA-01–03) |
| `<Chart kind, data />` | Adapter wrapping Tremor + Visx | All charts. Consumers never import `recharts` or `@visx/*` directly. |
| `<Tappable size />` | Wrapper enforcing NF-A11Y-04 sizes | Every interactive element on touch viewports |
| `<CommandPalette />` | shadcn `<Command>` (cmdk) | Global Cmd+K (F-NAV-02) |
| `<Breadcrumb path />` | shadcn Breadcrumb | Every sub-metro page (F-NAV-03) |
| `<CompareDrawer />` | shadcn Sheet, sticky bottom | F-CMP-05 |
| `<TierBadge tier />` | shadcn Badge with paid-tier "★" | F-MON-01 |

##### 10.7.4.1 Component discipline (UX-review-derived rules)

Two enforcement rules prevent the predictable drift that comes with shadcn's copy-paste model and the Tremor + Visx mix:

1. **Single chart entry point.** All chart usage MUST go through the `<Chart>` adapter. Direct imports from `recharts` or `@visx/*` in `apps/web` are blocked by an ESLint `no-restricted-imports` rule. The adapter routes simple cases to Tremor (sparkline, area, bar, scatter) and complex cases to Visx (Market Clock face, fragmentation viz, brushable timeseries with macro overlays).

2. **`components/ui/` is the only home for shadcn primitives.** Per-feature overrides require an explicit `/* shadcn-override: <reason> */` magic comment plus code-review signoff. A CI check (`scripts/check-shadcn-overrides.sh`) lists overrides on every PR; reviewers must justify each.

These two rules — together with the chart-as-table fallback (§10.7.5) and the OKLCH semantic token system (§10.7.3) — are the difference between a design system that ages well and one that fragments by month six.

#### 10.7.5 Accessibility implications

shadcn's Radix base satisfies most of NF-A11Y-01–03 out of the box:

- All interactive primitives are keyboard-navigable and ARIA-correct (Radix's reason for existing).
- Focus management in modals/popovers is automatic.
- Color contrast in OKLCH tokens above is hand-verified ≥ 4.5:1 (AA) for body text.
- For NF-A11Y-02 (chart text alternatives): every Tremor/Visx chart wrapped in `<figure>` with a `<figcaption>` summary + a "View as table" toggle that swaps the SVG for a TanStack Table rendering the underlying data. This pattern is mandatory, not optional, in the chart wrapper component.
- For NF-A11Y-03 (color not sole encoding): every semantic badge (affordability, phase, freshness) carries an icon AND text label. Enforced by the component API — `<MarketPhaseBadge>` cannot render without a label prop.

#### 10.7.6 Visual continuity from MVP — *not a migration*

**Decision (2026-05-11):** the current static dashboard (`dashboard/index.html`) is treated as a **throwaway prototype**, not as a migration target. There is no `/legacy` route, no URL preservation, no visual-language carry-over requirement. Phase 2 is greenfield Next.js.

What we *do* keep from the prototype:

- Its OKLCH-equivalent CSS variable structure (the `:root` block with `--bg`, `--surface`, `--tx`, `--green`, `--amber`) inspired the §10.7.3 token scheme above. The aesthetic intent ("Wall Street terminal," dark-first, monospaced) is preserved.
- The 7 seed cities (`scrape.py::CITIES`) are the Phase 0 / Phase 2 ingest target — see `docs/seed-data.md`.

What we discard:

- The HTML template. New product is a Next.js App Router build.
- The `MANUAL_CONDO_NOTES` hack. Phase 2 either has real data or shows "no data yet."
- The static-data-inlined-in-HTML pattern. Phase 2 is API-driven with ISR caching.

This avoids a migration tax that would have constrained Phase 2 to match Phase 0/1 URL shapes and visual decisions made under MVP pressure.

---

## 11. How requirements map to architecture

| Requirement | Where it's satisfied |
|-------------|----------------------|
| F-AFF-* (affordability) | `packages/finance/affordability.py` + `/v1/finance/*` + client component in `apps/web` |
| F-TCO-*, F-RVB-* | `packages/finance/{tco,rent_vs_buy}.py` + same |
| F-GEO-* (geographic + schools) | `geographic_area` polymorphic table + `attendance_zone` versioning + `market_snapshot` filtered by `area_id` + map tiles |
| F-CMP-* (comparison) | `/compare` page; data from same snapshot endpoints |
| F-TIM-01–02, F-TIM-04–07 (timing core) | `packages/finance/timing.py::compute_phase` + `/v1/areas/{id}/timing` + `/timing` pages |
| F-TIM-03 (cost of waiting) | `packages/finance/cost_of_waiting.py` + `POST /v1/areas/{id}/timing/cost-of-waiting` |
| F-TIM-06 (fragmentation viz) | `GET /v1/metros/{id}/timing/fragmentation` + clock-face React component |
| F-TIM-08 (timing-fit score) | `packages/finance/timing.py::fit_score` (scenario × area phase) |
| F-RT-01–11 (realtime updates) | Event-driven ETL §4.4 + `market_signal` + `alert_subscription` + `alert_dispatch` tables + SSE channel + status page |
| F-RSK-* (risk) | `packages/adapters/{fema,calfire,...}.py` + risk overlay component |
| F-EDU-* (education) | Static MDX in `apps/web/app/education/` |
| F-SCN-* (scenarios + alerts) | `scenario` + `alert_subscription` tables + auth + `/account/scenarios` + alert preferences |
| F-MM-* (multi-metro) | `metro_id` denormalization + URL namespacing |
| F-NAV-* (nav, search, breadcrumb) | App Router layout + shadcn `<Command>` (cmdk) + breadcrumb component |
| F-DATA-* (data presentation states) | `<DataNotice>` component + source-disagree popover + rate-fallback affordance |
| F-MON-01 + NF-UX-01 (cognitive load + tier signaling) | `<TierBadge>` + default-collapse rule enforced by `<MetricsSection>` wrapper |
| NF-A11Y-04 (tap target sizes) | `<Tappable>` wrapper enforced by ESLint rule on all interactive elements |
| NF-DAT-01–05 (data quality) | `confidence_score` column + freshness label component + source disagreement resolver |
| NF-DAT-06 (per-tier SLA) | Schedule table §4.2 + status page §10.6 + tier label injected by snapshot resolver |
| NF-DAT-07 (event-driven mandate) | §4.4 pipeline; alert evaluation subscribes to `market_signal` insert |
| NF-DAT-08 (status page) | `/v1/status` endpoint + `apps/web/app/status` |
| NF-PRF-* (performance) | Pre-computed snapshots + RSC + ISR + LRU + map tile caching |
| NF-PRF-05 (alert latency) | LISTEN/NOTIFY MVP, Redis Streams Phase 4+; SSE for in-app delivery |
| NF-REL-* (reliability) | Dagster per-asset retries + per-source isolation + 95% coverage gate on `packages/finance/` |
| NF-SEC-*, NF-CMP-* | Column encryption + CSP + disclaimers + license tracking |
| NF-OBS-04–05 (SLA + alert funnel) | OTel spans on signal → match → dispatch → open + status page |
| NF-COST-* | Vercel Hobby + Neon free tier + R2 + Mapbox free tier |

---

## 12. Architectural decision records (ADR pointers)

The following decisions are load-bearing and should each get a short ADR in `docs/adr/` when implemented:

1. ADR-001: PostGIS over Mongo / DuckDB-only — durable spatial joins, mature ecosystem.
2. ADR-002: Polymorphic `GeographicArea` over per-kind tables — single snapshot pipeline.
3. ADR-003: Pre-computed `MarketSnapshot` over query-time aggregation — read scaling.
4. ADR-004: Adapter pattern over hardcoded source priority — pluggability.
5. ADR-005: Bronze / Silver / Gold tiers — re-derivability.
6. ADR-006: Dagster over Prefect / Airflow — asset model fits domain.
7. ADR-007: Next.js RSC + ISR over fully-static — needed for personalization + scale.
8. ADR-008: Column-level encryption via pgcrypto — minimal viable for financial PII.

---

## 13. Persona review log

- **Engineer (future contributor):** Confirms `packages/finance/` boundary makes the trust layer testable in isolation. Asks: how does the TS port stay in sync? Decision: golden-file tests on both sides assert byte-equal outputs for a fixed input matrix; CI fails on drift.
- **SRE / on-call:** Confirms NF-REL-02 isolation strategy. Flags: column encryption complicates DR — backup key escrow process needs a runbook before Phase 4 ships. Added as open follow-up.
- **Security:** Confirms CSP + no-tracking on financial pages. Asks for explicit threat model doc; deferred to Phase 4 alongside auth implementation.
- **Future contributor onboarding:** Confirms monorepo layout is conventional. Adds: README with first-day setup script (`make dev`).
- **Wait-And-See user (P6):** Validates the elevated `/timing` page. Asks for downloadable raw data so they can build their own model — added as a P2 nice-to-have (CSV export per area).

Open follow-ups from this review:
- Backup key escrow runbook (Phase 4 blocker).
- Threat model doc (Phase 4 blocker).
- CSV export per area (Phase 3 nice-to-have).
- TS port: pick "transpile" vs. "hand-port + golden-file" decisively before Phase 1.
