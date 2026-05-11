"""Tests for the Redfin CSV adapter.

Uses the `responses` library to intercept HTTP — no real network calls. The
TSV fixtures in `fixtures/` are tiny, hand-written rows that exercise the
common paths (happy, blanks/sentinels, no-match).
"""

from __future__ import annotations

import gzip
import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
import responses
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
    DEFAULT_REDFIN_WEEKLY_URL,
    SEED_CITIES,
    RedfinCsvAdapter,
    iter_seed_areas,
)

FIXTURES = Path(__file__).parent / "fixtures"


# ── Helpers ─────────────────────────────────────────────────────────────────


def _fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def _gzipped_fixture(name: str) -> bytes:
    return gzip.compress(_fixture(name))


def _fremont() -> GeographicArea:
    return GeographicArea(kind=GeoKind.CITY, name="Fremont", slug="fremont")


def _week() -> Week:
    return Week(year=2026, week=19)  # Sunday = 2026-05-10


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
    # Capability not advertised
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


# ── Happy path: plain TSV via mocked HTTP ───────────────────────────────────


@responses.activate
def test_fetch_happy_path_writes_bronze_and_returns_raw_snapshot(
    tmp_path: Path,
) -> None:
    responses.add(
        responses.GET,
        DEFAULT_REDFIN_WEEKLY_URL,
        body=_fixture("redfin_weekly_minimal.tsv"),
        status=200,
        content_type="text/tab-separated-values",
    )
    a = RedfinCsvAdapter(data_root=tmp_path)
    snap = a.fetch(_fremont(), _week())

    assert isinstance(snap, RawSnapshot)
    assert snap.area_slug == "fremont"
    assert snap.source == "redfin_csv"
    assert snap.period == _week()
    # Bronze file written under data/bronze/redfin/{week}/{slug}.tsv
    bronze = tmp_path / "bronze" / "redfin" / "2026-W19" / "fremont.tsv"
    assert bronze.exists()
    assert "Fremont, CA" in bronze.read_text()

    # Metric coverage — every advertised capability is populated.
    for cap in a.capabilities:
        assert cap in snap.metrics, f"Missing capability {cap}"

    mp = snap.metrics[Capability.MEDIAN_PRICE]
    assert mp.value == Decimal("1500000")
    assert mp.unit == "USD"
    assert mp.sample_size == 142  # homes_sold from fixture

    homes = snap.metrics[Capability.HOMES_SOLD]
    assert homes.value == 142
    assert homes.unit == "count"

    dom = snap.metrics[Capability.DOM]
    assert dom.value == Decimal("18")
    assert dom.unit == "days"


@responses.activate
def test_fetch_decodes_gzip_payload(tmp_path: Path) -> None:
    """Adapter must transparently handle gzip — Redfin's real URL is `.tsv000.gz`."""
    responses.add(
        responses.GET,
        DEFAULT_REDFIN_WEEKLY_URL,
        body=_gzipped_fixture("redfin_weekly_minimal.tsv"),
        status=200,
        content_type="application/gzip",
    )
    a = RedfinCsvAdapter(data_root=tmp_path)
    snap = a.fetch(_fremont(), _week())
    assert snap.metrics[Capability.MEDIAN_PRICE].value == Decimal("1500000")
    # Bronze stored as plain TSV (decoded), not gzip.
    bronze = tmp_path / "bronze" / "redfin" / "2026-W19" / "fremont.tsv"
    assert bronze.read_text().startswith("period_begin\t")


@responses.activate
def test_fetch_idempotent_does_not_overwrite_bronze(tmp_path: Path) -> None:
    """Bronze immutability per Phase 0: re-running ETL must not mutate the
    cached raw payload."""
    responses.add(
        responses.GET,
        DEFAULT_REDFIN_WEEKLY_URL,
        body=_fixture("redfin_weekly_minimal.tsv"),
        status=200,
    )
    a = RedfinCsvAdapter(data_root=tmp_path)
    a.fetch(_fremont(), _week())
    bronze = tmp_path / "bronze" / "redfin" / "2026-W19" / "fremont.tsv"
    bronze.write_text("SENTINEL — must not be overwritten")
    a.fetch(_fremont(), _week())
    assert bronze.read_text() == "SENTINEL — must not be overwritten"


# ── Edge cases: blanks, sentinels, parse errors ─────────────────────────────


@responses.activate
def test_fetch_handles_blanks_and_sentinel_values(tmp_path: Path) -> None:
    responses.add(
        responses.GET,
        DEFAULT_REDFIN_WEEKLY_URL,
        body=_fixture("redfin_weekly_with_blanks.tsv"),
        status=200,
    )
    a = RedfinCsvAdapter(data_root=tmp_path)
    snap = a.fetch(_fremont(), _week())
    # Blank median_ppsf → None, not zero.
    assert snap.metrics[Capability.PPSF].value is None
    # '-' sentinel for pct_with_price_drops → None.
    assert snap.metrics[Capability.PCT_PRICE_DROPS].value is None
    # Blank `new_listings` → None even though it's a count column.
    assert snap.metrics[Capability.NEW_LISTINGS].value is None


@responses.activate
def test_fetch_strips_currency_and_percent_formatting(tmp_path: Path) -> None:
    responses.add(
        responses.GET,
        DEFAULT_REDFIN_WEEKLY_URL,
        body=_fixture("redfin_weekly_with_blanks.tsv"),
        status=200,
    )
    dublin = GeographicArea(kind=GeoKind.CITY, name="Dublin", slug="dublin")
    a = RedfinCsvAdapter(data_root=tmp_path)
    snap = a.fetch(dublin, _week())
    assert snap.metrics[Capability.MEDIAN_PRICE].value == Decimal("1625000")
    assert snap.metrics[Capability.PCT_PRICE_DROPS].value == Decimal("18.2")


@responses.activate
def test_fetch_raises_parse_error_when_no_row_matches(tmp_path: Path) -> None:
    responses.add(
        responses.GET,
        DEFAULT_REDFIN_WEEKLY_URL,
        body=_fixture("redfin_weekly_no_match.tsv"),
        status=200,
    )
    a = RedfinCsvAdapter(data_root=tmp_path)
    with pytest.raises(ParseError):
        a.fetch(_fremont(), _week())


@responses.activate
def test_fetch_raises_parse_error_on_missing_header(tmp_path: Path) -> None:
    responses.add(
        responses.GET,
        DEFAULT_REDFIN_WEEKLY_URL,
        body=b"period_end\tregion\nx\ty\n",  # missing region_type / property_type
        status=200,
    )
    a = RedfinCsvAdapter(data_root=tmp_path)
    with pytest.raises(ParseError):
        a.fetch(_fremont(), _week())


@responses.activate
def test_fetch_raises_fetch_error_on_http_500(tmp_path: Path) -> None:
    responses.add(responses.GET, DEFAULT_REDFIN_WEEKLY_URL, status=500)
    a = RedfinCsvAdapter(data_root=tmp_path)
    with pytest.raises(FetchError):
        a.fetch(_fremont(), _week())


def test_fetch_rejects_monthly_period(tmp_path: Path) -> None:
    a = RedfinCsvAdapter(data_root=tmp_path)
    with pytest.raises(FetchError):
        a.fetch(_fremont(), Month(year=2026, month=4))  # type: ignore[arg-type]


def test_fetch_rejects_unknown_slug(tmp_path: Path) -> None:
    a = RedfinCsvAdapter(data_root=tmp_path)
    other = GeographicArea(kind=GeoKind.CITY, name="Oakland", slug="oakland")
    with pytest.raises(FetchError):
        a.fetch(other, _week())


# ── Picks the latest period_end at or before the requested week's Sunday ────


@responses.activate
def test_fetch_picks_latest_row_within_window(tmp_path: Path) -> None:
    """The fixture has two Fremont rows (period_end 2026-04-27 and
    2026-05-04). We ask for week 19 (Sunday 2026-05-10) → the 2026-05-04 row
    must be chosen."""
    responses.add(
        responses.GET,
        DEFAULT_REDFIN_WEEKLY_URL,
        body=_fixture("redfin_weekly_minimal.tsv"),
        status=200,
    )
    a = RedfinCsvAdapter(data_root=tmp_path)
    snap = a.fetch(_fremont(), Week(year=2026, week=19))
    assert snap.source_published_at.date() == date(2026, 5, 4)


# ── CLI orchestration ──────────────────────────────────────────────────────


@responses.activate
def test_cli_run_redfin_writes_valid_snapshot_file(tmp_path: Path) -> None:
    responses.add(
        responses.GET,
        DEFAULT_REDFIN_WEEKLY_URL,
        body=_fixture("redfin_weekly_minimal.tsv"),
        status=200,
    )
    data_root = tmp_path / "data"
    sources_path = data_root / "sources.json"
    output_path = data_root / "2026-05-14.json"
    a = RedfinCsvAdapter(data_root=data_root)
    written = run_redfin(
        "2026-W19",
        data_root=data_root,
        sources_path=sources_path,
        output_path=output_path,
        adapter=a,
        today=date(2026, 5, 14),
    )
    assert written == output_path
    payload = json.loads(output_path.read_text())
    snap = TypeAdapter(SnapshotFile).validate_python(payload)
    assert snap.as_of_week == "2026-W19"
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
    assert fremont.data_quality.freshness_tier.value == "weekly"
    assert "redfin_csv:2026-w19" in fremont.data_quality.sources

    # sources.json updated.
    sources_payload = json.loads(sources_path.read_text())
    redfin_status = sources_payload["sources"]["redfin_csv"]
    assert redfin_status["status"] == "ok"
    assert len(redfin_status["successful_areas"]) == 7
    assert redfin_status["failed_areas"] == {}


@responses.activate
def test_cli_run_redfin_isolates_per_city_failures(tmp_path: Path) -> None:
    """Per NF-REL-02: one bad city must not abort the whole run.

    Fixture only contains Oakland → all 7 seed cities miss → run raises
    RuntimeError, but the sources.json log is still written with status=error
    so the status page can show what happened."""
    responses.add(
        responses.GET,
        DEFAULT_REDFIN_WEEKLY_URL,
        body=_fixture("redfin_weekly_no_match.tsv"),
        status=200,
    )
    data_root = tmp_path / "data"
    sources_path = data_root / "sources.json"
    a = RedfinCsvAdapter(data_root=data_root)
    with pytest.raises(RuntimeError):
        run_redfin(
            "2026-W19",
            data_root=data_root,
            sources_path=sources_path,
            output_path=data_root / "snap.json",
            adapter=a,
            today=date(2026, 5, 14),
        )
    sources_payload = json.loads(sources_path.read_text())
    redfin_status = sources_payload["sources"]["redfin_csv"]
    assert redfin_status["status"] == "error"
    assert len(redfin_status["failed_areas"]) == 7


@responses.activate
def test_cli_run_redfin_partial_success_marks_partial(tmp_path: Path) -> None:
    """If at least one city succeeds and at least one fails, sources.json says
    'partial' and the snapshot file contains only successful cities."""
    # Build a mini-fixture with only Fremont + Dublin.
    fixture = (
        b"period_begin\tperiod_end\tregion_type\tregion\tproperty_type\t"
        b"median_sale_price\tmedian_ppsf\tmedian_days_on_market\t"
        b"average_sale_to_list_ratio\thomes_sold\tactive_listings\t"
        b"new_listings\tmonths_of_supply\tpercent_homes_sold_with_price_drops\n"
        b"2026-04-13\t2026-05-04\tplace\tFremont, CA\tAll Residential\t"
        b"1500000\t950\t18\t1.02\t142\t89\t102\t1.9\t14.5\n"
        b"2026-04-13\t2026-05-04\tplace\tDublin, CA\tAll Residential\t"
        b"1625000\t780\t22\t1.01\t38\t51\t44\t2.1\t18.2\n"
    )
    responses.add(
        responses.GET,
        DEFAULT_REDFIN_WEEKLY_URL,
        body=fixture,
        status=200,
    )
    data_root = tmp_path / "data"
    sources_path = data_root / "sources.json"
    output_path = data_root / "snap.json"
    a = RedfinCsvAdapter(data_root=data_root)
    run_redfin(
        "2026-W19",
        data_root=data_root,
        sources_path=sources_path,
        output_path=output_path,
        adapter=a,
        today=date(2026, 5, 14),
    )
    payload = json.loads(output_path.read_text())
    snap = SnapshotFile.model_validate(payload)
    assert {c.slug for c in snap.cities} == {"fremont", "dublin"}
    sources_payload = json.loads(sources_path.read_text())
    redfin_status = sources_payload["sources"]["redfin_csv"]
    assert redfin_status["status"] == "partial"
    assert set(redfin_status["successful_areas"]) == {"fremont", "dublin"}
    assert len(redfin_status["failed_areas"]) == 5
