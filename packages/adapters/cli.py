"""CLI entry point: `python -m adapters.cli redfin --month current`.

Phase 0 sequencing (per `docs/implementation-plan.md`, updated 2026-05-12 to
reflect Redfin's retirement of the public weekly file):

  1. Resolve the target month (`current`, `previous`, or explicit `YYYY-MM`).
  2. Stream Redfin's `city_market_tracker.tsv000.gz` ONCE, filtering inline
     to the 7 seed cities × `PROPERTY_TYPE='All Residential'`.
  3. Aggregate into a `SnapshotFile` and write `data/YYYY-MM-DD.json`
     (filename date == today UTC).
  4. Update `data/sources.json` (read by the status-page generator) with the
     adapter's last-fetch metadata.

The adapter handles per-city failures in isolation per NF-REL-02 — one bad
city does not abort the whole run. Cities that fail land in sources.json
with status='error' and are omitted from the snapshot file. CI fails the
run (non-zero exit) only if zero cities succeeded.

Re cadence: "current" resolves to the **previous** calendar month — Redfin
publishes a given month's data in the first half of the following month, so
asking for "this month" early in the month would fail with no data.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from domain.period import Month
from domain.snapshot import (
    SCHEMA_VERSION,
    CitySnapshot,
    DataQuality,
    FreshnessTier,
    MetricsBlock,
    SnapshotFile,
)

from ._base import Capability, MetricValue, RawSnapshot
from .redfin_csv import (
    SEED_CITIES,
    RedfinCsvAdapter,
    city_county,
    city_display_name,
)

log = logging.getLogger(__name__)


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_ROOT = REPO_ROOT / "data"
DEFAULT_SOURCES_PATH = DEFAULT_DATA_ROOT / "sources.json"


# ── Snapshot assembly ───────────────────────────────────────────────────────


def _metric_decimal(
    metrics: dict[Capability, MetricValue], cap: Capability
) -> Decimal | None:
    mv = metrics.get(cap)
    if mv is None or mv.value is None:
        return None
    return Decimal(mv.value) if not isinstance(mv.value, Decimal) else mv.value


def _metric_int(metrics: dict[Capability, MetricValue], cap: Capability) -> int | None:
    mv = metrics.get(cap)
    if mv is None or mv.value is None:
        return None
    return int(mv.value)


def _to_metrics_block(metrics: dict[Capability, MetricValue]) -> MetricsBlock:
    return MetricsBlock(
        median_price=_metric_decimal(metrics, Capability.MEDIAN_PRICE),
        median_ppsf=_metric_decimal(metrics, Capability.PPSF),
        dom=_metric_int(metrics, Capability.DOM),
        sale_to_list=_metric_decimal(metrics, Capability.SALE_TO_LIST),
        homes_sold=_metric_int(metrics, Capability.HOMES_SOLD),
        active_listings=_metric_int(metrics, Capability.INVENTORY),
        new_listings=_metric_int(metrics, Capability.NEW_LISTINGS),
        months_of_supply=_metric_decimal(metrics, Capability.MONTHS_OF_SUPPLY),
        pct_with_price_drops=_metric_decimal(metrics, Capability.PCT_PRICE_DROPS),
    )


def _confidence_for(snapshot: RawSnapshot) -> int:
    """Phase 0 placeholder confidence formula.

    Real `packages/finance/confidence.py` arrives in Phase 1 (per implementation
    plan) and will replace this. We compute a stub here so every record has a
    value (NF-DAT-01 requires it). Logic:
      - start at 90 (Redfin is a high-quality source)
      - subtract 10 if homes_sold sample is < 30 (the design.md §5.2 high-conf
        threshold for median_sale_price)
      - subtract 10 if median_price is missing entirely
    """
    score = 90
    homes_sold = _metric_int(snapshot.metrics, Capability.HOMES_SOLD) or 0
    if homes_sold < 30:
        score -= 10
    if _metric_decimal(snapshot.metrics, Capability.MEDIAN_PRICE) is None:
        score -= 10
    return max(0, min(100, score))


def _to_city_snapshot(snapshot: RawSnapshot) -> CitySnapshot:
    period = snapshot.period
    assert isinstance(period, Month)
    sources = [f"{snapshot.source}:{period}"]
    return CitySnapshot(
        slug=snapshot.area_slug,
        name=city_display_name(snapshot.area_slug),
        county=city_county(snapshot.area_slug),
        metro="bay-area",
        sfh=_to_metrics_block(snapshot.metrics),
        condo=None,  # Per design.md §10.7.6 — never fake condo data.
        data_quality=DataQuality(
            sources=sources,
            as_of=snapshot.source_published_at.date(),
            confidence=_confidence_for(snapshot),
            freshness_tier=FreshnessTier.MONTHLY,
        ),
    )


# ── sources.json — fed to the status-page generator ─────────────────────────


def _load_sources_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"schema_version": 1, "sources": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def _update_sources_json(
    path: Path,
    *,
    source_name: str,
    last_run_at: datetime,
    successful_slugs: list[str],
    failed: dict[str, str],
    snapshot_file: Path | None,
) -> None:
    payload = _load_sources_json(path)
    sources = payload.setdefault("sources", {})
    sources[source_name] = {
        "name": source_name,
        "last_run_at": last_run_at.isoformat(),
        "status": (
            "ok"
            if successful_slugs and not failed
            else ("partial" if successful_slugs else "error")
        ),
        "successful_areas": sorted(successful_slugs),
        "failed_areas": dict(sorted(failed.items())),
        "snapshot_file": (
            str(snapshot_file.relative_to(path.parent.parent))
            if snapshot_file is not None
            else None
        ),
        "freshness_tier": "monthly",
        "license": "attribution",
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


# ── Run orchestration ───────────────────────────────────────────────────────


def _resolve_month(arg: str, today: date | None = None) -> Month:
    today = today or datetime.now(tz=UTC).date()
    if arg == "current":
        # Redfin publishes month M's data in the first half of M+1, so "current"
        # for our purposes is the *previous* calendar month.
        return Month.from_date(today).previous()
    if arg == "previous":
        return Month.from_date(today).previous()
    return Month.parse(arg)


def run_redfin(
    month_arg: str,
    *,
    data_root: Path = DEFAULT_DATA_ROOT,
    sources_path: Path = DEFAULT_SOURCES_PATH,
    output_path: Path | None = None,
    adapter: RedfinCsvAdapter | None = None,
    today: date | None = None,
) -> Path:
    """Stream the Redfin city tracker once, fetch all 7 seed cities, write
    the snapshot file and update sources.json. Returns the snapshot file
    path on success.

    Raises `RuntimeError` if zero cities succeeded (CI gate)."""
    today = today or datetime.now(tz=UTC).date()
    month = _resolve_month(month_arg, today=today)
    log.info("Redfin ingest: target month %s, today %s", month, today)

    adapter = adapter or RedfinCsvAdapter(data_root=data_root)

    # ONE streaming pass for all 7 cities — much cheaper than 7 fetches.
    successful: list[CitySnapshot] = []
    failed: dict[str, str] = {}
    try:
        raw_by_slug = adapter.fetch_all_seed_cities(month)
    except Exception as e:  # network / parse failure on the whole run
        log.error("Streaming Redfin fetch failed entirely: %s", e)
        failed = {cfg["slug"]: f"{type(e).__name__}: {e}" for cfg in SEED_CITIES}
        raw_by_slug = {}

    for cfg in SEED_CITIES:
        slug = cfg["slug"]
        if slug not in raw_by_slug:
            if slug not in failed:
                failed[slug] = "ParseError: no row matched in streaming pass"
            continue
        try:
            successful.append(_to_city_snapshot(raw_by_slug[slug]))
        except Exception as e:
            log.warning("Snapshot assembly failure for %s: %s", slug, e)
            failed[slug] = f"{type(e).__name__}: {e}"

    if not successful:
        # Still update sources.json so the status page reflects the failure.
        _update_sources_json(
            sources_path,
            source_name=adapter.name,
            last_run_at=datetime.now(tz=UTC),
            successful_slugs=[],
            failed=failed,
            snapshot_file=None,
        )
        raise RuntimeError(
            f"Redfin ingest produced 0 successful cities; failures: {failed!r}"
        )

    snap = SnapshotFile(
        schema_version=SCHEMA_VERSION,
        as_of_period=str(month),
        scraped_at=datetime.now(tz=UTC),
        cities=successful,
    )

    output_path = output_path or (data_root / f"{today.isoformat()}.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(snap.model_dump_json(indent=2) + "\n", encoding="utf-8")
    log.info(
        "Wrote %s with %d cities (failed: %d)",
        output_path,
        len(successful),
        len(failed),
    )

    _update_sources_json(
        sources_path,
        source_name=adapter.name,
        last_run_at=datetime.now(tz=UTC),
        successful_slugs=[c.slug for c in successful],
        failed=failed,
        snapshot_file=output_path,
    )
    return output_path


# ── argparse plumbing ───────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="adapters.cli",
        description="Run a Phase 0 adapter and write a snapshot file.",
    )
    sub = parser.add_subparsers(dest="adapter", required=True)

    redfin = sub.add_parser(
        "redfin", help="Run the Redfin Data Center monthly CSV adapter."
    )
    redfin.add_argument(
        "--month",
        default="current",
        help=(
            "Calendar month: ISO `YYYY-MM`, the literal `current` "
            "(= previous calendar month — Redfin lags ~1 month), or `previous`. "
            "Default: current."
        ),
    )
    redfin.add_argument(
        "--data-root",
        type=Path,
        default=DEFAULT_DATA_ROOT,
        help="Where to write Bronze + the snapshot file. Default: ./data",
    )
    redfin.add_argument(
        "--sources-path",
        type=Path,
        default=DEFAULT_SOURCES_PATH,
        help="Path to sources.json (status-page input). Default: ./data/sources.json",
    )
    redfin.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output snapshot file. Default: ./data/<today-utc>.json",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )
    args = build_parser().parse_args(argv)
    if args.adapter == "redfin":
        try:
            run_redfin(
                args.month,
                data_root=args.data_root,
                sources_path=args.sources_path,
                output_path=args.output,
            )
        except RuntimeError as e:
            log.error(str(e))
            return 1
        return 0
    raise SystemExit(f"Unknown adapter: {args.adapter}")


if __name__ == "__main__":
    sys.exit(main())
