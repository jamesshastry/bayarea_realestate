"""Tests for the Redfin CSV adapter (monthly city tracker).

The new adapter streams ~1 GB from Redfin and gunzips inline. Tests inject a
local file as the stream factory — no real network calls, no fake gzip needed
because the factory yields already-decompressed bytes.

Fixtures in `fixtures/` are tiny ALL_CAPS TSVs hand-written to exercise the
common paths: happy, blanks/sentinels, no-match.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from domain.geographic_area import GeographicArea, GeoKind
from domain.period import Month, Week
from domain.snapshot import SnapshotFile
from pydantic import TypeAdapter

from adapters._base import (
    Capability,
    DataSourceAdapter,
    FetchError,
    ParseError,
    RawSnapshot,
)
from adapters.cli import run_redfin
from adapters.redfin_csv import (
    SEED_CITIES,
    RedfinCsvAdapter,
    iter_seed_areas,
)

FIXTURES = Path(__file__).parent / "fixtures"


# ── Helpers ─────────────────────────────────────────────────────────────────


def _local_stream(fixture_name: str):
    """Return a stream_factory that yields a local TSV file in 8 KB chunks.

    Mirrors the production factory's interface: callable taking (url, timeout)
    and returning an iterator of decompressed bytes.
    """
    path = FIXTURES / fixture_name

    def factory(_url: str, _timeout: int) -> Iterator[bytes]:
        with path.open("rb") as f:
            while True:
                chunk = f.read(8192)
                if not chunk:
                    break
                yield chunk

    return factory


def _broken_stream(_url: str, _timeout: int) -> Iterator[bytes]:
    yield b"PERIOD_END\tREGION\nx\ty\n"  # missing required columns


def _fremont() -> GeographicArea:
    return GeographicArea(kind=GeoKind.CITY, name="Fremont", slug="fremont")


def _march() -> Month:
    return Month(year=2026, month=3)


# ── Protocol conformance ────────────────────────────────────────────────────


def test_adapter_satisfies_protocol(tmp_path: Path) -> None:
    a = RedfinCsvAdapter(data_root=tmp_path)
    assert isinstance(a, DataSourceAdapter)
    assert a.name == "redfin_csv"
    assert a.license == "attribution"
    assert Capability.MEDIAN_PRICE in a.capabilities


def test_can_fetch_only_for_seed_cities(tmp_path: Path) -> None:
    a = RedfinCsvAdapter(data_root=tmp_path)
    assert a.can_fetch(_fremont(), Capability.MEDIAN_PRICE) is True
    other = GeographicArea(kind=GeoKind.CITY, name="Oakland", slug="oakland")
    assert a.can_fetch(other, Capability.MEDIAN_PRICE) is False
    assert a.can_fetch(_fremont(), Capability.SCHOOL_RATING) is False


def test_reliability_returns_high_for_native_metrics(tmp_path: Path) -> None:
    a = RedfinCsvAdapter(data_root=tmp_path)
    assert a.reliability(Capability.MEDIAN_PRICE) >= 0.9
    assert a.reliability(Capability.SCHOOL_RATING) == 0.0


def test_seed_cities_cover_all_seven_per_seed_data() -> None:
    """Locks the seed-data.md §2.1 list — fail loudly if the mapping drifts."""
    expected = {
        "dublin",
        "pleasanton",
        "fremont",
        "milpitas",
        "sunnyvale",
        "mountain-view",
        "campbell",
    }
    assert {cfg["slug"] for cfg in SEED_CITIES} == expected
    assert {area.slug for area in iter_seed_areas()} == expected


# ── Single-city fetch path ──────────────────────────────────────────────────


def test_fetch_happy_path_writes_bronze_and_returns_raw_snapshot(
    tmp_path: Path,
) -> None:
    a = RedfinCsvAdapter(
        data_root=tmp_path,
        stream_factory=_local_stream("redfin_city_minimal.tsv"),
    )
    snap = a.fetch(_fremont(), _march())

    assert isinstance(snap, RawSnapshot)
    assert snap.area_slug == "fremont"
    assert snap.source == "redfin_csv"
    assert snap.period == _march()

    # Bronze file written under data/bronze/redfin/{YYYY-MM}/{slug}.tsv
    bronze = tmp_path / "bronze" / "redfin" / "2026-03" / "fremont.tsv"
    assert bronze.exists()
    text = bronze.read_text()
    assert "Fremont, CA" in text
    # Bronze stores only the matched filtered row (header + 1 row), not the
    # whole upstream dataset.
    assert text.count("\n") <= 2

    # Metric coverage — every advertised capability is populated.
    for cap in a.capabilities:
        assert cap in snap.metrics, f"Missing capability {cap}"

    mp = snap.metrics[Capability.MEDIAN_PRICE]
    assert mp.value == Decimal("1500000")
    assert mp.unit == "USD"
    assert mp.sample_size == 142  # HOMES_SOLD from fixture

    homes = snap.metrics[Capability.HOMES_SOLD]
    assert homes.value == 142
    assert homes.unit == "count"

    dom = snap.metrics[Capability.DOM]
    assert dom.value == Decimal("18")
    assert dom.unit == "days"


def test_fetch_idempotent_does_not_overwrite_bronze(tmp_path: Path) -> None:
    """Bronze immutability per Phase 0: re-running ETL must not mutate the
    cached filtered row."""
    a = RedfinCsvAdapter(
        data_root=tmp_path,
        stream_factory=_local_stream("redfin_city_minimal.tsv"),
    )
    a.fetch(_fremont(), _march())
    bronze = tmp_path / "bronze" / "redfin" / "2026-03" / "fremont.tsv"
    bronze.write_text("SENTINEL — must not be overwritten")
    a.fetch(_fremont(), _march())
    assert bronze.read_text() == "SENTINEL — must not be overwritten"


def test_fetch_picks_exact_month_when_multiple_periods_present(tmp_path: Path) -> None:
    """Fixture has Fremont rows for 2026-02 and 2026-03; asking for 2026-03
    must pick the March row, not the February one."""
    a = RedfinCsvAdapter(
        data_root=tmp_path,
        stream_factory=_local_stream("redfin_city_minimal.tsv"),
    )
    snap = a.fetch(_fremont(), Month(year=2026, month=3))
    assert snap.source_published_at.date() == date(2026, 3, 31)

    snap_feb = a.fetch(_fremont(), Month(year=2026, month=2))
    assert snap_feb.source_published_at.date() == date(2026, 2, 28)


def test_fetch_skips_non_all_residential_property_types(tmp_path: Path) -> None:
    """Fixture has both 'All Residential' and 'Single Family Residential' for
    Fremont in March; the adapter must pick the All Residential row."""
    a = RedfinCsvAdapter(
        data_root=tmp_path,
        stream_factory=_local_stream("redfin_city_minimal.tsv"),
    )
    snap = a.fetch(_fremont(), _march())
    # 'All Residential' has median_price 1_500_000, SFR has 1_620_000.
    assert snap.metrics[Capability.MEDIAN_PRICE].value == Decimal("1500000")


# ── Edge cases: blanks, sentinels, parse errors ─────────────────────────────


def test_fetch_handles_blanks_and_sentinel_values(tmp_path: Path) -> None:
    a = RedfinCsvAdapter(
        data_root=tmp_path,
        stream_factory=_local_stream("redfin_city_with_blanks.tsv"),
    )
    snap = a.fetch(_fremont(), _march())
    # Blank MEDIAN_PPSF → None, not zero.
    assert snap.metrics[Capability.PPSF].value is None
    # '-' sentinel for PRICE_DROPS → None.
    assert snap.metrics[Capability.PCT_PRICE_DROPS].value is None
    # Blank NEW_LISTINGS → None even though it's a count column.
    assert snap.metrics[Capability.NEW_LISTINGS].value is None


def test_fetch_strips_currency_and_percent_formatting(tmp_path: Path) -> None:
    a = RedfinCsvAdapter(
        data_root=tmp_path,
        stream_factory=_local_stream("redfin_city_with_blanks.tsv"),
    )
    dublin = GeographicArea(kind=GeoKind.CITY, name="Dublin", slug="dublin")
    snap = a.fetch(dublin, _march())
    # `$1,625,000` parses to 1_625_000.
    assert snap.metrics[Capability.MEDIAN_PRICE].value == Decimal("1625000")
    # `18.2%` parses to Decimal("18.2").
    assert snap.metrics[Capability.PCT_PRICE_DROPS].value == Decimal("18.2")


def test_fetch_raises_parse_error_when_no_row_matches(tmp_path: Path) -> None:
    a = RedfinCsvAdapter(
        data_root=tmp_path,
        stream_factory=_local_stream("redfin_city_no_match.tsv"),
    )
    with pytest.raises(ParseError):
        a.fetch(_fremont(), _march())


def test_fetch_raises_parse_error_on_missing_header(tmp_path: Path) -> None:
    a = RedfinCsvAdapter(data_root=tmp_path, stream_factory=_broken_stream)
    with pytest.raises(ParseError):
        a.fetch(_fremont(), _march())


def test_fetch_rejects_weekly_period(tmp_path: Path) -> None:
    a = RedfinCsvAdapter(data_root=tmp_path)
    with pytest.raises(FetchError):
        a.fetch(_fremont(), Week(year=2026, week=19))  # type: ignore[arg-type]


def test_fetch_rejects_unknown_slug(tmp_path: Path) -> None:
    a = RedfinCsvAdapter(
        data_root=tmp_path,
        stream_factory=_local_stream("redfin_city_minimal.tsv"),
    )
    other = GeographicArea(kind=GeoKind.CITY, name="Oakland", slug="oakland")
    with pytest.raises(FetchError):
        a.fetch(other, _march())


# ── Multi-city streaming pass ───────────────────────────────────────────────


def test_fetch_all_seed_cities_returns_dict_keyed_by_slug(tmp_path: Path) -> None:
    a = RedfinCsvAdapter(
        data_root=tmp_path,
        stream_factory=_local_stream("redfin_city_minimal.tsv"),
    )
    snapshots = a.fetch_all_seed_cities(_march())
    assert set(snapshots.keys()) == {
        "dublin",
        "pleasanton",
        "fremont",
        "milpitas",
        "sunnyvale",
        "mountain-view",
        "campbell",
    }
    assert all(snap.area_slug == slug for slug, snap in snapshots.items())


# ── CLI orchestration ──────────────────────────────────────────────────────


def test_cli_run_redfin_writes_valid_snapshot_file(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    sources_path = data_root / "sources.json"
    output_path = data_root / "2026-04-15.json"
    a = RedfinCsvAdapter(
        data_root=data_root,
        stream_factory=_local_stream("redfin_city_minimal.tsv"),
    )
    written = run_redfin(
        "2026-03",
        data_root=data_root,
        sources_path=sources_path,
        output_path=output_path,
        adapter=a,
        today=date(2026, 4, 15),
    )
    assert written == output_path
    payload = json.loads(output_path.read_text())
    snap = TypeAdapter(SnapshotFile).validate_python(payload)
    assert snap.as_of_period == "2026-03"
    assert {c.slug for c in snap.cities} == {
        "dublin",
        "pleasanton",
        "fremont",
        "milpitas",
        "sunnyvale",
        "mountain-view",
        "campbell",
    }
    fremont = next(c for c in snap.cities if c.slug == "fremont")
    assert fremont.sfh is not None
    assert fremont.sfh.median_price == Decimal("1500000")
    assert fremont.data_quality.freshness_tier.value == "monthly"
    assert "redfin_csv:2026-03" in fremont.data_quality.sources

    # sources.json updated.
    sources_payload = json.loads(sources_path.read_text())
    redfin_status = sources_payload["sources"]["redfin_csv"]
    assert redfin_status["status"] == "ok"
    assert len(redfin_status["successful_areas"]) == 7
    assert redfin_status["failed_areas"] == {}


def test_cli_run_redfin_isolates_per_city_failures(tmp_path: Path) -> None:
    """Per NF-REL-02: a fixture with no Bay Area cities → all 7 seed cities
    miss → run raises RuntimeError, but sources.json log is still written
    with status=error so the status page can show what happened."""
    data_root = tmp_path / "data"
    sources_path = data_root / "sources.json"
    a = RedfinCsvAdapter(
        data_root=data_root,
        stream_factory=_local_stream("redfin_city_no_match.tsv"),
    )
    with pytest.raises(RuntimeError):
        run_redfin(
            "2026-03",
            data_root=data_root,
            sources_path=sources_path,
            output_path=data_root / "snap.json",
            adapter=a,
            today=date(2026, 4, 15),
        )
    sources_payload = json.loads(sources_path.read_text())
    redfin_status = sources_payload["sources"]["redfin_csv"]
    assert redfin_status["status"] == "error"
    assert len(redfin_status["failed_areas"]) == 7


def test_cli_run_redfin_partial_success_marks_partial(tmp_path: Path) -> None:
    """If at least one city succeeds and at least one fails, sources.json says
    'partial' and the snapshot file contains only successful cities."""
    fixture = (
        b'"PERIOD_BEGIN"\t"PERIOD_END"\t"REGION_TYPE"\t"REGION"\t"PROPERTY_TYPE"\t'
        b'"MEDIAN_SALE_PRICE"\t"MEDIAN_PPSF"\t"MEDIAN_DOM"\t"AVG_SALE_TO_LIST"\t'
        b'"HOMES_SOLD"\t"INVENTORY"\t"NEW_LISTINGS"\t"MONTHS_OF_SUPPLY"\t"PRICE_DROPS"\n'
        b'"2026-03-01"\t"2026-03-31"\t"place"\t"Fremont, CA"\t"All Residential"\t'
        b"1500000\t950\t18\t1.02\t142\t89\t102\t1.9\t0.145\n"
        b'"2026-03-01"\t"2026-03-31"\t"place"\t"Dublin, CA"\t"All Residential"\t'
        b"1625000\t780\t22\t1.01\t38\t51\t44\t2.1\t0.182\n"
    )

    def factory(_url: str, _timeout: int) -> Iterator[bytes]:
        yield fixture

    data_root = tmp_path / "data"
    sources_path = data_root / "sources.json"
    output_path = data_root / "snap.json"
    a = RedfinCsvAdapter(data_root=data_root, stream_factory=factory)
    run_redfin(
        "2026-03",
        data_root=data_root,
        sources_path=sources_path,
        output_path=output_path,
        adapter=a,
        today=date(2026, 4, 15),
    )
    payload = json.loads(output_path.read_text())
    snap = SnapshotFile.model_validate(payload)
    assert {c.slug for c in snap.cities} == {"fremont", "dublin"}
    sources_payload = json.loads(sources_path.read_text())
    redfin_status = sources_payload["sources"]["redfin_csv"]
    assert redfin_status["status"] == "partial"
    assert set(redfin_status["successful_areas"]) == {"fremont", "dublin"}
    assert len(redfin_status["failed_areas"]) == 5


def test_cli_resolve_month_current_returns_previous_calendar_month() -> None:
    """`current` resolves to last month — Redfin lags ~1 month."""
    from adapters.cli import _resolve_month

    assert _resolve_month("current", today=date(2026, 5, 12)) == Month(
        year=2026, month=4
    )
    assert _resolve_month("current", today=date(2026, 1, 5)) == Month(
        year=2025, month=12
    )
    assert _resolve_month("2025-11", today=date(2026, 5, 12)) == Month(
        year=2025, month=11
    )
