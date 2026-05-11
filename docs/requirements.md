# Requirements

> Status: Draft v1 · Owner: project lead · Last updated: 2026-05-10
> This document is the **what and why**. Architecture is in `design.md`, the entity model is in `datamodel.md`, and sequencing is in `implementation-plan.md`.

---

## 1. Vision

A decision-support web product that helps Bay Area first-time home buyers (FTHB) answer **where to buy, what type to buy, when to buy, and at what price** using their actual financial situation and personal priorities — not generic medians.

### Why this exists

The information FTHBs need is publicly available but fragmented across Redfin, Zillow, GreatSchools, county assessor sites, FEMA maps, and mortgage calculators. None of these tools combines them into a single personalized view. The opportunity is in *interpretation*, not data: turning "median sale price $1.5M" into "at your income that's a 42% DTI — comfortable max in this city is $1.1M" with the math shown.

### Non-goals

- Listing aggregation / "homes for sale" search (Redfin and Zillow already do this well; we'd compete on their turf).
- Agent matching, mortgage origination, or any transactional flow.
- Investment-property analysis (cap rates, rental yield) — different audience, different math.
- Predictive "the market will do X" claims. We surface indicators; we do not forecast.

---

## 2. Operating principles

These constrain every feature decision. When two requirements conflict, the principle higher in this list wins.

1. **Show the math.** Every number must be one click from its derivation. No black-box scores.
2. **Honest about uncertainty.** Distinguish fact (recorded sale) from estimate (smoothed index) from projection (5-yr trend) visually and in copy.
3. **Personalized over aggregated.** A median is a starting point; the product's value comes from filtering it by the user's income, down, debt, and priorities.
4. **No decisions, only frameworks.** Output is "here's what this means for you," never "you should buy." Reduces liability and builds trust.
5. **Educate inline.** Define every domain term (Mello-Roos, PMI, jumbo, DTI, Prop 13) at point of use, not in a separate glossary.
6. **Scale through abstraction.** Adding a new metro should be a config + data ingest, not a code change.
7. **Anonymous-first.** Core value (affordability, market data, school stats) is usable without an account. Auth gates only saved scenarios and alerts.
8. **Freshness is a feature.** Every served number carries a freshness tier label and an `as_of` timestamp. The product's value depends on users trusting that they're seeing today's reality, not last quarter's.
9. **Event-driven, not poll-driven.** Internal architecture treats data updates as events that flow through the system. This is what makes realtime alerts and the "what changed" feed possible without a rewrite.
10. **Timing is a first-class surface, not a tab.** The "should I buy now or wait" question is the highest-stakes question an FTHB asks. It gets a top-level page (`/timing`), explicit decision frameworks, and personalized cost-of-waiting math — not a sidebar widget.

---

## 3. Audience

### Personas (Bay Area FTHB cohorts)

| ID | Persona | Income band | Down | Primary anxiety | Key feature |
|----|---------|-------------|------|-----------------|-------------|
| P1 | DINK Tech | $400–700K | $200K+ (RSU) | "Should we wait for a crash?" | Market timing, TCO |
| P2 | Single Tech IC | $250–400K | $80–150K | "Can I afford anything?" | Affordability + condo focus |
| P3 | Family Forming | $300–500K | $150K+ | "Which schools, and what's the premium?" | School-zone drill-down |
| P4 | Move-Up From Rental | $250–500K | $100K+ | "Is owning actually better than renting?" | Rent vs. buy |
| P5 | Multigen / In-Law | $300–600K | varies | "ADU potential? Lot size?" | Parcel-level data |
| P6 | Wait-And-See | $300K+ | $200K+ | "Validate that I should not buy now." | Market signals, honest framing |

P1–P3, P6 are the priority cohorts for the first year; P4 is well-served by Pillar C (rent vs. buy) and Pillar F (timing); P5 is deferred until parcel-level data is in.

### Jobs-to-be-done

| JTBD | One-line | Priority |
|------|----------|----------|
| J1 | "Tell me what I can actually afford, and where." | P0 |
| J2 | "Help me understand the true cost of owning here vs. there vs. renting." | P0 |
| J3 | "Tell me which areas match my school / commute / lifestyle priorities." | P1 |
| J4 | "Tell me whether the market is hot or cooling — should I wait?" | P1 |
| J5 | "Help me compare my finalist neighborhoods side-by-side." | P1 |

Every functional requirement below traces to at least one JTBD.

---

## 3a. Competitive landscape & differentiators

A scan of the FTHB tooling market (May 2026) shows the space is unbundled: each tool does one thing well; no tool integrates them.

| Tool / source | What it does well | Where it falls short for FTHB |
|---|---|---|
| [Redfin](https://www.redfin.com/news/data-center/) | Realtime listings, weekly market data ([Thursdays 1pm ET, 4-week rolling](https://www.redfin.com/news/data-center/methodology/)) | No personalized affordability; no "should I buy now" framing |
| [Zillow](https://www.zillow.com) / [ZORI rent index](https://www.zillow.com/research/methodology-zori-repeat-rent-27092/) | Listings, rent index, ZHVI smoothed valuation | Black-box "Zestimate"; no school-zone scoping; no decision interpretation |
| [GreatSchools](https://www.greatschools.org) | School ratings | Single number, no context; no integration with home prices |
| [NerdWallet](https://www.nerdwallet.com/mortgages/best/online-mortgage-lenders) / mortgage calculators | Static affordability math | No local data integration; no timing |
| [MGIC Buy Now vs. Wait](https://www.mgic.com/tools/buynow) | Cost-of-waiting calculator | Generic appreciation assumptions; no metro-specific data; no school/commute layer |
| [Realtor.com Market Clock](https://www.realtor.com/research/market-clock-report-2026q1) | Quarterly cycle-phase classification per metro | Quarterly cadence (not realtime); metro-only (no city / school zone); narrative not actionable |
| [Compass Intelligence](https://www.compass.com/research/market-outlook/) | Glossy market reports | PDF / quarterly; no personalization; agent-funnel UX |

**The market gap (this product's wedge):**

1. **Personal × Local × Timing.** No tool combines the user's actual finances with sub-metro (city + school zone) micro-market data and an explicit timing decision framework.
2. **Sub-metro fragmentation.** Realtor.com's Q1 2026 report explicitly calls the US market "the most fragmented in 8 years" — meaning a single metro number hides the truth. We compute Market Phase per **city and per school zone**, not per metro.
3. **Realtime decision relevance.** Existing tools either have realtime data (Redfin) or decision frameworks (MGIC / NerdWallet) but never both. We push alerts when a *decision-relevant* signal changes, not just when a number moves.
4. **Show-the-math interpretation.** Redfin gives you "median $1.5M"; we give you "median $1.5M; at your income that's a 42% DTI; market phase is 'cooling' — expect 3–5 more months of inventory growth historically."

These four points are the marketing positioning AND the architectural drivers of every requirement below.

---

## 4. Functional requirements

Conventions: `MUST` = required for the feature to ship; `SHOULD` = strongly preferred; `MAY` = nice to have. Each requirement has a stable ID for traceability.

### 4.1 Affordability engine (J1)

- **F-AFF-01** MUST accept inputs: gross household income (with optional base/bonus/RSU split), liquid down + closing budget, monthly debt obligations, credit score band, mortgage rate (with current 30Y default from FRED), term (15/30).
- **F-AFF-02** MUST output three price points: comfortable (28% front-end DTI), stretch (36% back-end DTI), maximum approvable (per loan type — conforming, high-balance conforming, jumbo, FHA, with current county limits).
- **F-AFF-03** MUST show, for each city/area in view, a green / yellow / red affordability badge tied to the user's inputs.
- **F-AFF-04** MUST show monthly breakdown at any selected price: P&I, property tax (Prop 13 base + voted assessments), Mello-Roos (per-parcel when known, area-typical otherwise), HOA, insurance (with wildfire surcharge for high-FHSZ areas), PMI when applicable, maintenance reserve.
- **F-AFF-05** MUST persist user inputs in browser localStorage anonymously; SHOULD persist server-side when authed.
- **F-AFF-06** SHOULD recompute live as inputs change (no submit button).
- **F-AFF-07** SHOULD show a rate sensitivity slider (±2 percentage points) with live monthly impact.
- **F-AFF-08** MUST link every output to its calculation breakdown ("show the math" — principle #1).
- **F-AFF-09** MUST display "not financial advice" disclaimer prominently in the affordability surface.
- **F-AFF-10** MUST prefill inputs with a median Bay Area FTHB profile (default: $300K household income, $150K down, $0 monthly debt, current 30Y rate from FRED) on first visit, with a clear "this is an example — change it" banner. localStorage overrides the example after first user input. *(UX-review-derived)*
- **F-AFF-11** SHOULD display a non-modal banner after 30 seconds on an area page, prompting the user toward Cost-of-Waiting if they haven't yet visited it. *(UX-review-derived)*
- **F-AFF-12** Monthly cost breakdown (per F-AFF-04) MUST be inline-expandable on the same page — never a modal or separate page navigation. *(UX-review-derived)*
- **F-AFF-13** Income input defaults to a single "household income" field. Splitting into base / bonus / RSU MUST be a progressive opt-in toggle, not always visible. *(UX-review-derived)*

### 4.2 True cost of ownership (J2)

- **F-TCO-01** MUST compute total cost over 5 / 10 / 30-year horizons.
- **F-TCO-02** MUST include amortized P&I, property tax (compounded at 2% Prop 13 cap), HOA, Mello-Roos (with expiration when known), insurance, maintenance reserve (1–2% of value), major repair sinking fund.
- **F-TCO-03** MUST include the federal mortgage interest tax shield, capped by the SALT $10K limit.
- **F-TCO-04** MUST include opportunity cost of the down payment (configurable expected return; default 7% S&P).
- **F-TCO-05** SHOULD show principal vs. interest split per year.
- **F-TCO-06** MUST allow comparing two price points / two areas side by side.

### 4.3 Rent vs. buy (J2, J4)

- **F-RVB-01** MUST pull median rent (Zillow ZORI or equivalent) by area and bedroom count.
- **F-RVB-02** MUST compute years-to-breakeven under conservative / base / aggressive home appreciation scenarios.
- **F-RVB-03** MUST include selling costs (commission + transfer tax) weighted by user-specified probability of moving in N years.
- **F-RVB-04** SHOULD show 5-yr and 10-yr wealth difference (own − rent) chart.
- **F-RVB-05** MUST disclose all assumptions on the same page where the answer appears.

### 4.4 Geographic discovery & school drill-down (J3)

- **F-GEO-01** MUST support area pages for: metro, county, city, neighborhood, ZIP, school attendance zone.
- **F-GEO-02** MUST render the same metric set on every area page (median price, $/sqft, DOM, sale-to-list ratio, months of supply, SFH/condo/townhome split, 5-yr trend chart).
- **F-GEO-03** MUST render attendance-zone-scoped market snapshots (i.e., "median SFH price for homes zoned to Mission San Jose HS").
- **F-GEO-04** MUST surface the **school premium** ($/sqft delta vs. surrounding non-zoned area) for each high-rated school zone.
- **F-GEO-05** MUST display feeder elementary → middle → high school chain on each school page.
- **F-GEO-06** SHOULD show a map view with school-zone choropleth toggleable by metric (median price, $/sqft, DOM, school rating).
- **F-GEO-07** MUST disclose attendance-zone effective dates (zones change; users must see "as of" date).
- **F-GEO-08** MUST follow Fair Housing rules: no demographic filters, no "neighborhood quality" rankings that proxy for protected classes. School ratings are presented with multiple sources side-by-side (GreatSchools, raw test scores, Niche when available) so users form their own view.

### 4.5 Comparison (J5)

- **F-CMP-01** MUST allow selecting 2–4 areas (cities or school zones) for side-by-side comparison.
- **F-CMP-02** MUST render: median SFH/condo, Mello-Roos likelihood, school API, commute to user-selected employer hub, personalized affordability badge, 5-yr price growth, wildfire risk, flood risk.
- **F-CMP-03** MUST link every cell to its calculation breakdown.
- **F-CMP-04** SHOULD allow exporting the comparison as PNG or PDF.
- **F-CMP-05** "Add to compare" button MUST exist on every area card; clicking populates a sticky bottom drawer showing the active comparison set with quick-remove. *(UX-review-derived)*
- **F-CMP-06** On viewports < 768px, the comparison matrix MUST collapse to one accordion per area with metrics inline. *(UX-review-derived)*
- **F-CMP-07** Comparison view MUST support column-group show/hide (price, schools, commute, risk) for power-user focus. *(UX-review-derived)*

### 4.6 Market timing — first-class decision surface (J4) [PRIORITY: P0 for cohort P6]

This is the product's primary differentiator. Existing tools (Redfin, Zillow, Realtor.com) report market stats; few interpret them as a *timing decision*. Realtor.com publishes a quarterly "Market Clock" report that classifies metros into cycle phases ([Q1 2026 report](https://www.realtor.com/research/market-clock-report-2026q1) flagged the US as "the most fragmented housing market in 8 years" — meaning sub-metro phases diverge sharply, exactly the gap we're filling). MGIC's [Buy Now vs. Wait calculator](https://www.mgic.com/tools/buynow) computes "cost of waiting" but doesn't integrate with personal affordability or local micro-market data. We combine all of it.

- **F-TIM-01** MUST display per area: months of supply, % listings with price drops, median price drop %, sale-to-list ratio trend (4-week + 12-week), inventory YoY, new-listings velocity, pending-sales velocity, mortgage rate context vs. 5-yr and 30-yr history.
- **F-TIM-02** MUST compute and display a **Market Phase classification** per area (peak / cooling / trough / recovery), modeled after Realtor.com's Market Clock but computed at sub-metro granularity (city + school zone). Formula and inputs MUST be visible on click.
- **F-TIM-03** MUST surface a **"Cost of Waiting" / "Cost of Acting Now"** calculator that takes the user's affordability inputs + a target area and computes, for waiting horizons of 3 / 6 / 12 / 24 months under three appreciation × three rate scenarios:
  - Lost / gained appreciation
  - Rent paid during waiting period
  - Monthly payment delta from rate change
  - Net dollar impact + break-even rate scenarios
- **F-TIM-04** MUST overlay seasonality bands on price/inventory charts (Bay Area: peak listings Mar–May, peak buyer competition Apr–Jun, soft window Nov–Jan).
- **F-TIM-05** MUST annotate timeline charts with macro events (Fed rate decisions, conforming-loan-limit changes annually, major tech layoffs, NVDA/Meta/Google earnings as RSU-driven local demand proxies).
- **F-TIM-06** SHOULD display **fragmentation visualization** — Bay Area cities + school zones plotted on a Market Clock face simultaneously, so users see at a glance that Pleasanton may be at 4 o'clock while Sunnyvale is at 1.
- **F-TIM-07** MUST display a prominent "indicators, not predictions" disclaimer in the timing surface; MUST avoid any language that implies certainty about future direction.
- **F-TIM-08** SHOULD provide a **timing-fit score per scenario** (0–100): how well the user's stated timeline (timeline_months input) aligns with the current market phase of their target areas. Output is descriptive ("market is cooling — patience may be rewarded; expect more inventory by Q3") not prescriptive.
- **F-TIM-09** MUST allow CSV export of all underlying timing data per area (P6 cohort wants raw data to validate).
- **F-TIM-10** Cost-of-Waiting page MUST have a "Save this scenario" button that writes to localStorage anonymously and prompts auth on second visit. *(UX-review-derived)*
- **F-TIM-11** On viewports < 768px, the Cost-of-Waiting 3×3 grid MUST collapse to a vertical card list with the base case rendered first. *(UX-review-derived)*

### 4.11 Realtime updates [PRIORITY: P0 differentiator]

This is what no existing FTHB tool does well. Redfin and Zillow have realtime listings but no decision interpretation; decision tools (MGIC, NerdWallet) are static calculators with no live data. Combining both is the moat.

Freshness has tiers driven by source capability — see NF-DAT-06 below for the SLA per tier:

| Tier | Update cadence | Sources | Examples |
|------|----------------|---------|----------|
| **Realtime (sub-minute)** | Push via webhook | MLS / RESO Web API EntityEvent | New listing, price change, status flip in saved zones |
| **Near-realtime (≤ 1 hour)** | Pull on event | Mortgage rate APIs, FRED daily series | 30Y rate moves > 0.05pp |
| **Daily** | Scheduled pull | Redfin some series, FRED | Mortgage rate close, conforming limit changes |
| **Weekly** | Scheduled pull | Redfin Data Center weekly (Thursdays 1pm ET, rolling 4-week windows) | Inventory, DOM, sale-to-list updates |
| **Monthly / quarterly** | Scheduled pull | Redfin monthly, GreatSchools | School ratings, county-level deep stats |
| **Annual** | Scheduled pull | Census, conforming limits, tax law | Boundary changes, jumbo limits |

#### Functional requirements

- **F-RT-01** MUST classify every served metric into a freshness tier and surface its tier label + last-update timestamp in the UI on hover/click.
- **F-RT-02** MUST update weekly market data within 6 hours of source publication (Redfin publishes Thu 1pm ET; we MUST refresh by Thu 7pm ET).
- **F-RT-03** MUST update mortgage rate context within 1 hour of FRED publication on weekdays.
- **F-RT-04** SHOULD support MLS realtime feed (RESO Web API + EntityEvent webhooks) when MLS license is acquired in Phase 6. Architecture MUST be event-driven from Phase 2 onward so this slots in without rewrite.
- **F-RT-05** MUST surface a **"What changed" feed** per saved area showing chronological events (new listing, price drop, sold, market-phase shift) for the last N days. Users opt-in per area.
- **F-RT-06** MUST emit user-facing alerts (in-app banner + optional email) when any of these occur in user's saved areas:
  - Market phase transition (e.g., "Fremont SFH moved from cooling → trough")
  - Months of supply crosses 3 (buyer/seller market threshold)
  - Sale-to-list ratio drops below 1.0 (no more bidding wars)
  - DOM exceeds user-set threshold
  - Mortgage rate crosses a user-set value
  - (Phase 6) New listing matching saved criteria
  - (Phase 6) Price drop > 2% on watched listing
- **F-RT-07** MUST provide alert delivery channels: in-app, email digest (immediate / daily / weekly), web push notification. SMS deferred.
- **F-RT-08** MUST deduplicate alerts (no more than one alert per (user, area, signal) per 24h unless severity escalates).
- **F-RT-09** MUST allow alert snoozing per area (mute for 7/30 days).
- **F-RT-10** SHOULD display a "freshness header" at the top of every area page: "Last updated: 18 minutes ago · 12 data points refreshed today · Source breakdown ↓"
- **F-RT-11** SHOULD provide a public **status page** showing per-source ingest health and last successful refresh.
- **F-RT-12** Alert subscription UI MUST default to a curated bundle ("watch for material market changes"); per-signal customization is behind a "Custom thresholds" disclosure. *(UX-review-derived)*
- **F-RT-13** Every dispatched alert (in-app or email) MUST include "Mute 7d" / "Mute 30d" / "Edit thresholds" inline actions. *(UX-review-derived)*
- **F-RT-14** Email and in-app digests MUST follow a "3 things to know this week" structure: (1) phase movement, (2) affordability impact, (3) one notable area-level change. Not a metric dump. *(UX-review-derived)*
- **F-RT-15** A PWA manifest + service worker MUST be shipped in Phase 4 enabling install-to-home-screen + offline cache of last-viewed area pages. *(UX-review-derived)*

#### Why this matters for FTHB

The home-buying decision window is asymmetric: a great house in a target zone gets bid up within 72 hours; a mortgage-rate dip below a threshold could move a borderline-affordable home to comfortable. A user who learns about either event a week late has effectively missed the signal. Realtime alerts compress the user's reaction time from "I check the dashboard every Sunday" to "the dashboard tells me when something changed."

### 4.7 Risk & disclosure layer

- **F-RSK-01** MUST surface, per area: wildfire (Cal Fire FHSZ), flood (FEMA), earthquake (USGS faults + soil liquefaction), sea-level rise (BCDC), air quality history (EPA AQI / PurpleAir).
- **F-RSK-02** SHOULD surface climate projections (heat days, drought indicators).
- **F-RSK-03** MUST link to the authoritative source for each risk indicator.

### 4.8 Education hub

- **F-EDU-01** MUST provide explainer pages for: Mello-Roos, Prop 13, conforming/high-balance/jumbo limits by county, PMI, DTI, escrow, preliminary title report, ADU rules by city, closing-cost negotiation.
- **F-EDU-02** MUST cross-link explainers from in-app tooltips at point of use.
- **F-EDU-03** SHOULD optimize for SEO (this is the discovery channel for FTHB users).
- **F-EDU-04** Every defined glossary term in the UI MUST be a tappable badge that opens an inline definition card on tap (not just hover) — required for mobile parity. *(UX-review-derived)*

### 4.9 Saved scenarios & alerts (auth)

- **F-SCN-01** MUST allow authed users to save a Scenario (target areas, property type, financial assumptions, must-haves, nice-to-haves with weights).
- **F-SCN-02** MUST allow saving multiple named Scenarios per user (e.g., "now," "if rates drop to 6%," "if we push to $200K down").
- **F-SCN-03** MUST allow comparing Scenarios.
- **F-SCN-04** MUST support multiple alert delivery channels (see F-RT-07): immediate in-app, immediate email, daily digest, weekly digest, web push.
- **F-SCN-05** MUST allow exporting and deleting all user data (CCPA).
- **F-SCN-06** SHOULD allow users to specify alert thresholds per signal type (e.g., "alert me when 30Y rate drops below 6.0%" or "when DOM in Mission San Jose zone exceeds 25 days").
- **F-SCN-07** Auth settings MUST include a "Sessions" view listing active devices/IPs with revoke-individual and revoke-all actions. *(UX-review-derived)*
- **F-SCN-08** After 2–3 anonymous interactions with affordability inputs, a non-blocking "save these inputs" prompt SHOULD appear. *(UX-review-derived)*
- **F-SCN-09** Auth settings MUST allow specifying preferred digest cadence + timezone + optional quiet-hours window. *(UX-review-derived)*

### 4.10 Multi-metro readiness

- **F-MM-01** MUST treat the current 7 cities as one configured metro (Bay Area). Adding Sacramento or another metro MUST require only configuration + data ingest, not core code changes.
- **F-MM-02** MUST namespace URLs by metro (`/bay-area/cities/fremont`).
- **F-MM-03** MUST scope analytics, alerts, and comparisons within a single metro by default (cross-metro comparison is a separate, opt-in mode).

### 4.12 Navigation & wayfinding *(UX-review-derived)*

- **F-NAV-01** Primary nav MUST be exactly: `Areas | Timing | Compare | Map | Saved | Learn` (6 items; fits desktop tab bar and mobile bottom nav). Cities/schools/zips/neighborhoods are reached *through* `Areas`, not as top-level items.
- **F-NAV-02** A global Cmd+K command palette MUST be available on every page, supporting search by area name, school, ZIP, glossary term. Built on shadcn `<Command>` (cmdk).
- **F-NAV-03** Every page below `/[metro]` MUST render a breadcrumb (e.g., `Bay Area › Cities › Fremont › Schools › Foothill HS`).

### 4.13 Data presentation states *(UX-review-derived)*

- **F-DATA-01** A standardized `<DataNotice>` component MUST render any of: `missing | stale | sources-disagree | low-confidence | rate-fallback`. Each variant has prescribed copy + icon + action. No ad-hoc "Sorry, an error occurred" strings allowed in user-facing surfaces.
- **F-DATA-02** When the mortgage-rate fetch fails, the affordability widget MUST display the most recent successful rate with an inline `<DataNotice variant="rate-fallback">` showing the `as_of` date and a refresh button.
- **F-DATA-03** Numbers where source disagreement (NF-DAT-04) was detected MUST render a `(?)` icon next to the value; clicking opens a popover listing each source's value.

### 4.14 Cognitive load & monetization signaling *(UX-review-derived)*

- **NF-UX-01** Default-collapse rule: any page with > 3 metrics in a section MUST default-collapse the 4th onward behind a "Show more" affordance.
- **F-MON-01** If/when freemium ships (decision D8), paid features MUST display a small "★" badge inline; tapping the badge explains the tier — no surprise paywall after data entry.

---

## 5. Non-functional requirements

### 5.1 Data quality & freshness

- **NF-DAT-01** Every served number MUST carry source attribution, `as_of` timestamp, and confidence level (low / medium / high based on sample size).
- **NF-DAT-02** Numbers older than 14 days MUST be visually flagged as stale.
- **NF-DAT-03** Low-confidence numbers (sample size below per-metric threshold) MUST be visually de-emphasized.
- **NF-DAT-04** When sources disagree by more than 5% on the same metric for the same area/period, the system MUST log the discrepancy and surface a "sources disagree" indicator on the affected number.
- **NF-DAT-05** Source-of-record (Bronze) data MUST be retained immutably so Silver/Gold can be re-derived after parser changes.
- **NF-DAT-06** Per-tier freshness SLA (P95 measurement: tip-of-source publication → user-visible value):
  - **Realtime tier:** ≤ 60 seconds (Phase 6, MLS feed)
  - **Near-realtime tier:** ≤ 1 hour (mortgage rates, FRED daily series)
  - **Daily tier:** ≤ 6 hours from source publication
  - **Weekly tier:** ≤ 6 hours from source publication (Redfin Thu 1pm ET → ours by Thu 7pm ET)
  - **Monthly+ tier:** ≤ 24 hours from source publication
- **NF-DAT-07** Architecture MUST be event-driven from Phase 2 onward. Specifically: ETL emits `MarketSignal` events on every snapshot recompute; alert evaluation subscribes to these. Polling-based alert evaluation is forbidden.
- **NF-DAT-08** A public **status page** MUST display per-source ingest health, last successful fetch, and current SLA conformance for the prior 30 days.

### 5.2 Performance

- **NF-PRF-01** P75 page load (area page, cold cache) ≤ 2.0s on a 4G connection.
- **NF-PRF-02** P75 affordability recompute on input change ≤ 200ms (client-side after first API call).
- **NF-PRF-03** Map drill-in (click school zone → load page) ≤ 1.5s.
- **NF-PRF-04** ETL pipeline MUST complete a full Bay Area weekly refresh in ≤ 30 minutes.
- **NF-PRF-05** Alert evaluation latency (signal recomputed → user-facing alert dispatched) MUST be ≤ 5 minutes P95 for in-app/web-push, ≤ 15 minutes P95 for immediate email.
- **NF-PRF-06** "What changed" feed MUST render the last 30 days of events for a saved area in ≤ 500ms P75.
- **NF-PRF-07** Cold-cache area pages MUST render skeleton placeholders (Tremor sparkline shells + freshness badge visible) within 200ms; full data within NF-PRF-01 (2s). *(UX-review-derived)*
- **NF-PRF-08** Performance budgets (NF-PRF-01–06) MUST be enforced in CI via Lighthouse CI on every PR. PRs that regress P75 page load > 200ms fail the budget check. *(UX-review-derived)*

### 5.3 Reliability

- **NF-REL-01** Dashboard availability ≥ 99.5% monthly (allows ~3.6h downtime).
- **NF-REL-02** ETL failure for a single source MUST NOT block other sources or the user-facing site (degrade gracefully with stale-data indicator).
- **NF-REL-03** All calculations in `packages/finance/` MUST have ≥ 95% line coverage (this is the trust layer).

### 5.4 Security & privacy

- **NF-SEC-01** User financial inputs MUST be encrypted at rest (per row, not just disk-level).
- **NF-SEC-02** Privacy policy MUST disclose all data collected and retention periods.
- **NF-SEC-03** Account deletion MUST purge all PII within 30 days.
- **NF-SEC-04** Anonymous mode MUST function without any server-stored user data (localStorage only).
- **NF-SEC-05** No third-party trackers on pages where the user enters financial information.
- **NF-SEC-06** Affordability inputs interface MUST display first-party storage microcopy ("We save these on your device only — never sent to our servers unless you create an account") near the inputs. *(UX-review-derived)*

### 5.5 Compliance

- **NF-CMP-01** "Not financial advice" disclaimer MUST appear in the affordability surface, the TCO surface, and the rent-vs-buy surface.
- **NF-CMP-02** No filters or rankings that proxy for protected classes under Fair Housing (race, religion, national origin, family status, disability).
- **NF-CMP-03** All external data sources MUST have their license tracked in the adapter; commercial-use limits (e.g., GreatSchools) MUST be respected before monetization.
- **NF-CMP-04** MLS data, if integrated, MUST follow IDX rules of the originating MLS.

### 5.6 Accessibility

- **NF-A11Y-01** WCAG 2.1 AA conformance for all user-facing pages.
- **NF-A11Y-02** All charts MUST have a textual / table alternative.
- **NF-A11Y-03** Color MUST NOT be the sole encoding of meaning (affordability badges include text + color + icon).
- **NF-A11Y-04** Tap targets MUST be ≥ 44×44px on viewports < 768px and ≥ 32×32px on desktop. Enforced via shared `<Tappable>` wrapper. *(UX-review-derived)*

### 5.7 Observability

- **NF-OBS-01** Every page render MUST emit a structured event with: page type, area_id, latency, data freshness scores.
- **NF-OBS-02** ETL runs MUST emit per-source success/failure, row counts, parse anomalies.
- **NF-OBS-03** "Sources disagree" events MUST be aggregated to a weekly review.
- **NF-OBS-04** SLA conformance per freshness tier (NF-DAT-06) MUST be tracked and surfaced on the public status page (NF-DAT-08).
- **NF-OBS-05** Alert pipeline MUST emit per-stage events (signal generated → user matched → channel dispatched → user opened) for funnel analysis.

### 5.8 Cost

- **NF-COST-01** Phase 0–2 MUST run within a hobby budget (≤ $50/mo all-in).
- **NF-COST-02** Per-user marginal cost (excluding paid data sources) MUST stay under $0.05/mo at 10K MAU.

---

## 6. Scope by phase

> Sequencing reflects elevation of timing (Pillar F) and realtime updates (4.11) as P0 differentiators after May 2026 product review.

| Phase | What ships | Why | Exit criteria |
|-------|-----------|-----|---------------|
| 0 | Data-ingest validation against the 7 seed cities (`docs/seed-data.md`): Redfin CSV adapter, schema-validated JSON snapshots with freshness tier labels (NF-DAT-06), GitHub Actions weekly run, public status page stub. **No extension of the prototype dashboard.** | De-risk data fragility; pin the seed-data spec | Adapter produces valid weekly JSON for the 7 cities; freshness tier on every metric |
| 1 | Pure-function packages: `affordability`, `timing.compute_phase`, `cost_of_waiting`, `tax_rules`, with TS port + golden-file tests + property-based tests. Static MDX glossary. **No user-facing UI.** | Lock in the trust layer (`packages/finance/`) before any UI consumes it | ≥95% line coverage; Python↔TS golden-file tests pass; glossary committed |
| 2 | Greenfield Next.js + FastAPI on Vercel + Railway + Neon. Domain model, adapter pattern, **event-driven snapshot pipeline** (NF-DAT-07), all Bay Area cities (~100), daily mortgage rate ingest, weekly Redfin within 6h SLA, all 18 priority `GeographicArea` rows from `seed-data.md` materialized | Foundation for everything else; lock in event-driven; deliver first user-facing pages | Seed-data §9 acceptance queries pass; snapshot insert fires `market_signal` ≤ 10s |
| 3 | School drill-down, comparison tool, map view, **Market Phase classification per city + school zone**, fragmentation visualization. **The 3 priority schools digitized first.** | Killer features for Family Forming + Wait-And-See cohorts | The 3 priority school pages render with full data; Fair Housing review passed |
| 4 | TCO, rent vs. buy, auth, saved scenarios, **realtime alert engine** (in-app + email + web push), "what changed" feed | Engagement loop, return visits, realtime differentiator delivered | Authed users save scenarios and receive alerts within NF-PRF-05 latency budget |
| 5 | Risk overlays, second metro (Sacramento) | Validates multi-metro architecture | Sacramento ships with no core code changes |
| 6 (gated) | MLS listing integration via RESO Web API + EntityEvent webhooks (true sub-minute realtime) | Only if differentiation is clear and IDX compliance acceptable | Decision gate — re-evaluate at Phase 5 close. Architecture from Phase 2 must accept this without rewrite. |

Detailed sequencing in `implementation-plan.md`.

---

## 7. Open questions (decide before each phase)

These are left explicit so they don't get silently decided in code.

1. **Free / freemium / paid?** Affordability + market data should be free. Saved scenarios + alerts could gate signup. Decide before Phase 4.
2. **Hosting choice** — Vercel + Neon vs. fully self-hosted. Decide before Phase 2.
3. **GreatSchools licensing** — free tier is non-commercial only. If monetizing, need paid tier or alternative source. Decide before Phase 3.
4. **MLS integration** — $300–1500/mo per market and brings IDX compliance burden. Decide at Phase 5 close.
5. **Demographic data display** — Census ACS data on income / household composition is informative but legally sensitive. Decide policy before Phase 3.
6. **AI / LLM features** — easy to misuse for advice ("should I buy?"). If used, scope strictly to neighborhood summarization from public data. Decide before any LLM feature ships.
7. **Multi-metro UI mode** — single-metro-default vs. global search? Decide before Phase 5.

---

## 8. Persona review log

This requirements doc was reviewed against the following lenses:

- **FTHB (P3 Family Forming):** Confirms school-zone scoping (F-GEO-03, F-GEO-04) addresses the primary need. Asks: where is "is this house in this school zone" — answered by F-GEO-03 plus parcel-level lookup (deferred to Phase 5+).
- **Product manager:** Confirms scope is phased and exit criteria are testable. Flags: F-MM-01 ("only config + data ingest") is aspirational; we should write a metro-onboarding runbook in Phase 5 to enforce it.
- **Engineering lead:** Confirms NF-REL-03 (95% coverage on finance package) is achievable because finance is pure functions. Flags: F-AFF-04 (per-parcel Mello-Roos) is data-blocked — must caveat as "area-typical when parcel data unavailable."
- **Legal / compliance:** Confirms F-GEO-08, NF-CMP-02 cover Fair Housing. Adds NF-CMP-04 for MLS. Asks for explicit disclaimer placement (NF-CMP-01).
- **Data PM:** Confirms NF-DAT-01–05 capture source provenance. Flags: NF-DAT-04 ("sources disagree") needs a per-metric threshold table (TBD in `design.md`).

Open follow-ups from review:
- Add metro-onboarding runbook stub to implementation plan.
- Define per-metric source-disagreement thresholds in design doc.
- Confirm with counsel: SALT cap modeling in F-TCO-03 — fact, not advice. (My read: fine, it's deterministic math.)
