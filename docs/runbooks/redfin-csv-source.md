# Runbook: Redfin Data Center weekly CSV source

> Status: Phase 0 · Owner: Data ingestion track
> Adapter: `packages/adapters/redfin_csv.py`
> Workflow: `.github/workflows/weekly-ingest.yml`

## License

**Personal / non-commercial use confirmed by user 2026-05-11.** Redfin Data
Center's published Terms of Use permit personal, non-commercial use of the
weekly housing market CSVs with attribution. Pre-monetization (current) we
operate under that. The moment the product gates anything behind a paid tier,
re-confirm with Redfin (and Phase 6's MLS conversation supersedes this anyway).

Required attribution string (rendered on `/sources` in Phase 2):

> Source: Redfin Data Center (redfin.com/news/data-center)

The `data_source` row that lands in Postgres in Phase 2 carries this license
string in its `attribution` column.

## URL pattern

```
https://redfin-public-data.s3-us-west-2.amazonaws.com/redfin_market_tracker/weekly_housing_market_data_most_recent.tsv000.gz
```

That URL is "the most recent weekly snapshot" — the file is overwritten every
Thursday around 1pm ET (5pm UTC). Our cron runs Thu 18:00 UTC to give Redfin
a one-hour publishing buffer.

Historical files exist at parallel paths (`weekly_housing_market_data.tsv000.gz`
without `_most_recent`); Phase 0 doesn't need them.

## File format

- TSV (tab-separated), gzip-compressed in transport.
- One row per (region × property_type × period_end). Each row covers a 4-week
  rolling window — `period_begin` and `period_end` define the window.
- For Bay Area city-level work we filter:
  - `region_type == 'place'`
  - `region == "<City>, CA"` (e.g. `"Fremont, CA"`)
  - `property_type in {"All Residential", "All Homes", ""}` (the top-level
    summary; SFH/condo splits live under `"Single Family Residential"` and
    `"Condo/Co-op"` respectively, which we'll start consuming when we add
    `BY_PROPERTY_TYPE` capability in Phase 2)
- Numeric columns can carry blanks, `-`, `N/A`, dollar signs, and percent
  signs — the adapter normalizes all of these via `_parse_decimal`.

Columns we currently consume (others ignored, schema is forward-compatible):

| Redfin column | Capability | Unit |
|---|---|---|
| `median_sale_price` | `MEDIAN_PRICE` | USD |
| `median_ppsf` | `PPSF` | USD/sqft |
| `median_days_on_market` | `DOM` | days |
| `average_sale_to_list_ratio` | `SALE_TO_LIST` | ratio |
| `homes_sold` | `HOMES_SOLD` (also = sample_size) | count |
| `active_listings` | `INVENTORY` | count |
| `new_listings` | `NEW_LISTINGS` | count |
| `months_of_supply` | `MONTHS_OF_SUPPLY` | months |
| `percent_homes_sold_with_price_drops` | `PCT_PRICE_DROPS` | pct |

## Bronze immutability

The adapter caches the raw decoded TSV at:

```
data/bronze/redfin/{iso_week}/{slug}.tsv
```

Per Phase 0 deliverables, this file is **never** mutated. Re-running the
adapter for the same `(week, slug)` is a no-op for Bronze and writes the
parsed `RawSnapshot` from the cached file. If we need to re-fetch (Redfin
fixed a bad row), delete the Bronze file by hand and re-run.

Storage discipline: keep Bronze in git for now (Phase 0 has tiny volumes —
< 1 MB / week / city × 7 cities). When `data/bronze/` exceeds ~50 MB total,
move it to R2 (per `docs/design.md` §9.1) and replace the local cache with a
prefixed S3 URL.

## Per-city seed mapping

The 7 seed cities and their Redfin region names live in
`packages/adapters/redfin_csv.py::SEED_CITIES`. The mapping is verified
against `legacy/scrape.py::CITIES` (which the prototype used). If a city's
Redfin label changes (rename, missing diacritic, etc.), update only the
`redfin_region_name` field — the product slug must stay stable.

| Slug | Redfin region | Verified |
|---|---|---|
| dublin | `Dublin, CA` | TODO — first cron run |
| pleasanton | `Pleasanton, CA` | TODO |
| fremont | `Fremont, CA` | TODO |
| milpitas | `Milpitas, CA` | TODO |
| sunnyvale | `Sunnyvale, CA` | TODO |
| mountain-view | `Mountain View, CA` | TODO |
| campbell | `Campbell, CA` | TODO |

After the first successful weekly run, flip the TODOs to a checkmark + the
ISO week we confirmed in. If a city fails to match, the adapter raises
`ParseError("No Redfin rows matched region=...")` and the CLI marks that
city as failed in `data/sources.json`; the rest of the run continues.

## Breakage playbook

The adapter is HTML-fragile by design — Redfin's CSV format changes ~yearly.
When the weekly cron fails:

1. **Look at the failure on the status page** (`status/index.html` or
   `data/sources.json`). The `failed_areas` map carries the exception class
   + message per slug.
2. **Pull the Bronze file**:
   ```
   data/bronze/redfin/{week}/{slug}.tsv
   ```
   This was written before the parse, so it's the unmodified Redfin payload.
3. **Diff the header row** against `_COLUMN_TO_METRIC` in `redfin_csv.py`.
   Three common breakage modes:
   - Renamed column → update the key in `_COLUMN_TO_METRIC`.
   - Removed column → mark the affected `Capability` as None for that adapter
     (or drop it from `capabilities`).
   - Added column → no-op for us (extra columns are ignored).
4. **Region label changed** (e.g. Redfin moved to `"Fremont, California"`):
   update the `redfin_region_name` for the affected city in `SEED_CITIES`.
5. **HTTP 403 / blocked**: re-check `User-Agent` and the URL pattern.
   Redfin's S3 bucket is public; a 403 usually means the path moved.
6. **All 7 cities fail in the same way** = format change. Treat as a release
   blocker — the entire weekly snapshot is stale until fixed.
7. **Re-run locally** before merging the fix:
   ```
   make ingest
   ```
   The CLI is idempotent — Bronze cached files are reused, so iteration is
   cheap.

## Tests

`packages/adapters/tests/test_redfin_csv.py` uses the `responses` library to
intercept HTTP and tiny TSV fixtures in `fixtures/`. No real network calls.
Add a new fixture when Redfin changes the format — it documents the change
better than a comment.

## Future work

- Add SFH / condo splits by consuming the `Single Family Residential` and
  `Condo/Co-op` rows separately — this lights up the `BY_PROPERTY_TYPE`
  capability and removes the Phase 0 limitation that `condo` is always null.
- Move Bronze to R2 once total size exceeds ~50 MB.
- Phase 2: replace the CLI orchestrator with the Dagster `weekly_market`
  asset; the adapter itself stays unchanged.
