# Implementation Plan

> Status: Living · Owner: project lead · Last updated: 2026-05-12
> Read `requirements.md` (the "what"), `design.md` (the "how"), and `datamodel.md` (the "nouns") first. This document is the **sequencing**: phase-by-phase deliverables, exit criteria, dependencies, decisions, and risks.

---

## Live status (snapshot 2026-05-12)

| Phase | State | Notes |
|---|---|---|
| **0 — Data ingest validation** | ✅ **Complete** | Source pivoted weekly → monthly (Redfin retired the public weekly file 2026-05-12). Monthly cron (`0 18 8 * *`) green; auto-loads to Neon via `make load-latest` step. First snapshot: `data/2026-05-12.json` covering 2026-03 for 7 seed cities. |
| **1 — Affordability + timing pure functions** | ✅ **Complete** | `packages/finance/` 100% line coverage; TS port (`@bayre/finance`) byte-equal to Python via golden-file CI. Glossary MDX shipped. Phase weights are placeholder defaults (calibration is a Phase 3 task). |
| **2 — Backend foundation + event-driven pipeline** | 🟡 **Scaffold only** | Apps/api FastAPI scaffold + Alembic migrations + Neon schema all live. **Direct DB read path live via Vercel Server Components + `postgres.js`** — Railway/FastAPI deployment deferred (not required for read-side workloads). Dagster/event-driven signal pipeline not yet built. Adapter framework Protocol exists; only Redfin adapter implements it. |
| **3 — Schools + comparison + per-zone timing** | ⏳ **Page-route stubs** | `/[metro]/schools` and `/[metro]/schools/[slug]` routes exist; render "ingest pending" until CDE + GreatSchools adapters land. Comparison page + map view + fragmentation viz still TODO. |
| **4 — Auth, scenarios, realtime alerts** | ⏳ **Not started** | Blocked on Phase 2 event-driven signal pipeline + Phase 4 prerequisites (key-escrow runbook, threat model). |
| **5 — Risk overlays + second metro** | ⏳ **Not started** | — |
| **6 (gated) — MLS realtime via RESO** | ⏳ **Not started** | Decision gate at Phase 5 close. |

**Architecture decision made 2026-05-12:** Railway deployment deferred indefinitely. The Phase 2/3 read-side runs entirely on Vercel Server Components (Next.js → `postgres.js` → Neon, ~1s cold). Railway becomes load-bearing only when one of these arrives: (a) Dagster orchestrated ETL replacing GH Actions cron, (b) the Phase 4 always-on alert dispatcher, or (c) a public typed REST API for non-web consumers (Phase 6 MLS receiver). Until then, the `apps/api` FastAPI scaffold lives in the repo as the OpenAPI source of truth but doesn't deploy.

**Live URLs (as of 2026-05-12):**

- App: https://bayarea-realestate-web.vercel.app/bay-area
- Repo: https://github.com/jamesshastry/bayarea_realestate
- DB: Neon `bayre` project (us-west-2)
- Cron: `.github/workflows/monthly-ingest.yml` — next run 2026-06-08 18:00 UTC

**What surfaces work end-to-end in production:**

- `/bay-area` — metro overview, 7 city cards with live median prices
- `/bay-area/cities/{slug}` — full snapshot grid + monthly-cost teaser using `@bayre/finance`
- `/bay-area/timing` — per-city Market Phase classification (gracefully shows "Accumulating" until ≥3 months of history)
- `/bay-area/schools` — index page with "ingest pending" notice + decision-needs list
- `/status` — static page generated from `data/sources.json`

---

## How to read this plan

Each phase lists:

- **Goal** — one sentence; what success looks like at the end.
- **Deliverables** — concrete artifacts (code, schemas, jobs, pages).
- **Requirements satisfied** — links back to F-* / NF-* IDs from `requirements.md`.
- **Dependencies** — what must be true to start this phase.
- **Exit criteria** — testable. If you can't tick the box, the phase isn't done.
- **Decisions to make first** — things to settle before writing code.
- **Risks** — what could derail this phase.
- **Effort** — rough sizing for a solo / small team. **Note:** these are wall-clock weeks of focused work. With agent parallelism (3–5 agents), real elapsed time can be 30–50% lower for parallelizable work.

Phases are designed to ship usable improvements at each gate — never "spend 8 weeks on infra then ship nothing."

---

## Cross-cutting principles (apply at every phase)

1. **Show the math** in every UI surface (operating principle #1).
2. **Pure functions in `packages/finance/`** — no I/O, ≥ 95% line coverage gate enforced from Phase 1 onward.
3. **Bronze immutability** — never edit raw payloads; re-derive Silver/Gold from code.
4. **Event-driven from Phase 2 onward** — every snapshot recompute writes a `MarketSignal`. Polling-based alert evaluation is forbidden (NF-DAT-07).
5. **One PR = one feature flag**. Behind-flag rollout from Phase 4 onward when auth exists.
6. **Tests before merge.** Adapter tests with recorded fixtures (vcrpy / responses); finance tests with golden files; ETL with synthetic data; web with Playwright smoke per page.

---

# Phase 0 — Data ingest validation + seed (1–2 weeks)

**Goal:** Build and validate the data-ingest path against the 7 seed cities (`docs/seed-data.md`) so Phase 2 starts with proven adapters and a known-good JSON schema. The current static dashboard is *not* extended — it remains a throwaway prototype (decision 2026-05-11).

**Deliverables:**

- New `packages/adapters/redfin_csv.py` adapter: downloads weekly CSV from Redfin Data Center for Bay Area cities (the 7 seed cities at minimum) + ZIPs + property-type, normalizes to internal schema. Bronze-tier raw payloads cached to `data/bronze/redfin/{week}/`.
- Pydantic v2 schema for the JSON snapshot file (matches `datamodel.md` §10 spec). Includes `data_quality` block (`{sources, as_of, confidence, freshness_tier}`) per NF-DAT-01.
- Per-snapshot freshness-tier classification (NF-DAT-06) — the adapter writes its source's tier into every record.
- GitHub Actions workflow: weekly cron (Thu 18:00 UTC, after Redfin's 1pm ET publish) → run adapter → write `data/YYYY-MM-DD.json` → push to repo. **No dashboard regeneration** (the static dashboard is not extended; the JSON is the artifact).
- Seed-data spec finalized (`docs/seed-data.md`) — 7 cities + 3 priority high schools + 5 districts. **No school data ingested yet** — that's Phase 3 — but the spec exists so Phase 2 ingest jobs can use it as their target list.
- Public status page stub (single HTML, served from GitHub Pages): per-source last-fetch time + green/red indicator. This is a throwaway too, replaced by `/v1/status` in Phase 2.
- `pyproject.toml` (uv-managed) committed; `make ingest` / `make status` targets.

**Requirements satisfied:** NF-DAT-01–06 (partial), NF-DAT-08 (stub), NF-OBS-02

**Dependencies:** none.

**Exit criteria:**

- [x] Adapter produces a valid `data/YYYY-MM-DD.json` for all 7 seed cities, ~~weekly~~ **monthly**, with no human intervention. *(2026-05-12: Redfin retired the public weekly file; see runbook. Cron `0 18 8 * *` validated end-to-end.)*
- [x] Every metric in that JSON carries `as_of`, `source`, `freshness_tier`, and `confidence`.
- [x] Schema validates with `pydantic.TypeAdapter` against the spec in `datamodel.md` §10. *(CI gate; `SCHEMA_VERSION` bumped 1 → 2 with the cadence change.)*
- [x] Status page (static HTML) shows green for the Redfin adapter after a successful run. *(GH Pages enable still pending — file is generated and committed; just not served as a public URL until you flip the Pages source.)*
- [x] `seed-data.md` reviewed and pinned (CDS codes, slugs, polygon source URLs all confirmed). *(Redfin region-name strings flipped to ✓ in the runbook after the first real ingest.)*

**Decisions made:**

- ✓ Redfin Data Center license: personal/non-commercial use confirmed by user 2026-05-11 (see `docs/runbooks/redfin-csv-source.md`).
- ✓ Package manager: `uv` (D1).
- 🔁 Source cadence: weekly → monthly (2026-05-12 — forced by Redfin retiring the public weekly file).

**Risks (status):**

- ✓ Redfin CSV format change — mitigated and tested. *(2026-05-12 the upstream URL + schema both changed; the adapter's structured filter + Bronze cache made the migration mechanical.)*
- ⏳ GitHub Actions cron drift — first scheduled run is 2026-06-08; alerting on missed runs is a Phase 2/4 follow-up.

**Effort (actual):** ~2 sessions including the source pivot.

---

# Phase 1 — Affordability + basic timing (2–3 weeks)

**Goal:** Validate the FTHB-framing AND timing-decision-framing as **pure-function packages with thorough tests**, ready for Phase 2 to consume. No user-facing UI in this phase — the prototype dashboard is *not* extended (decision 2026-05-11).

**Deliverables:**

- New `packages/finance/affordability.py` (Python). Pure functions. Front-end DTI 28% / back-end DTI 36% / max-by-loan-type math. Unit-tested ≥ 95% line coverage.
- New `packages/finance/timing.py::compute_phase` — Market Phase classification per snapshot. Pure function; output shape matches `datamodel.md` §6a column spec.
- New `packages/finance/cost_of_waiting.py` — 9-scenario grid (3 appreciation × 3 rate).
- New `packages/finance/tax_rules.py` — pinned constants for 2026 conforming / high-balance / jumbo limits per Bay Area county; SALT cap; Prop 13 base + 2% cap.
- Hand-ported TS mirror in `packages/finance/_ts_export/` with golden-file tests asserting byte-equal output for a fixed input matrix. CI fails on drift.
- Property-based tests (Hypothesis on the Python side; fast-check on the TS side) for the obvious invariants: monotonicity (more income → ≥ same affordability), conservation (sum of monthly_cost components = total), idempotence (compute_phase is deterministic given inputs).
- Static MDX glossary entries for: DTI, jumbo, PMI, Mello-Roos, Prop 13, conforming limit, SALT, Prop 13 base year. (`docs/glossary/` — used as source-of-truth for in-app `<EducationTooltip>` content in Phase 2.)

**Requirements satisfied:** F-AFF-01–02, F-AFF-04, F-AFF-08, F-TIM-02 (formula), F-TIM-03 (formula), operating principle #1.

**Dependencies:** Phase 0 schema valid (so Python finance code can consume Phase 0 JSON for golden-file inputs).

**Exit criteria:**

- [x] All `packages/finance/` modules ≥ 95% line coverage. *(Actually 100% on every module.)*
- [x] Python ↔ TS golden-file tests pass for a 100-row input matrix. *(101 cases; CI gate.)*
- [x] Property-based tests pass (Hypothesis + fast-check).
- [x] `tax_rules.py` includes 2026 county-specific conforming/jumbo limits with citation. *(`TODO(verify)` markers on the projected Nov 2025 FHFA values until you confirm against the press release.)*
- [x] Glossary MDX exists for all 8 priority terms.

**Decisions made:**

- ✓ TS port strategy: hand-port + golden-file (D2).
- ⏳ Default mortgage rate source: FRED MORTGAGE30US — adapter not yet built. Phase 1 finance teaser uses a hardcoded 6.5% (`apps/web/src/lib/finance.ts::DEFAULTS.rateAnnual`). **Wire FRED before launching the per-buyer affordability calculator.**
- ✓ 2026 conforming/jumbo limits live in `packages/finance/tax_rules.py` (D-flagged for annual refresh).

**Risks (status):**

- ⏳ FTHB framing — not yet validated against real users (Phase 4 deliverable).
- ⏳ Market Phase formula — defaults shipped; calibration deferred to Phase 3.

**Effort (actual):** Single session via 3 parallel agents (Python, TS port, glossary). Cleared the gate end-to-end.

---

# Phase 2 — Backend foundation + event-driven pipeline (4–6 weeks)

**Goal:** Lock in the architecture that everything later depends on. Same user-facing features as Phase 1, but powered by the new backend so Phase 3+ can be additive.

**Deliverables:**

- Postgres 16 + PostGIS + pgcrypto + (eventually) pg_partman provisioned (Neon).
- Alembic migrations for all entities in `datamodel.md`: `geographic_area`, `school_district`, `school`, `attendance_zone`, `parcel`, `listing`, `sale`, `market_snapshot` (with phase columns), `market_signal`, `data_source`, `source_fetch`.
- Boundary ingest: Census TIGER (counties, cities, ZCTAs) + CDE (school districts) for entire Bay Area. **The 18 priority `GeographicArea` rows from `docs/seed-data.md` §6 must exist and pass the §9 acceptance queries.**
- All Bay Area cities (~100) onboarded — not just the original 7.
- Adapter framework (`packages/adapters/_base.py` Protocol + `Capability` enum + `SnapshotResolver`).
- Refactor Redfin CSV adapter to the new framework.
- New adapter: FRED daily mortgage rate (`packages/adapters/fred_rates.py`).
- Dagster (or Prefect) ETL with schedules from `design.md` §4.2.
- Event-driven pipeline (per `design.md` §4.4): snapshot insert → Postgres LISTEN/NOTIFY → SignalDetector → `market_signal` row.
- FastAPI backend (`apps/api`): area + snapshot + timeseries + finance endpoints.
- Pydantic v2 domain models in `packages/domain/`; OpenAPI spec generated.
- Next.js scaffold (`apps/web`): Bay Area area pages backed by API. Greenfield — no migration from the current static dashboard (decision 2026-05-11). The current `scrape.py` / `generate_dashboard.py` / `dashboard/index.html` remain in the repo as reference only and are not deployed.
- **System-wide UI primitives (UX-review-derived):** ship the entire `components/ui/` baseline before building features on top. Includes `<DataNotice>`, `<Chart>` adapter, `<Tappable>`, `<CommandPalette>`, `<Breadcrumb>`, `<MetricCell>`, `<FreshnessBadge>`, `<DisclaimerNote>`, `<EducationTooltip>`. ESLint `no-restricted-imports` rule blocking direct `recharts`/`@visx` imports + `scripts/check-shadcn-overrides.sh` CI check land in the same PR.
- **Top-nav structure** (F-NAV-01): `Areas | Timing | Compare | Map | Saved | Learn`. Implemented as `apps/web/app/(metro)/[metro]/layout.tsx`.
- **Affordability prefill** (F-AFF-10): default Bay Area FTHB profile + "this is an example" banner.
- **Lighthouse CI** (NF-PRF-08): perf budget enforcement on every PR.
- `/v1/status` endpoint + `/status` page.
- Per-tier freshness SLA tracking (NF-DAT-06): instrument every fetch with publish-time vs. our-time metadata.

**Requirements satisfied:** F-MM-01–02, NF-DAT-01–08, NF-DAT-07 (event-driven mandate), NF-PRF-04, NF-REL-02, NF-OBS-01–04.

**Dependencies:** Phase 1 finance package working in pure-Python form.

**Exit criteria:**

- [~] All Phase-1 features render via the new API ~~the new API~~ **directly via Server Components** (same numbers, same math). *(Architecture pivot 2026-05-12: Vercel SSR queries Neon directly via `postgres.js`. The "API" path moves into Server Component lib functions in `apps/web/src/lib/`. FastAPI scaffold preserved as the OpenAPI source of truth.)*
- [~] All ~100 Bay Area cities have ~~weekly~~ **monthly** snapshots ≤ 6h after Redfin publishes (NF-DAT-06). *(7 priority cities live; remaining ~93 deferred to a later expansion of `SEED_CITIES` — same adapter, same workflow.)*
- [x] All 18 priority `GeographicArea` rows from `docs/seed-data.md` exist and the §9 acceptance queries return expected counts. *(Migration `0002` + `make verify-seed`.)*
- [ ] Inserting a snapshot row triggers SignalDetector → `market_signal` row within 10 seconds. *(SignalDetector not built — deferred until alerts (Phase 4) become a real product driver.)*
- [x] `<DataNotice>`, `<Chart>` adapter, `<Tappable>`, `<CommandPalette>`, `<Breadcrumb>` all exist in `components/ui/`. *(Stub form; full implementation per `docs/design.md` §10.7.4 happens as features need them.)*
- [x] ESLint blocks `recharts` / `@visx/*` imports outside the `<Chart>` adapter; `scripts/check-shadcn-overrides.sh` exists.
- [ ] Lighthouse CI green on every page in the cold-cache scenario; P75 page load ≤ 2s (NF-PRF-01). *(Lighthouse CI not yet wired; manual cold-cache hits are ~1.2s on /bay-area.)*
- [~] `/status` page renders per-source health. *(Static `status/index.html` from sources.json; the "prior 30 days" view is Phase 2 backend follow-up.)*
- [x] `apps/web` deployed on Vercel. ~~`apps/api` deployed on Railway~~ — **deferred per 2026-05-12 architecture decision** (see Live status banner above).
- [x] Cost ≤ $50/mo (NF-COST-01). *(Vercel hobby + Neon free tier + GitHub Actions free minutes; current run rate $0.)*

**Decisions made:**

- ✓ Hosting: Vercel + Neon (D3). Railway deferred indefinitely — see top-of-doc banner.
- ✓ Pub/sub at MVP: N/A — no event pipeline built yet (no signals, no alerts). Postgres LISTEN/NOTIFY remains the design when it lands.
- 🔁 Dagster: deferred — GH Actions cron + `make load-latest` covers monthly cadence; revisit when signal pipeline lands.
- ✓ ORM: SQLAlchemy 2.0 async + GeoAlchemy2 (used in apps/api models, even though apps/api isn't deployed).

**Risks (status):**

- ⏳ Boundary data ingest — not yet attempted; punted with `geometry NULL` in `geographic_area` (migration 0001 has a comment to tighten with a follow-up migration).
- ✓ Migration from static-site — N/A; Phase 2 was greenfield.
- ⏳ Per-tier SLA tracking — Protocol exists; SLA tracker not yet wired.

**Effort (actual so far):** ~1 session for the scaffold; ETL → DB → UI wiring took another session. The full ~100-city expansion + boundary ingest + signal pipeline + Lighthouse gates remain.

---

# Phase 3 — School drill-down + comparison + Market Phase per zone (4–6 weeks)

**Goal:** Ship the killer feature for Family Forming (P3) and the fragmentation viz for Wait-And-See (P6).

**Deliverables:**

- School data ingest:
  - CDE annual data (school metadata, district boundaries, official scores).
  - GreatSchools adapter (with explicit license note — non-commercial tier OK pre-monetization).
- `school` and `attendance_zone` tables populated for Bay Area.
- **3 priority high schools (per `docs/seed-data.md`) digitized first:** Foothill HS Pleasanton (CDS `01751010130096`), Fremont HS Sunnyvale (CDS `43694684332474`), Dublin HS Dublin (CDS `01750930132704`). Each with current-effective `AttendanceZone` polygon, district link, and CDE-sourced metadata.
- New runbook `docs/runbooks/digitize-attendance-zone.md` — QGIS / Mapbox Studio steps for converting district PDFs/maps to GeoJSON. The 3 priority zones are its first test cases; remaining Bay Area zones digitized using the same runbook.
- Parcel-to-zone backfill job (spatial join; runs after boundary changes).
- Compute snapshots scoped to each `school_zone` `GeographicArea` — uses the same MarketSnapshot pipeline (validates polymorphism).
- School premium computation (`packages/finance/school_premium.py`); requires baseline area construction (e.g., Fremont-minus-MSJ-zone polygons via PostGIS difference).
- School pages (`/bay-area/schools/{slug}`) with: ratings (multi-source side-by-side per F-GEO-08), zone-scoped market data, school premium, feeder chain. The 3 priority schools' pages are the Phase 3 demo.
- Comparison page (`/bay-area/compare?areas=a,b,c,d`) — 2–4 areas side-by-side per F-CMP-01–04.
- Map view (`/bay-area/map`): vector-tile choropleth (`tippecanoe` build at ETL time → R2). Toggle metric: median price, $/sqft, DOM, school rating, **Market Phase** clock position.
- **Market Phase computed per city AND per school zone** — not just metro.
- **Fragmentation visualization** (F-TIM-06): all areas in metro plotted on one clock face. New page `/bay-area/timing/fragmentation`. The 3 priority schools and 7 cities are the headline data points.
- Market Clock face React component (reusable: per-area `/timing` page also uses it).
- CSV export per area (F-TIM-09).

**Requirements satisfied:** F-GEO-01–08, F-CMP-01–04, F-TIM-02 (full), F-TIM-06, F-TIM-08–09.

**Dependencies:** Phase 2 backend live; school data licenses confirmed.

**Exit criteria:**

- [ ] Every Bay Area attendance zone has a snapshot and a Market Phase classification (or marked `unknown` if sample < threshold).
- [ ] **The 3 priority schools' pages render with full data** (ratings, zone snapshot, school premium, feeder chain).
- [ ] User can pick 4 areas and see comparison matrix.
- [ ] Map drill-in ≤ 1.5s P75 (NF-PRF-03).
- [ ] Fragmentation viz shows ≥ 50 areas plotted on clock.
- [ ] Fair Housing review checklist passed before launch.

**Decisions to make first:**

- GreatSchools commercial-tier subscription? Defer until monetization (free tier OK for non-commercial); document in `data_source.license`.
- School zone source: official district publications (PDFs/GIS layers per district) vs. GreatSchools-provided. **Recommendation:** official, with GreatSchools as fallback. Plan ingest as per-district scripts.
- Demographic data on area pages — Census ACS is informative but legally sensitive. **Recommendation:** ship without it in Phase 3; revisit with legal counsel before adding.

**Risks:**

- Attendance-zone GIS data is inconsistent across districts (some publish KML, some PDFs, some none). Schedule contingency for manual digitization.
- Fair Housing review may surface UI changes (renaming "school quality," removing rankings). Build in a review-cycle buffer.
- Parcel-to-zone backfill can be expensive (~1M parcels × spatial join). Profile early.

**Effort:** 4–6 weeks. Parallelizable: one agent on school ingest, one on comparison + map, one on fragmentation viz + clock component, one on parcel-zone backfill.

---

# Phase 4 — Auth, scenarios, realtime alert engine (4–6 weeks)

**Goal:** Deliver the realtime differentiator and the engagement loop. Users return because the product tells them when something changed.

**Deliverables:**

- Auth: NextAuth.js magic-link primary; Google OAuth secondary. JWT to FastAPI middleware.
- `buyer`, `scenario`, `saved_area`, `alert_subscription`, `alert_dispatch`, `alert_preference` tables (per `datamodel.md` §8). Column-level pgcrypto encryption on financial fields.
- `packages/finance/tco.py` + `packages/finance/rent_vs_buy.py` (full implementation per `design.md` §5.1).
- Scenario CRUD pages (`/account/scenarios`).
- Alert subscription UI (per F-RT-06–09): pick area, signal kind, threshold, channels, dedupe + snooze.
- Alert pipeline:
  - SignalDetector emits `market_signal` rows (already built in Phase 2).
  - AlertMatcher subscribes via LISTEN/NOTIFY → finds matching `alert_subscription` rows.
  - AlertDispatcher writes `alert_dispatch` row + sends via channel (in-app SSE / web push VAPID / email Resend).
  - Email digest scheduler (immediate / daily / weekly).
- "What changed" feed (`/[metro]/areas/[area]/feed`) per F-RT-05.
- SSE channel `/v1/alerts/stream` for in-app live push.
- Web push registration (VAPID) per browser.
- CCPA: data export + account deletion (NF-SEC-03).
- Threat model doc (Phase 4 blocker per design persona-review).
- Backup key escrow runbook (Phase 4 blocker per design persona-review).
- **Sessions UI** (F-SCN-07): list active devices/IPs with revoke-individual + revoke-all.
- **Digest content templates** (F-RT-14): "3 things to know this week" structure for both immediate and weekly digest emails. Push notification copy library committed.
- **PWA manifest + service worker** (F-RT-15): install-to-home-screen; offline cache of last-viewed area pages.
- **Alert default bundle** (F-RT-12): "watch for material market changes" curated bundle as the one-click default; per-signal customization behind a "Custom thresholds" disclosure.
- **Alert inline actions** (F-RT-13): every dispatched alert renders "Mute 7d / Mute 30d / Edit thresholds" inline.
- **Save-from-Cost-of-Waiting** (F-TIM-10): button writes to localStorage anonymously and prompts auth on second visit.

**Requirements satisfied:** F-TCO-01–06, F-RVB-01–05, F-SCN-01–09, F-RT-01–15, F-TIM-10, NF-SEC-01–06, NF-PRF-05–06, NF-OBS-05.

**Dependencies:** Phase 2 event pipeline live; Phase 3 area pages stable.

**Exit criteria:**

- [ ] Authed user can save a scenario and receive an in-app alert within 5 min P95 of signal generation (NF-PRF-05).
- [ ] Email digest delivered at user's chosen cadence in user's timezone.
- [ ] Account deletion purges all PII within 30 days (NF-SEC-03).
- [ ] No third-party trackers on financial-input pages (NF-SEC-05) — verify with curl + DOM inspection.
- [ ] Alert dispatch funnel queryable per channel (NF-OBS-05).
- [ ] PWA installable from desktop + mobile Chrome/Safari; offline cache renders last-viewed area page after airplane-mode toggle.
- [ ] Sessions page lists active devices and supports revoke-all.
- [ ] Weekly digest test sends produce "3 things to know" output, not metric dumps.
- [ ] Threat model + backup key escrow runbook reviewed and merged.

**Decisions to make first:**

- Pricing model: free vs. freemium. **Recommendation:** core (affordability, market data, schools, timing) stays free; alerts + multiple scenarios + CSV export gate a $5/mo tier. Decide before launching alerts.
- Email service: Resend vs. Postmark. Either works; Resend has slightly better free tier.
- Web push: ship in Phase 4 or defer? Browser support is universal now; ship.

**Risks:**

- Alert latency under load — mitigation: load-test SignalDetector → dispatch path with synthetic signals at 10x expected volume.
- Email deliverability — set up SPF/DKIM/DMARC properly from day one; warm up sending domain.
- pgcrypto key management — easy to lose access to encrypted columns if key escrow isn't set up. **Block Phase 4 ship on key escrow runbook.**
- Realtime expectations vs. weekly Redfin cadence — be clear in UI: "Alerts fire as soon as the data we receive shows the signal — Redfin updates Thursdays."

**Effort:** 4–6 weeks. Parallelizable across 3–4 agents (auth/scenarios/finance/alert pipeline). Watch out for serialization on Postgres LISTEN/NOTIFY → Redis Streams migration if subscriber count grows during phase.

---

# Phase 5 — Risk overlays + second metro (3–5 weeks)

**Goal:** Validate the multi-metro architecture and round out FTHB risk disclosures.

**Deliverables:**

- New adapters:
  - `packages/adapters/fema_flood.py` (NFHL)
  - `packages/adapters/calfire_fhsz.py`
  - `packages/adapters/usgs_quake.py` (faults + liquefaction)
  - `packages/adapters/epa_aqi.py`
- Risk overlay component on every parcel/area page.
- Wildfire surcharge factored into insurance estimate in `monthly_cost` (closes a hole from Phase 1).
- Sacramento metro onboarding:
  - `GeographicArea` rows for metro/counties/cities/ZIPs/school districts.
  - Census TIGER + CDE ingest scripts run for Sacramento.
  - Redfin CSV adapter configured for new ZIPs.
  - **No core code changes** — onboarding is config + data ingest only (validates F-MM-01).
- Metro-onboarding runbook in `docs/runbooks/onboard-metro.md`.

**Requirements satisfied:** F-RSK-01–03, F-MM-01 (validated), F-MM-02–03.

**Dependencies:** Phase 4 stable.

**Exit criteria:**

- [ ] All Bay Area area pages show wildfire/flood/earthquake/AQI overlays.
- [ ] Sacramento metro live; URLs at `/sacramento/...` work.
- [ ] Sacramento onboarding required no changes to `apps/api`, `apps/web`, or `packages/finance/` (pure config + ingest).
- [ ] Runbook tested by re-running it against a hypothetical "Portland" metro (dry-run only).

**Decisions to make first:**

- Climate projection data source — Cal Adapt? First Street Foundation? Defer if no clear winner.
- Sacramento school data — does CDE format work as-is, or are there per-district quirks?

**Risks:**

- "Adding a metro is config-only" is aspirational; first attempt usually finds 1–3 places where code change leaks in. Plan to fix and document as part of the runbook.

**Effort:** 3–5 weeks. Mostly parallelizable.

---

# Phase 6 (gated) — MLS realtime via RESO (8–12 weeks if greenlit)

**Goal:** Sub-minute realtime listing data — only if differentiation is clear and IDX compliance is acceptable.

**Decision gate at Phase 5 close:**

- Are alerts driving meaningful retention (DAU/MAU)?
- Is the cost ($300–1500/mo per MLS) justified by paid-tier conversion?
- Is the legal team comfortable with IDX rules (per-MLS terms, attribution, takedown)?
- If NO to any → defer indefinitely; the product is complete without this.

**Deliverables (if greenlit):**

- MLS aggregator selection (Bridge / SimplyRETS / Repliers).
- New adapter: RESO Web API + EntityEvent webhook receiver. Writes to `listing` and `market_signal` tables (kinds: `new_listing`, `price_change`, `status_flip`, `sold`).
- Webhook receiver endpoint (FastAPI) with HMAC verification, replay protection (sequence tracking).
- `Listing` table populated from MLS feed; previous Redfin-derived listings retired.
- IDX-compliant listing detail pages.
- Phase 4 alert pipeline gains 4 new signal kinds (no other code changes — validates the design).

**Requirements satisfied:** F-RT-04 (full), NF-DAT-06 realtime tier (sub-minute).

**Dependencies:** MLS contract signed; legal review complete.

**Exit criteria:**

- [ ] New listing in subscribed area triggers in-app alert within 60 seconds P95.
- [ ] No code changes outside `packages/adapters/mls_*` and migration adding the 4 signal kinds.
- [ ] IDX compliance audit passes.

**Risks:**

- MLS terms vary wildly per association. Some require user authentication for full data display.
- Cost compounds across metros — re-evaluate per-metro economics.

---

## Cross-phase risk register

| Risk | Phase | Severity | Mitigation |
|------|-------|----------|------------|
| Redfin CSV format change | 0+ | High | Bronze immutability; schema validation; auto-alert on parse anomalies |
| GreatSchools commercial license needed at monetization | 3 → 4 | Medium | Document license in `data_source.license`; budget paid tier |
| Fair Housing UI review forces redesign | 3 | Medium | Run review checklist before final UI lock; consult counsel |
| pgcrypto key loss locks out user financial data | 4 | High | **Block Phase 4 on key escrow runbook**; test recovery |
| Alert latency under load | 4 | Medium | Load-test 10x expected volume before launch; have Redis Streams migration plan ready |
| TS port drift from Python finance | 1+ | Medium | Golden-file tests in CI; both sides fail if outputs differ |
| MLS contract scope-creep | 6 | High | Decision gate at Phase 5 close; defer if not clearly justified |
| Boundary data CRS bugs | 2 | Medium | Validate `ST_IsValid` on every geometry on insert; test with known-good fixtures |
| Solo-dev burnout / scope drift | all | High | Phase exit criteria are testable; resist mid-phase scope add — log as next-phase backlog |

---

## Decisions log (decide before each phase)

Each decision should land in a one-page ADR in `docs/adr/`.

| # | Decision | Decide by |
|---|----------|-----------|
| D1 | Package manager: `uv` vs. `requirements.txt` | Phase 0 start |
| D2 | TS port strategy: hand-port + golden-file vs. transpile | Phase 1 start |
| D3 | Hosting: Vercel + Neon vs. self-host | Phase 2 start |
| D4 | Pub/sub: Postgres LISTEN/NOTIFY → Redis Streams threshold | Phase 2 start, revisit Phase 4 |
| D5 | Dagster Cloud vs. self-host | Phase 2 start |
| D6 | School zone source per district | Phase 3 start |
| D7 | Demographic data display policy | Phase 3 start |
| D8 | Pricing model: free vs. freemium | Phase 4 start |
| D9 | Email service: Resend vs. Postmark | Phase 4 start |
| D10 | MLS integration go/no-go | Phase 5 close |

---

## Suggested team-of-agents work allocation

If launching parallel agents, the natural decomposition is:

| Track | Owner profile | Phases active |
|-------|---------------|---------------|
| **Data ingestion** | Adapter writer; comfortable with HTML/CSV parsing, CRS handling | 0, 2, 3, 5 |
| **Finance / computation** | Pure-function discipline; 95% coverage habit | 1, 4 |
| **Backend** | FastAPI / SQLAlchemy / migrations | 2, 4 |
| **Frontend** | Next.js RSC, Mapbox, charts | 1 (subset), 3, 4 |
| **ETL / pipeline / events** | Dagster, LISTEN/NOTIFY, signal pipeline | 2, 4 |
| **Reviewer / glue** | Code review, persona checks, doc updates | continuous |

Inter-track contracts:

- Data ingestion ↔ Backend: `MarketSnapshot` row shape (defined in `datamodel.md` §6).
- Finance ↔ Backend: function signatures (defined in `design.md` §5.1).
- Backend ↔ Frontend: OpenAPI spec generated on every API change.
- ETL ↔ Backend: `MarketSignal` row shape + LISTEN/NOTIFY channel name.

Maintain these contracts as "interface" PRs reviewed before parallel implementation lands.

---

## What success looks like at each phase gate

| End of phase | Demo-able outcome |
|--------------|-------------------|
| 0 | "We have a `data/2026-05-14.json` file with all 7 seed cities, every metric tagged with source + freshness tier + confidence. The status page is green." |
| 1 | "Open a Python REPL: `affordability(income=300_000, down=150_000, rate=0.065)` returns `{comfortable: 1_050_000, stretch: 1_350_000, max: 1_600_000}`. Same call from Node returns the same thing. Coverage report shows 96%." |
| 2 | "I open `bayre.app` (or whatever it ends up being). I land on `/bay-area/cities/fremont` and see real numbers from Neon. Affordability widget personalizes the display. The status page shows last-fetch within 6h of Redfin's Thursday publish." |
| 3 | "I click Foothill HS Pleasanton. I see the median SFH zoned to Foothill is $X, with a $Y/sqft premium over the rest of Pleasanton. I open the fragmentation viz: Foothill, Fremont HS Sunnyvale, Dublin HS Dublin are at clock positions 2, 5, and 11 respectively." |
| 4 | "I save Foothill HS as a watch. Three days later I get a push notification: 'Months of supply in the Foothill zone just crossed 3.0 — first time in 18 months. Cooling phase detected.' I click through to a recomputed cost-of-waiting." |
| 5 | "I open Sacramento. Every Bay Area feature works. I see flood and wildfire overlays for both metros." |
| 6 (gated) | "A new listing matching my criteria hits MLS at 9:47am. I get an in-app alert at 9:48am." |

---

## Open follow-ups (carry forward)

These are pulled from prior persona reviews in `requirements.md`, `design.md`, `datamodel.md`:

- Backup key escrow runbook (Phase 4 blocker).
- Threat model doc (Phase 4 blocker).
- Metro-onboarding runbook (Phase 5 deliverable).
- Decide encryption strategy for `Scenario.notes`.
- Per-metric source-disagreement thresholds confirmed in `design.md` §3.3.
- Per-metric confidence thresholds confirmed in `design.md` §5.2.
- Confirm with counsel: SALT cap modeling in F-TCO-03.
- Validate Redfin CSV terms for personal/non-commercial use.
- Calibrate Market Phase formula weights against historical data (Phase 3).
