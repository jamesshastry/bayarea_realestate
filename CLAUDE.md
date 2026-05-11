# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project purpose

A decision-support tool for Bay Area first-time home buyers. The longer-term product direction (affordability calc, school-zone drill-down, TCO, multi-metro expansion, realtime alerts) is captured in `docs/`.

The current code at the repo root (`scrape.py`, `generate_dashboard.py`, `dashboard/index.html`) is a **throwaway prototype** — kept as data-ingest reference and visual-aesthetic inspiration only. Phase 2 (per `docs/implementation-plan.md`) is a greenfield Next.js + FastAPI + Postgres+PostGIS rebuild on Vercel + Railway + Neon. There is no migration; do not extend the prototype as if it's the production path.

## Commands

No package manager config exists yet. Dependencies are `requests` and `beautifulsoup4`. Install with:

```bash
pip install requests beautifulsoup4
```

Run the scraper (writes `data/YYYY-MM.json`):

```bash
python scrape.py                              # current month, all 7 cities
python scrape.py --month 2026-04              # tag a specific month
python scrape.py --cities Dublin Fremont      # subset
python scrape.py --dry-run                    # skip network, write empty stubs
```

Regenerate the dashboard (reads all `data/*.json`, writes `dashboard/index.html`):

```bash
python generate_dashboard.py
```

There are no tests, lint config, or build steps in the repo today. If you add Python code, prefer `pyright`/`mypy` and `ruff`; install ad-hoc rather than assuming they exist.

## Architecture

Two-stage, file-based pipeline — no server, no DB:

```
scrape.py  ──►  data/YYYY-MM.json  ──►  generate_dashboard.py  ──►  dashboard/index.html
```

**`scrape.py`** fetches from three sources per city (Redfin housing-market page, Zillow home-values page, Movoto market-trends page), then `build_city_record()` merges them with source-priority **Redfin > Movoto > Zillow** for median price. Each city has a hardcoded config (`CITIES` list) carrying per-source URL slugs/IDs. Manual overrides for any month/city can be supplied via `data/overrides.json`.

**`generate_dashboard.py`** loads every `data/????-??.json`, embeds the full payload into the HTML template by string-replacing `__ALL_DATA__`, and writes a single self-contained `dashboard/index.html`. All filtering, charting, and table rendering happen client-side via Chart.js.

### Things to know before editing

- **Path bug — both scripts use `Path(__file__).parent.parent / "data"` and `"dashboard"`.** This assumes the files live in a `scripts/` subdir, but they're currently at repo root, so output is written one level *above* the repo. Either move the scripts into `scripts/` or change the path to `Path(__file__).parent / "data"`. Don't silently work around this without fixing it — outputs will land in the wrong place.

- **`MANUAL_CONDO_NOTES` (scrape.py) is stale by design.** It seeds condo prices/DOM/sale-to-list from a March 2026 baseline because Redfin's main page only reports SFH. The dashboard renders these as if current with a small `~est` marker. Treat as a known tech-debt item; preferred fix is to add a real condo data source, not to keep updating the dict.

- **The scrapers are HTML-fragile.** Redfin/Zillow are React SPAs and the parsing relies on `og:description` meta tags and embedded `<script type="application/json">` blocks. Expect breakage when those sites redesign. The longer-term plan in `docs/` is to switch to Redfin Data Center CSVs.

- **`median_price` and Zillow's `zhvi` are conflated** in `build_city_record()` — median sale price is a transaction stat, ZHVI is a smoothed valuation index. They're not interchangeable; the current fallback chain is a known modeling shortcut.

- **Politeness matters.** `get()` enforces a 3–6 second delay per request with retries. Don't remove this when iterating — it's the only thing keeping the scrapers from getting blocked.

- **Dashboard data lives in the HTML.** Page weight grows linearly with months of data because the full JSON is inlined via `__ALL_DATA__` substitution. Fine through several years; revisit if the file gets large.

## Documentation

`docs/` is the canonical place for product requirements, design notes, data model, seed-data spec, UX review, and implementation plans. When making non-trivial changes, check there first for existing decisions and update the relevant doc rather than letting the code and the spec drift.

| File | Purpose |
|------|---------|
| `docs/requirements.md` | Vision, personas, JTBD, F-* / NF-* requirements (stable IDs), phased scope |
| `docs/design.md` | Architecture, adapter pattern, event-driven pipeline, design system (§10.7), Vercel + Railway + Neon topology |
| `docs/datamodel.md` | DDL, polymorphic GeographicArea, MarketSnapshot + Phase, MarketSignal event log, alert tables, ER diagram, representative queries |
| `docs/seed-data.md` | The 7 seed cities + 3 priority high schools (Foothill HS Pleasanton, Fremont HS Sunnyvale, Dublin HS Dublin) with CDS codes, district mappings, naming-hazard notes |
| `docs/ux-review.md` | First UX review (Mobbin / Built for Mars / UserOnboard rubric) — drives F-NAV, F-DATA, F-MON, NF-UX requirements |
| `docs/implementation-plan.md` | Per-phase deliverables, exit criteria, decisions log, risk register, agent-team work allocation |
| `.env.example` / `.env` | Environment template + local secrets (`.env` gitignored) |
