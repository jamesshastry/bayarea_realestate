"""Redfin Data Center weekly market-data adapter.

Redfin publishes [Weekly Housing Market Data](https://www.redfin.com/news/data-center/)
every Thursday around 1pm ET. The file lives at a stable URL (TSV / gzip'd TSV)
and contains one row per (region x property_type x period_end). For Bay Area
work we filter to `region_type == 'place'` (city) and the 7 seed cities by
their Redfin region name.

This adapter:
  1. Downloads the weekly TSV from Redfin's public S3 bucket
     (license: personal/non-commercial use confirmed by user 2026-05-11 —
     see `docs/runbooks/redfin-csv-source.md`).
  2. Caches the raw payload to `data/bronze/redfin/{iso_week}/{slug}.tsv`
     **before** parsing — Bronze immutability per `docs/implementation-plan.md`
     Phase 0 deliverable list.
  3. Parses + filters to the requested city, returning a `RawSnapshot`.

`freshness_tier` for everything we emit is `weekly`.
"""

from __future__ import annotations

import csv
import gzip
import io
import logging
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

import requests
from domain.geographic_area import GeographicArea
from domain.period import Period, Week

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

# Redfin's public TSV. Both the "most recent" snapshot and the historical
# series live at stable paths. Phase 0 only needs the most-recent file.
DEFAULT_REDFIN_WEEKLY_URL = (
    "https://redfin-public-data.s3-us-west-2.amazonaws.com/"
    "redfin_market_tracker/weekly_housing_market_data_most_recent.tsv000.gz"
)

# 7 seed cities per `docs/seed-data.md` §2.1. Slugs are the canonical product
# slugs (`docs/seed-data.md` §2). `redfin_region_name` is the literal value
# Redfin's CSV uses in the `region` column for `region_type='place'`.
#
# TODO(verify): re-confirm `redfin_region_name` strings against an actual
# Redfin Data Center download — the city-name + ", CA" pattern is what they
# use for ZHVI and most weekly tables, but the exact string varies (some have
# "city, CA", some "City, California"). First real run with the workflow will
# surface any miss; fix here.
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


# Map from Redfin TSV column name → (Capability, unit). Adding a column means
# adding it here and (if it's a new capability) to the Capability enum.
# Numeric strings come in cleanly; we coerce in `_parse_decimal`.
_COLUMN_TO_METRIC: Mapping[str, tuple[Capability, str]] = {
    "median_sale_price": (Capability.MEDIAN_PRICE, "USD"),
    "median_ppsf": (Capability.PPSF, "USD/sqft"),
    "median_days_on_market": (Capability.DOM, "days"),
    "average_sale_to_list_ratio": (Capability.SALE_TO_LIST, "ratio"),
    "homes_sold": (Capability.HOMES_SOLD, "count"),
    "active_listings": (Capability.INVENTORY, "count"),
    "new_listings": (Capability.NEW_LISTINGS, "count"),
    "months_of_supply": (Capability.MONTHS_OF_SUPPLY, "months"),
    "percent_homes_sold_with_price_drops": (Capability.PCT_PRICE_DROPS, "pct"),
}


# ── Helpers ─────────────────────────────────────────────────────────────────


def _parse_decimal(raw: str | None) -> Decimal | None:
    """Permissive: accept dollar signs, percents, commas. Returns None for
    blanks or sentinel values Redfin uses ('', '-', 'N/A')."""
    if raw is None:
        return None
    s = raw.strip()
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
    return date.fromisoformat(raw.strip())


def _bronze_path(data_root: Path, iso_week: str, slug: str) -> Path:
    """`data/bronze/redfin/{iso_week}/{slug}.tsv` per Phase 0 contract."""
    return data_root / "bronze" / "redfin" / iso_week / f"{slug}.tsv"


# ── Adapter ─────────────────────────────────────────────────────────────────


def _default_capabilities() -> set[Capability]:
    return {capability for capability, _ in _COLUMN_TO_METRIC.values()}


def _default_data_root() -> Path:
    return Path(__file__).resolve().parents[2] / "data"


@dataclass
class RedfinCsvAdapter:
    """Implements `DataSourceAdapter` for Redfin Data Center weekly CSVs."""

    name: str = "redfin_csv"
    license: License = "attribution"
    capabilities: set[Capability] = field(default_factory=_default_capabilities)
    data_root: Path = field(default_factory=_default_data_root)
    url: str = DEFAULT_REDFIN_WEEKLY_URL
    timeout_seconds: int = 30
    # Injected for tests; default uses `requests.get` so the `responses`
    # library can intercept. Typed as Callable returning Any because requests
    # has no proper type stubs in this project.
    http_get: Callable[..., object] = field(default=requests.get)

    # ── Protocol methods ─────────────────────────────────────────────────

    def can_fetch(self, area: GeographicArea, capability: Capability) -> bool:
        if capability not in self.capabilities:
            return False
        return any(cfg["slug"] == area.slug for cfg in SEED_CITIES)

    def reliability(self, capability: Capability) -> float:
        """Rough reliability priors per `docs/design.md` §3.4 (Redfin is the
        primary weekly source for FTHB use case)."""
        # Higher confidence on the metrics Redfin reports natively; lower on
        # derived ones (months_of_supply is computed downstream by Redfin).
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
        if not isinstance(period, Week):
            raise FetchError(
                f"Redfin CSV adapter is weekly-tier only; got period kind={period.kind!r}"
            )
        cfg = self._city_config(area.slug)
        raw_bytes = self._download(self.url)
        bronze_path = self._write_bronze(raw_bytes, period, area.slug)
        text = self._decode(raw_bytes)
        row = self._extract_city_row(text, cfg["redfin_region_name"], period)
        metrics = self._row_to_metrics(row)
        return RawSnapshot(
            area_slug=area.slug,
            period=period,
            metrics=metrics,
            source=self.name,
            fetched_at=datetime.now(tz=UTC),
            source_published_at=datetime.combine(
                _parse_iso_date(row["period_end"]),
                datetime.min.time(),
                tzinfo=UTC,
            ),
            bronze_path=str(bronze_path.relative_to(self.data_root.parent)),
        )

    # ── Internals ────────────────────────────────────────────────────────

    def _city_config(self, slug: str) -> dict[str, str]:
        for cfg in SEED_CITIES:
            if cfg["slug"] == slug:
                return cfg
        raise FetchError(f"No Redfin region mapping for slug {slug!r}")

    def _download(self, url: str) -> bytes:
        try:
            response = self.http_get(url, timeout=self.timeout_seconds)
        except requests.RequestException as e:
            raise FetchError(f"HTTP error downloading {url}: {e}") from e
        # `responses` and `requests` both provide a Response with .status_code
        # and .content; we don't want to depend on requests' types directly so
        # we use getattr-style access with explicit casts.
        status_code: int = getattr(response, "status_code", 200)
        if status_code >= 400:
            raise FetchError(f"HTTP {status_code} downloading {url}")
        content: bytes = getattr(response, "content", b"")
        return content

    @staticmethod
    def _decode(raw_bytes: bytes) -> str:
        # Redfin's "_most_recent.tsv000.gz" is gzip-compressed TSV; raw fixtures
        # in tests are plain TSV. Sniff the magic bytes.
        if raw_bytes[:2] == b"\x1f\x8b":
            try:
                raw_bytes = gzip.decompress(raw_bytes)
            except OSError as e:
                raise ParseError(f"Gzip decode failed: {e}") from e
        try:
            return raw_bytes.decode("utf-8")
        except UnicodeDecodeError as e:
            raise ParseError(f"UTF-8 decode failed: {e}") from e

    def _write_bronze(self, raw_bytes: bytes, period: Week, slug: str) -> Path:
        path = _bronze_path(self.data_root, str(period), slug)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Bronze immutability: write-if-not-exists. The same (week, city) should
        # never be re-fetched into a different file; if it already exists,
        # trust it. (Re-running ETL idempotently is a Phase 0 requirement.)
        if not path.exists():
            # Decode for storage so it's grep-able and small (gzip is the
            # transport layer, not the storage layer here).
            text = self._decode(raw_bytes)
            path.write_text(text, encoding="utf-8")
        return path

    def _extract_city_row(
        self, tsv_text: str, redfin_region_name: str, period: Week
    ) -> dict[str, str]:
        """Filter the multi-region TSV down to one row for this city + week.

        Match logic:
          - region_type == 'place' (city)
          - region == the configured Redfin name
          - property_type == 'All Residential' (top-level summary)
          - period_end falls inside the requested ISO week (Redfin uses 4-week
            rolling windows; we want the row whose period_end is the most
            recent date within or before the week's Sunday).
        """
        reader = csv.DictReader(io.StringIO(tsv_text), delimiter="\t")
        if reader.fieldnames is None:
            raise ParseError("Redfin TSV has no header row")
        required = {"region_type", "region", "property_type", "period_end"}
        missing = required - set(reader.fieldnames)
        if missing:
            raise ParseError(
                f"Redfin TSV missing required columns: {sorted(missing)}; got {reader.fieldnames!r}"
            )
        target_sunday = period.sunday()
        candidates = [
            row
            for row in reader
            if row.get("region_type") == "place"
            and row.get("region") == redfin_region_name
            and row.get("property_type") in {"All Residential", "All Homes", ""}
        ]
        if not candidates:
            raise ParseError(
                f"No Redfin rows matched region={redfin_region_name!r} "
                f"with region_type='place' and property_type in "
                f"{{'All Residential','All Homes',''}}"
            )

        # Pick the row whose period_end is the latest date <= target_sunday;
        # fall back to the latest overall if Redfin hasn't published yet.
        def _key(row: dict[str, str]) -> date:
            return _parse_iso_date(row["period_end"])

        on_or_before = [r for r in candidates if _key(r) <= target_sunday]
        if on_or_before:
            return max(on_or_before, key=_key)
        log.warning(
            "Redfin has no row at or before %s for %s; using latest available.",
            target_sunday,
            redfin_region_name,
        )
        return max(candidates, key=_key)

    def _row_to_metrics(self, row: Mapping[str, str]) -> dict[Capability, MetricValue]:
        sample_size = _parse_int(row.get("homes_sold"))
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
