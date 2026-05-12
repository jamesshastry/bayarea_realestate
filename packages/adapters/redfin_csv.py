"""Redfin Data Center monthly market-data adapter.

Redfin publishes [the City Market Tracker](https://www.redfin.com/news/data-center/)
as a monthly aggregate per city × property type. The previous weekly file
(`weekly_housing_market_data_most_recent.tsv000.gz`) was retired from the
public bucket; the live source is now the ~1 GB monthly tracker.

This adapter:
  1. **Streams** the gzip TSV directly from Redfin's public S3 bucket, gunzips
     line-by-line (the file is ~1 GB compressed; loading it whole would OOM
     a GitHub Actions runner).
  2. Filters in one pass to the 7 seed cities + `PROPERTY_TYPE='All Residential'`,
     keeping only the requested calendar month's row per city.
  3. Caches the **filtered** TSV slice (a few KB) to
     `data/bronze/redfin/{YYYY-MM}/{slug}.tsv` — Bronze immutability per
     `docs/implementation-plan.md` Phase 0. We don't cache the full upstream
     file because the storage / GC cost isn't worth it.
  4. Returns one `RawSnapshot` per city per call.

`freshness_tier` for everything we emit is `monthly`. License: personal /
non-commercial use confirmed by user 2026-05-11 — see
`docs/runbooks/redfin-csv-source.md`.
"""

from __future__ import annotations

import csv
import gzip
import io
import logging
from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

import requests
from domain.geographic_area import GeographicArea
from domain.period import Month, Period

from ._base import (
    Capability,
    FetchError,
    License,
    MetricValue,
    ParseError,
    RawSnapshot,
)

log = logging.getLogger(__name__)


# ── Constants ───────────────────────────────────────────────────────────────

# Redfin's monthly per-city tracker. ~991 MB compressed as of 2026-05.
DEFAULT_REDFIN_CITY_URL = (
    "https://redfin-public-data.s3-us-west-2.amazonaws.com/"
    "redfin_market_tracker/city_market_tracker.tsv000.gz"
)

# 7 seed cities per `docs/seed-data.md` §2.1.
SEED_CITIES: tuple[dict[str, str], ...] = (
    # Alameda County
    {
        "slug": "dublin",
        "name": "Dublin",
        "county": "Alameda",
        "redfin_region_name": "Dublin, CA",
    },
    {
        "slug": "pleasanton",
        "name": "Pleasanton",
        "county": "Alameda",
        "redfin_region_name": "Pleasanton, CA",
    },
    {
        "slug": "fremont",
        "name": "Fremont",
        "county": "Alameda",
        "redfin_region_name": "Fremont, CA",
    },
    # Santa Clara County
    {
        "slug": "milpitas",
        "name": "Milpitas",
        "county": "Santa Clara",
        "redfin_region_name": "Milpitas, CA",
    },
    {
        "slug": "sunnyvale",
        "name": "Sunnyvale",
        "county": "Santa Clara",
        "redfin_region_name": "Sunnyvale, CA",
    },
    {
        "slug": "mountain-view",
        "name": "Mountain View",
        "county": "Santa Clara",
        "redfin_region_name": "Mountain View, CA",
    },
    {
        "slug": "campbell",
        "name": "Campbell",
        "county": "Santa Clara",
        "redfin_region_name": "Campbell, CA",
    },
)


# Map from Redfin TSV column name (ALL_CAPS in the city tracker) → (Capability, unit).
# Adding a column means adding it here and (if it's a new capability) to the
# Capability enum.
_COLUMN_TO_METRIC: Mapping[str, tuple[Capability, str]] = {
    "MEDIAN_SALE_PRICE": (Capability.MEDIAN_PRICE, "USD"),
    "MEDIAN_PPSF": (Capability.PPSF, "USD/sqft"),
    "MEDIAN_DOM": (Capability.DOM, "days"),
    "AVG_SALE_TO_LIST": (Capability.SALE_TO_LIST, "ratio"),
    "HOMES_SOLD": (Capability.HOMES_SOLD, "count"),
    "INVENTORY": (Capability.INVENTORY, "count"),
    "NEW_LISTINGS": (Capability.NEW_LISTINGS, "count"),
    "MONTHS_OF_SUPPLY": (Capability.MONTHS_OF_SUPPLY, "months"),
    "PRICE_DROPS": (Capability.PCT_PRICE_DROPS, "pct"),
}

# Filter constants (match Redfin's exact strings — quotes are stripped per row)
_TARGET_REGION_TYPE = "place"
_TARGET_PROPERTY_TYPE = "All Residential"


# ── Helpers ─────────────────────────────────────────────────────────────────


def _parse_decimal(raw: str | None) -> Decimal | None:
    """Permissive: accept dollar signs, percents, commas. Returns None for
    blanks or sentinel values Redfin uses ('', '-', 'N/A', 'NA')."""
    if raw is None:
        return None
    s = raw.strip().strip('"')
    if s == "" or s in {"-", "N/A", "NA", "null", "None"}:
        return None
    s = s.replace("$", "").replace(",", "").replace("%", "").strip()
    try:
        return Decimal(s)
    except (InvalidOperation, ValueError) as e:
        raise ParseError(f"Could not parse decimal from {raw!r}: {e}") from e


def _parse_int(raw: str | None) -> int | None:
    d = _parse_decimal(raw)
    if d is None:
        return None
    # Redfin sometimes reports counts as floats (e.g. "142.0"); truncate.
    return int(d)


def _parse_iso_date(raw: str) -> date:
    return date.fromisoformat(raw.strip().strip('"'))


def _strip_quotes(s: str) -> str:
    return s.strip().strip('"')


def _bronze_path(data_root: Path, period: Month, slug: str) -> Path:
    """`data/bronze/redfin/{YYYY-MM}/{slug}.tsv` per Phase 0 contract."""
    return data_root / "bronze" / "redfin" / str(period) / f"{slug}.tsv"


# ── Adapter ─────────────────────────────────────────────────────────────────


def _default_capabilities() -> set[Capability]:
    return {capability for capability, _ in _COLUMN_TO_METRIC.values()}


def _default_data_root() -> Path:
    return Path(__file__).resolve().parents[2] / "data"


def _default_stream_factory(url: str, timeout: int) -> Iterator[bytes]:
    """Open the URL, gunzip on the fly, yield raw decompressed bytes in chunks.

    The default impl uses `requests.get(stream=True)` + `gzip.GzipFile`.
    Tests inject a different factory that yields from a local fixture file.
    """
    response = requests.get(
        url,
        stream=True,
        timeout=timeout,
        # AWS S3 sometimes serves 403 to clients with no User-Agent; be polite.
        headers={
            "User-Agent": "bayre-realestate/0.1 (+https://github.com/jamesshastry/bayarea_realestate)"
        },
    )
    response.raise_for_status()
    gz = gzip.GzipFile(fileobj=response.raw)
    while True:
        chunk = gz.read(64 * 1024)
        if not chunk:
            break
        yield chunk


# Type for the streaming factory: takes (url, timeout) → iterator of bytes.
StreamFactory = Callable[[str, int], Iterator[bytes]]


@dataclass
class RedfinCsvAdapter:
    """Implements `DataSourceAdapter` for Redfin Data Center monthly CSVs."""

    name: str = "redfin_csv"
    license: License = "attribution"
    capabilities: set[Capability] = field(default_factory=_default_capabilities)
    data_root: Path = field(default_factory=_default_data_root)
    url: str = DEFAULT_REDFIN_CITY_URL
    timeout_seconds: int = 600  # 10 minutes — the file is ~1 GB compressed
    # Test injection — yields decompressed TSV bytes in chunks.
    stream_factory: StreamFactory = field(default=_default_stream_factory)

    # ── Protocol methods ─────────────────────────────────────────────────

    def can_fetch(self, area: GeographicArea, capability: Capability) -> bool:
        if capability not in self.capabilities:
            return False
        return any(cfg["slug"] == area.slug for cfg in SEED_CITIES)

    def reliability(self, capability: Capability) -> float:
        """Rough reliability priors per `docs/design.md` §3.4."""
        high = {
            Capability.MEDIAN_PRICE,
            Capability.PPSF,
            Capability.DOM,
            Capability.SALE_TO_LIST,
            Capability.HOMES_SOLD,
            Capability.INVENTORY,
            Capability.NEW_LISTINGS,
        }
        if capability in high:
            return 0.95
        if capability in self.capabilities:
            return 0.85
        return 0.0

    def fetch(self, area: GeographicArea, period: Period) -> RawSnapshot:
        """Single-city fetch.

        The single-city signature satisfies the Protocol; if you're fetching
        multiple seed cities, call `fetch_all_seed_cities` instead — it streams
        once and emits N RawSnapshots, which is *much* cheaper than N full
        downloads of the 1 GB tracker.
        """
        if not isinstance(period, Month):
            raise FetchError(
                f"Redfin CSV adapter is monthly-tier only; got period kind={period.kind!r}"
            )
        cfg = self._city_config(area.slug)
        snapshots = self._stream_and_filter([cfg], period)
        if cfg["slug"] not in snapshots:
            raise ParseError(
                f"No Redfin row matched region={cfg['redfin_region_name']!r} for {period}"
            )
        return snapshots[cfg["slug"]]

    def fetch_all_seed_cities(self, period: Period) -> dict[str, RawSnapshot]:
        """One streaming pass → one RawSnapshot per seed city.

        Returns a dict keyed by slug. Cities that didn't match (e.g. Redfin
        hasn't published the requested month yet for that city) are *omitted*
        — the caller logs them as failures.
        """
        if not isinstance(period, Month):
            raise FetchError(
                f"Redfin CSV adapter is monthly-tier only; got period kind={period.kind!r}"
            )
        return self._stream_and_filter(list(SEED_CITIES), period)

    # ── Internals ────────────────────────────────────────────────────────

    def _city_config(self, slug: str) -> dict[str, str]:
        for cfg in SEED_CITIES:
            if cfg["slug"] == slug:
                return cfg
        raise FetchError(f"No Redfin region mapping for slug {slug!r}")

    def _stream_and_filter(
        self,
        target_cities: list[dict[str, str]],
        period: Month,
    ) -> dict[str, RawSnapshot]:
        """Streaming filter: scan the gunzipped TSV once, keep only rows
        matching one of `target_cities` AND `PROPERTY_TYPE='All Residential'`,
        retain the row whose `PERIOD_BEGIN` matches `period`."""

        target_regions = {cfg["redfin_region_name"]: cfg for cfg in target_cities}
        target_first_day = period.first_day().isoformat()

        # The streaming TSV reader: bytes → text lines → DictReader
        bytes_iter = self.stream_factory(self.url, self.timeout_seconds)
        text_iter = _bytes_to_text_lines(bytes_iter)
        reader = csv.DictReader(text_iter, delimiter="\t")
        if reader.fieldnames is None:
            raise ParseError("Redfin TSV has no header row")
        # Normalize fieldnames (strip surrounding quotes Redfin emits).
        reader.fieldnames = [_strip_quotes(f) for f in reader.fieldnames]
        required = {
            "REGION_TYPE",
            "REGION",
            "PROPERTY_TYPE",
            "PERIOD_BEGIN",
            "PERIOD_END",
        }
        missing = required - set(reader.fieldnames)
        if missing:
            raise ParseError(
                f"Redfin TSV missing required columns: {sorted(missing)}; "
                f"got {reader.fieldnames!r}"
            )

        # Best-row-per-slug. We keep the row whose PERIOD_BEGIN equals the
        # requested month's first day; otherwise the most recent on or before.
        # Most-recent fallback is chosen by max(PERIOD_BEGIN) at the end.
        candidates: dict[str, dict[str, str]] = {}
        fallback_candidates: dict[str, list[dict[str, str]]] = {
            cfg["slug"]: [] for cfg in target_cities
        }

        for row in reader:
            if _strip_quotes(row.get("REGION_TYPE", "")) != _TARGET_REGION_TYPE:
                continue
            region = _strip_quotes(row.get("REGION", ""))
            cfg = target_regions.get(region)
            if cfg is None:
                continue
            if _strip_quotes(row.get("PROPERTY_TYPE", "")) != _TARGET_PROPERTY_TYPE:
                continue
            period_begin = _strip_quotes(row.get("PERIOD_BEGIN", ""))
            if period_begin == target_first_day:
                candidates[cfg["slug"]] = row
            else:
                fallback_candidates[cfg["slug"]].append(row)

        # For any city without an exact-month match, pick the latest available.
        for slug, rows in fallback_candidates.items():
            if slug in candidates or not rows:
                continue
            best = max(rows, key=lambda r: _parse_iso_date(r["PERIOD_BEGIN"]))
            log.warning(
                "Redfin has no row for %s in %s; using latest available (%s).",
                slug,
                period,
                _strip_quotes(best["PERIOD_BEGIN"]),
            )
            candidates[slug] = best

        # Materialize → RawSnapshot per city.
        now = datetime.now(tz=UTC)
        out: dict[str, RawSnapshot] = {}
        for slug, row in candidates.items():
            cfg = next(c for c in target_cities if c["slug"] == slug)
            bronze_path = self._write_bronze(row, period, slug)
            out[slug] = RawSnapshot(
                area_slug=slug,
                period=period,
                metrics=self._row_to_metrics(row),
                source=self.name,
                fetched_at=now,
                source_published_at=datetime.combine(
                    _parse_iso_date(row["PERIOD_END"]),
                    datetime.min.time(),
                    tzinfo=UTC,
                ),
                bronze_path=str(bronze_path.relative_to(self.data_root.parent)),
            )
        return out

    def _write_bronze(
        self,
        row: Mapping[str, str],
        period: Month,
        slug: str,
    ) -> Path:
        """Write the filtered single row as TSV to Bronze.

        Bronze immutability: write-if-not-exists. The same (period, city)
        should never be re-fetched into a different file; if it already
        exists, trust it. We cache only the filtered slice (single row, not
        the 1 GB upstream file) — the storage cost of the raw isn't worth it
        when the filter logic is deterministic and re-derivable.
        """
        path = _bronze_path(self.data_root, period, slug)
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            buf = io.StringIO()
            writer = csv.DictWriter(buf, fieldnames=list(row.keys()), delimiter="\t")
            writer.writeheader()
            writer.writerow(dict(row))
            path.write_text(buf.getvalue(), encoding="utf-8")
        return path

    def _row_to_metrics(self, row: Mapping[str, str]) -> dict[Capability, MetricValue]:
        sample_size = _parse_int(row.get("HOMES_SOLD"))
        out: dict[Capability, MetricValue] = {}
        for column, (capability, unit) in _COLUMN_TO_METRIC.items():
            raw = row.get(column)
            if capability in {
                Capability.HOMES_SOLD,
                Capability.INVENTORY,
                Capability.NEW_LISTINGS,
            }:
                value: Decimal | int | None = _parse_int(raw)
            else:
                value = _parse_decimal(raw)
            out[capability] = MetricValue(value=value, sample_size=sample_size, unit=unit)  # type: ignore[arg-type]
        return out


def _bytes_to_text_lines(byte_chunks: Iterator[bytes]) -> Iterator[str]:
    """Buffer byte chunks → yield decoded UTF-8 lines (split on `\\n`).

    The csv.DictReader expects an iterable of strings; we adapt the gunzip
    chunk stream by buffering across boundaries so multi-byte UTF-8 sequences
    and partial lines aren't split mid-character or mid-line.
    """
    buf = bytearray()
    for chunk in byte_chunks:
        buf.extend(chunk)
        # Pop complete lines.
        while True:
            nl = buf.find(b"\n")
            if nl == -1:
                break
            line_bytes = bytes(buf[: nl + 1])
            del buf[: nl + 1]
            try:
                yield line_bytes.decode("utf-8")
            except UnicodeDecodeError as e:
                raise ParseError(f"UTF-8 decode failed in row: {e}") from e
    # Flush trailing line (no newline at EOF).
    if buf:
        try:
            yield bytes(buf).decode("utf-8")
        except UnicodeDecodeError as e:
            raise ParseError(f"UTF-8 decode failed at EOF: {e}") from e


# ── Module-level convenience for the CLI ────────────────────────────────────


def iter_seed_areas() -> Iterable[GeographicArea]:
    """Yield a `GeographicArea` for each seed city. Used by the CLI to drive
    the per-city loop without each city needing a real DB row in Phase 0."""
    from domain.geographic_area import GeoKind

    for cfg in SEED_CITIES:
        yield GeographicArea(kind=GeoKind.CITY, name=cfg["name"], slug=cfg["slug"])


def city_county(slug: str) -> str:
    """Look up the county for a seed city slug (Phase 0 helper)."""
    for cfg in SEED_CITIES:
        if cfg["slug"] == slug:
            return cfg["county"]
    raise KeyError(slug)


def city_display_name(slug: str) -> str:
    for cfg in SEED_CITIES:
        if cfg["slug"] == slug:
            return cfg["name"]
    raise KeyError(slug)
