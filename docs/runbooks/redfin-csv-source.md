# Runbook: Redfin Data Center monthly CSV source

> Status: Phase 0 · Owner: Data ingestion track
> Adapter: `packages/adapters/redfin_csv.py`
> Workflow: `.github/workflows/monthly-ingest.yml`
>
> **2026-05-12 — Source change.** Redfin retired the public weekly file
> (`weekly_housing_market_data_most_recent.tsv000.gz` returns HTTP 403 from
> S3). We now consume the monthly per-city tracker (`city_market_tracker.tsv000.gz`,
> ~991 MB compressed, streamed inline). Cadence shifted weekly → monthly;
> `as_of_period` in the snapshot file now carries `YYYY-MM` rather than
> `YYYY-Www`. `SCHEMA_VERSION` bumped 1 → 2.

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
https://redfin-public-data.s3-us-west-2.amazonaws.com/redfin_market_tracker/city_market_tracker.tsv000.gz
```

That URL is "the all-time per-city monthly aggregate" — the file is
overwritten ~once a month with the latest published data. The compressed
file is **~991 MB** (5–8 GB decompressed); the adapter streams it via
`requests.get(stream=True)` + `gzip.GzipFile`, never holding the whole
thing in memory. The streaming filter pass takes ~30 s on a US-West runner.

Our cron runs day 8 of every month at 18:00 UTC (`0 18 8 * *`) — Redfin
typically refreshes within the first week, day 8 gives a buffer.

## File format

- TSV (tab-separated), gzip-compressed in transport.
- One row per (region × property_type × period_begin). `PERIOD_DURATION` = 30
  days for the city tracker; `PERIOD_BEGIN`/`PERIOD_END` mark the calendar
  month.
- Header is fully **double-quoted, ALL_CAPS** — `csv.DictReader` strips the
  quotes; the adapter additionally `_strip_quotes()` as belt-and-suspenders.
- For Bay Area city-level work we filter:
  - `REGION_TYPE == 'place'`
  - `REGION == "<City>, CA"` (e.g. `"Fremont, CA"`)
  - `PROPERTY_TYPE == 'All Residential'` (the top-level summary; SFH/condo
    splits live under `"Single Family Residential"` (id=6) and `"Condo/Co-op"`
    (id=3), to be consumed when we add `BY_PROPERTY_TYPE` capability in Phase 2)
- Numeric columns can carry blanks, `-`, `NA`, `N/A`, dollar signs, and percent
  signs — the adapter normalizes all of these via `_parse_decimal`.

Columns we currently consume (others ignored, schema is forward-compatible):

| Redfin column | Capability | Unit |
|---|---|---|
| `MEDIAN_SALE_PRICE` | `MEDIAN_PRICE` | USD |
| `MEDIAN_PPSF` | `PPSF` | USD/sqft |
| `MEDIAN_DOM` | `DOM` | days |
| `AVG_SALE_TO_LIST` | `SALE_TO_LIST` | ratio |
| `HOMES_SOLD` | `HOMES_SOLD` (also = sample_size) | count |
| `INVENTORY` | `INVENTORY` | count |
| `NEW_LISTINGS` | `NEW_LISTINGS` | count |
| `MONTHS_OF_SUPPLY` | `MONTHS_OF_SUPPLY` | months |
| `PRICE_DROPS` | `PCT_PRICE_DROPS` | pct |

## Bronze immutability

The adapter caches the **filtered** single row (header + 1 data row, ~1 KB)
per city at:

```
data/bronze/redfin/{YYYY-MM}/{slug}.tsv
```

Per Phase 0 deliverables, this file is **never** mutated. Re-running the
adapter for the same `(month, slug)` is a no-op for Bronze. If we need to
re-derive (e.g. Redfin republished with a corrected value), delete the
Bronze file and re-run.

**Why filtered, not raw:** the upstream file is ~991 MB compressed.
Caching it whole would balloon git history; caching the filtered slice is
~1 KB per (month × city) and keeps the audit trail useful. The filter
logic is pure and re-derivable, so caching the *result* of the filter is
sufficient for reproducibility.

Storage discipline: keep Bronze in git for now (Phase 0 has tiny volumes
— ~1 KB / month / city × 7 cities). When the cache outgrows reasonable
git limits, move it to R2 (per `docs/design.md` §9.1) and replace the
local cache with a prefixed S3 URL.

## Per-city seed mapping

The 7 seed cities and their Redfin region names live in
`packages/adapters/redfin_csv.py::SEED_CITIES`. The mapping is verified
against `legacy/scrape.py::CITIES` (which the prototype used). If a city's
Redfin label changes (rename, missing diacritic, etc.), update only the
`redfin_region_name` field — the product slug must stay stable.

| Slug | Redfin region | Verified |
|---|---|---|
| dublin | `Dublin, CA` | ✓ 2026-05-12 (first ingest, March 2026 data) |
| pleasanton | `Pleasanton, CA` | ✓ 2026-05-12 |
| fremont | `Fremont, CA` | ✓ 2026-05-12 |
| milpitas | `Milpitas, CA` | ✓ 2026-05-12 |
| sunnyvale | `Sunnyvale, CA` | ✓ 2026-05-12 |
| mountain-view | `Mountain View, CA` | ✓ 2026-05-12 |
| campbell | `Campbell, CA` | ✓ 2026-05-12 |

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
