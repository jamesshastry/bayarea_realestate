"""Load a Phase 0 `SnapshotFile` JSON into the `market_snapshot` Postgres table.

CLI:
    uv run python -m etl.load_snapshots <path/to/snapshot.json>
    uv run python -m etl.load_snapshots --latest         # latest data/YYYY-MM-DD.json
    uv run python -m etl.load_snapshots --latest --dry-run

Idempotent: the table's `UNIQUE (area_id, property_type, period_kind,
period_start)` constraint backs an `ON CONFLICT … DO UPDATE` upsert, so
re-loading the same file overwrites with the new values rather than
inserting duplicates.

Property-type note: Redfin's `All Residential` rollup is loaded as
`property_type = 'sfh'` to match the JSON contract (`CitySnapshot.sfh`).
TODO(phase-2): add an `'all_residential'` enum value via migration when we
ingest the per-property-type split, then route 'All Residential' there
and free 'sfh' for the actual SFH rollup.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import pathlib
import sys
from collections.abc import Iterable
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import asyncpg
from dotenv import load_dotenv

# Repo root = packages/etl/load_snapshots.py → parents[2]
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
load_dotenv(_REPO_ROOT / ".env")

# Re-import path: domain.snapshot is installed under the workspace name.
from domain.snapshot import CitySnapshot, SnapshotFile  # noqa: E402

log = logging.getLogger(__name__)


# Map an `as_of_period` string from the snapshot file → (period_kind, start, end).
def _resolve_period(as_of_period: str) -> tuple[str, date, date]:
    """`'2026-04'` → ('monthly', 2026-04-01, 2026-04-30).
    `'2026-W19'` → ('weekly', Mon 2026-05-04, Sun 2026-05-10).
    """
    if "-W" in as_of_period:
        # ISO week
        year_str, week_str = as_of_period.split("-W")
        year, week = int(year_str), int(week_str)
        monday = date.fromisocalendar(year, week, 1)
        sunday = date.fromisocalendar(year, week, 7)
        return ("weekly", monday, sunday)
    # ISO month YYYY-MM
    year, month = (int(p) for p in as_of_period.split("-"))
    first = date(year, month, 1)
    next_year, next_month = (year + 1, 1) if month == 12 else (year, month + 1)
    last = date(next_year, next_month, 1)
    # Postgres-friendly: `period_end` is INCLUSIVE in datamodel.md §6 spec.
    from datetime import timedelta

    return ("monthly", first, last - timedelta(days=1))


def _to_int(v: Any) -> int | None:
    if v is None:
        return None
    return int(v)


def _to_decimal(v: Any) -> Decimal | None:
    if v is None:
        return None
    return Decimal(str(v))


# ── Per-row builders ────────────────────────────────────────────────────────


def _row_for_city(
    city: CitySnapshot,
    *,
    period_kind: str,
    period_start: date,
    period_end: date,
    source_versions: dict[str, str],
) -> dict[str, Any] | None:
    """Build the SQL row dict for a city's `sfh` block. Returns None if there's
    no usable metric data."""
    block = city.sfh
    if block is None:
        return None

    homes_sold = _to_int(block.homes_sold) or 0
    return {
        "slug": city.slug,
        # See module docstring: `All Residential` is loaded as 'sfh' until the
        # SFH/condo split lands.
        "property_type": "sfh",
        "period_kind": period_kind,
        "period_start": period_start,
        "period_end": period_end,
        "median_sale_price": _to_decimal(block.median_price),
        "median_ppsf": _to_decimal(block.median_ppsf),
        "sale_to_list_ratio": _to_decimal(block.sale_to_list),
        "median_dom": _to_int(block.dom),
        "homes_sold": _to_int(block.homes_sold),
        "active_listings": _to_int(block.active_listings),
        "new_listings": _to_int(block.new_listings),
        "months_of_supply": _to_decimal(block.months_of_supply),
        "pct_with_price_drops": _to_decimal(block.pct_with_price_drops),
        "sample_size": homes_sold,  # NOT NULL per schema
        "confidence_score": city.data_quality.confidence,
        "source_versions": json.dumps(source_versions),
    }


# ── Upsert ──────────────────────────────────────────────────────────────────

_UPSERT_SQL = """
INSERT INTO market_snapshot (
    area_id, property_type, period_kind, period_start, period_end,
    median_sale_price, median_ppsf, sale_to_list_ratio, median_dom,
    homes_sold, active_listings, new_listings, months_of_supply,
    pct_with_price_drops, sample_size, confidence_score, source_versions,
    computed_at
)
SELECT
    ga.id,
    $2::property_type,
    $3::period_kind,
    $4::date,
    $5::date,
    $6::numeric, $7::numeric, $8::numeric, $9::int,
    $10::int, $11::int, $12::int, $13::numeric,
    $14::numeric, $15::int, $16::smallint, $17::jsonb,
    now()
FROM geographic_area ga
WHERE ga.kind = 'city' AND ga.slug = $1
ON CONFLICT (area_id, property_type, period_kind, period_start) DO UPDATE SET
    period_end           = EXCLUDED.period_end,
    median_sale_price    = EXCLUDED.median_sale_price,
    median_ppsf          = EXCLUDED.median_ppsf,
    sale_to_list_ratio   = EXCLUDED.sale_to_list_ratio,
    median_dom           = EXCLUDED.median_dom,
    homes_sold           = EXCLUDED.homes_sold,
    active_listings      = EXCLUDED.active_listings,
    new_listings         = EXCLUDED.new_listings,
    months_of_supply     = EXCLUDED.months_of_supply,
    pct_with_price_drops = EXCLUDED.pct_with_price_drops,
    sample_size          = EXCLUDED.sample_size,
    confidence_score     = EXCLUDED.confidence_score,
    source_versions      = EXCLUDED.source_versions,
    computed_at          = now()
RETURNING id;
"""


async def _execute_upsert(conn: asyncpg.Connection, row: dict[str, Any]) -> bool:
    """Run one upsert. Returns True if a row landed (i.e. the city slug
    resolved to a `geographic_area` row)."""
    inserted_id = await conn.fetchval(
        _UPSERT_SQL,
        row["slug"],
        row["property_type"],
        row["period_kind"],
        row["period_start"],
        row["period_end"],
        row["median_sale_price"],
        row["median_ppsf"],
        row["sale_to_list_ratio"],
        row["median_dom"],
        row["homes_sold"],
        row["active_listings"],
        row["new_listings"],
        row["months_of_supply"],
        row["pct_with_price_drops"],
        row["sample_size"],
        row["confidence_score"],
        row["source_versions"],
    )
    return inserted_id is not None


# ── Public entry ────────────────────────────────────────────────────────────


async def load_snapshot_file(
    path: pathlib.Path,
    *,
    dry_run: bool = False,
) -> dict[str, int]:
    """Load one snapshot file. Returns counts: `{loaded, skipped_no_match, skipped_no_data}`."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    snap = SnapshotFile.model_validate(payload)
    period_kind, period_start, period_end = _resolve_period(snap.as_of_period)

    log.info(
        "Loading %s — period %s (%s → %s), %d cities",
        path,
        snap.as_of_period,
        period_start,
        period_end,
        len(snap.cities),
    )

    rows: list[dict[str, Any]] = []
    skipped_no_data = 0
    for city in snap.cities:
        row = _row_for_city(
            city,
            period_kind=period_kind,
            period_start=period_start,
            period_end=period_end,
            source_versions={"redfin_csv": snap.as_of_period},
        )
        if row is None:
            log.warning("Skipping %s: no `sfh` block present", city.slug)
            skipped_no_data += 1
            continue
        rows.append(row)

    if dry_run:
        log.info("[dry-run] would upsert %d rows", len(rows))
        return {"loaded": 0, "skipped_no_match": 0, "skipped_no_data": skipped_no_data}

    url = os.environ.get("DATABASE_URL_DIRECT") or os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "Neither DATABASE_URL_DIRECT nor DATABASE_URL is set. "
            "ETL needs the **direct** Neon URL (or the pooled URL for short jobs)."
        )

    loaded = 0
    skipped_no_match = 0
    conn = await asyncpg.connect(url)
    try:
        async with conn.transaction():
            for row in rows:
                if await _execute_upsert(conn, row):
                    loaded += 1
                else:
                    log.warning(
                        "City slug %r not found in geographic_area; skipped",
                        row["slug"],
                    )
                    skipped_no_match += 1
    finally:
        await conn.close()

    log.info(
        "Done: loaded=%d skipped_no_match=%d skipped_no_data=%d",
        loaded,
        skipped_no_match,
        skipped_no_data,
    )
    return {
        "loaded": loaded,
        "skipped_no_match": skipped_no_match,
        "skipped_no_data": skipped_no_data,
    }


def _latest_snapshot_file(data_dir: pathlib.Path) -> pathlib.Path:
    matches: Iterable[pathlib.Path] = data_dir.glob(
        "[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9].json"
    )
    files = sorted(matches)
    if not files:
        raise FileNotFoundError(
            f"No data/YYYY-MM-DD.json files found under {data_dir}. Run `make ingest` first."
        )
    return files[-1]


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )
    p = argparse.ArgumentParser(prog="etl.load_snapshots")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument(
        "path", nargs="?", type=pathlib.Path, help="Path to a snapshot JSON file."
    )
    g.add_argument(
        "--latest",
        action="store_true",
        help="Use the latest data/YYYY-MM-DD.json under the repo data dir.",
    )
    p.add_argument(
        "--data-dir",
        type=pathlib.Path,
        default=_REPO_ROOT / "data",
        help="Where to look for --latest. Default: <repo>/data",
    )
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args(argv)

    target = _latest_snapshot_file(args.data_dir) if args.latest else args.path
    if not target.exists():
        log.error("File not found: %s", target)
        return 1

    counts = asyncio.run(load_snapshot_file(target, dry_run=args.dry_run))
    if counts["loaded"] == 0 and not args.dry_run:
        log.error("0 rows loaded — check city slugs and the `geographic_area` seed.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())


# Module-level constant exported so callers (CLI, GH Actions) can reference
# the load timestamp consistently. Kept here rather than UTC-now-at-call so
# tests can monkeypatch.
LOAD_RUN_AT: datetime = datetime.now(tz=UTC)
