"""Schema validation round-trip tests for the snapshot file format.

These tests are the executable form of `docs/contracts.md` C2 — if any of them
break, the JSON contract has changed and downstream agents need to be told
(bump `SCHEMA_VERSION` per the doc's Update protocol).
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any, cast

import pytest
from pydantic import TypeAdapter, ValidationError

from domain.geographic_area import GeographicArea, GeoKind
from domain.period import Month, Period, Week
from domain.snapshot import (
    SCHEMA_VERSION,
    CitySnapshot,
    DataQuality,
    FreshnessTier,
    MetricsBlock,
    SnapshotFile,
)

# ── Fixtures ────────────────────────────────────────────────────────────────


def _valid_payload() -> dict[str, object]:
    """A minimal-but-realistic payload — what the Redfin adapter writes."""
    return {
        "schema_version": SCHEMA_VERSION,
        "as_of_period": "2026-W19",
        "scraped_at": "2026-05-08T18:00:00Z",
        "cities": [
            {
                "slug": "fremont",
                "name": "Fremont",
                "county": "Alameda",
                "metro": "bay-area",
                "sfh": {
                    "median_price": "1500000",
                    "median_ppsf": "950",
                    "yoy_pct": "-8.0",
                    "dom": 18,
                    "sale_to_list": "1.02",
                    "homes_sold": 142,
                    "active_listings": 89,
                    "months_of_supply": "1.9",
                },
                "condo": None,
                "data_quality": {
                    "sources": ["redfin_csv:2026-w17"],
                    "as_of": "2026-05-04",
                    "confidence": 88,
                    "freshness_tier": "weekly",
                },
            }
        ],
    }


# ── SnapshotFile validation ─────────────────────────────────────────────────


def test_snapshot_file_validates_minimum_payload() -> None:
    payload = _valid_payload()
    snap = TypeAdapter(SnapshotFile).validate_python(payload)
    assert snap.schema_version == SCHEMA_VERSION
    assert snap.as_of_period == "2026-W19"
    assert len(snap.cities) == 1
    assert snap.cities[0].slug == "fremont"
    assert snap.cities[0].sfh is not None
    assert snap.cities[0].sfh.median_price == Decimal("1500000")


def test_snapshot_file_round_trips_through_json() -> None:
    payload = _valid_payload()
    snap = SnapshotFile.model_validate(payload)
    json_str = snap.model_dump_json()
    reloaded = SnapshotFile.model_validate_json(json_str)
    # Round-trip equality of canonicalized JSON
    assert reloaded.model_dump_json() == snap.model_dump_json()


def test_snapshot_file_rejects_extra_fields() -> None:
    payload = _valid_payload()
    payload["unknown_top_level"] = "nope"
    with pytest.raises(ValidationError):
        SnapshotFile.model_validate(payload)


def test_snapshot_file_rejects_wrong_schema_version() -> None:
    payload = _valid_payload()
    payload["schema_version"] = SCHEMA_VERSION + 1
    with pytest.raises(ValidationError):
        SnapshotFile.model_validate(payload)


def test_snapshot_file_rejects_empty_cities_list() -> None:
    payload = _valid_payload()
    payload["cities"] = []
    with pytest.raises(ValidationError):
        SnapshotFile.model_validate(payload)


def test_snapshot_file_rejects_malformed_period() -> None:
    """`as_of_period` must be ISO week (YYYY-Www) or ISO month (YYYY-MM)."""
    payload = _valid_payload()
    # Neither week (no `W`, 3-digit suffix) nor month (3-digit suffix).
    payload["as_of_period"] = "2026-019"
    with pytest.raises(ValidationError):
        SnapshotFile.model_validate(payload)


def test_snapshot_file_accepts_iso_month_period() -> None:
    """v2 schema: `as_of_period` accepts ISO months (YYYY-MM) for the
    monthly-cadence Redfin source as well as ISO weeks."""
    payload = _valid_payload()
    payload["as_of_period"] = "2026-04"
    snap = SnapshotFile.model_validate(payload)
    assert snap.as_of_period == "2026-04"


# ── CitySnapshot validation ─────────────────────────────────────────────────


def test_city_snapshot_requires_data_quality() -> None:
    with pytest.raises(ValidationError):
        CitySnapshot.model_validate(
            {
                "slug": "fremont",
                "name": "Fremont",
                "county": "Alameda",
                "metro": "bay-area",
                # missing data_quality
            }
        )


def test_city_snapshot_rejects_uppercase_slug() -> None:
    with pytest.raises(ValidationError):
        CitySnapshot.model_validate(
            {
                "slug": "Fremont",  # uppercase not allowed
                "name": "Fremont",
                "county": "Alameda",
                "metro": "bay-area",
                "data_quality": {
                    "sources": ["redfin_csv:2026-w17"],
                    "as_of": "2026-05-04",
                    "confidence": 88,
                    "freshness_tier": "weekly",
                },
            }
        )


def test_city_snapshot_omits_condo_when_no_data() -> None:
    """Per design.md §10.7.6: omit condo block rather than fake it."""
    payload = _valid_payload()
    cities = cast(list[dict[str, Any]], payload["cities"])
    cities[0].pop("condo", None)
    snap = SnapshotFile.model_validate(payload)
    assert snap.cities[0].condo is None


# ── DataQuality validation ──────────────────────────────────────────────────


def test_data_quality_requires_freshness_tier() -> None:
    with pytest.raises(ValidationError):
        DataQuality.model_validate(
            {
                "sources": ["redfin_csv:2026-w17"],
                "as_of": "2026-05-04",
                "confidence": 88,
                # missing freshness_tier
            }
        )


def test_data_quality_rejects_blank_source_string() -> None:
    with pytest.raises(ValidationError):
        DataQuality.model_validate(
            {
                "sources": ["redfin_csv:2026-w17", "  "],
                "as_of": "2026-05-04",
                "confidence": 88,
                "freshness_tier": "weekly",
            }
        )


def test_data_quality_rejects_empty_sources() -> None:
    with pytest.raises(ValidationError):
        DataQuality.model_validate(
            {
                "sources": [],
                "as_of": "2026-05-04",
                "confidence": 88,
                "freshness_tier": "weekly",
            }
        )


def test_data_quality_rejects_confidence_out_of_range() -> None:
    for bad in (-1, 101):
        with pytest.raises(ValidationError):
            DataQuality.model_validate(
                {
                    "sources": ["redfin_csv:2026-w17"],
                    "as_of": "2026-05-04",
                    "confidence": bad,
                    "freshness_tier": "weekly",
                }
            )


@pytest.mark.parametrize("tier", list(FreshnessTier))
def test_freshness_tier_accepts_all_enum_values(tier: FreshnessTier) -> None:
    dq = DataQuality.model_validate(
        {
            "sources": ["redfin_csv:2026-w17"],
            "as_of": "2026-05-04",
            "confidence": 88,
            "freshness_tier": tier.value,
        }
    )
    assert dq.freshness_tier == tier


def test_freshness_tier_rejects_unknown_string() -> None:
    with pytest.raises(ValidationError):
        DataQuality.model_validate(
            {
                "sources": ["redfin_csv:2026-w17"],
                "as_of": "2026-05-04",
                "confidence": 88,
                "freshness_tier": "biweekly",
            }
        )


# ── MetricsBlock validation ─────────────────────────────────────────────────


def test_metrics_block_accepts_all_optional() -> None:
    """A near-empty MetricsBlock is valid — partial data over parse failure."""
    m = MetricsBlock.model_validate({})
    assert m.median_price is None


def test_metrics_block_rejects_negative_money() -> None:
    with pytest.raises(ValidationError):
        MetricsBlock.model_validate({"median_price": "-1"})


def test_metrics_block_rejects_negative_count() -> None:
    with pytest.raises(ValidationError):
        MetricsBlock.model_validate({"homes_sold": -1})


def test_metrics_block_pct_drops_capped_at_100() -> None:
    with pytest.raises(ValidationError):
        MetricsBlock.model_validate({"pct_with_price_drops": "105"})


# ── Period (Week / Month) ───────────────────────────────────────────────────


def test_week_parses_iso_week_string() -> None:
    w = Week.parse("2026-W19")
    assert w.year == 2026
    assert w.week == 19
    assert str(w) == "2026-W19"


def test_week_rejects_bad_format() -> None:
    with pytest.raises(ValueError):
        Week.parse("2026-19")
    with pytest.raises(ValueError):
        Week.parse("2026/W19")


def test_week_from_date_returns_iso_calendar_week() -> None:
    w = Week.from_date(date(2026, 5, 8))  # Friday
    assert (w.year, w.week) == (2026, 19)


def test_week_monday_and_sunday_round_trip() -> None:
    w = Week(year=2026, week=19)
    assert w.monday().weekday() == 0
    assert w.sunday().weekday() == 6
    # Round-trip through from_date
    assert Week.from_date(w.monday()) == w
    assert Week.from_date(w.sunday()) == w


def test_week_rejects_week_past_year_end() -> None:
    # 2026 has 53 ISO weeks; 2025 has 52 — pick one that's actually invalid.
    # Use 2024 (52 ISO weeks): W53 should be rejected.
    with pytest.raises(ValueError):
        Week(year=2024, week=53)


def test_month_parses_string() -> None:
    m = Month.parse("2026-04")
    assert (m.year, m.month) == (2026, 4)
    assert str(m) == "2026-04"


def test_month_rejects_bad_format() -> None:
    with pytest.raises(ValueError):
        Month.parse("2026/04")


def test_period_discriminator_round_trips() -> None:
    """The Period union should JSON-roundtrip cleanly via the `kind` discriminator."""
    adapter: TypeAdapter[Week | Month] = TypeAdapter(Period)
    week = Week(year=2026, week=19)
    month = Month(year=2026, month=4)
    for p in (week, month):
        dumped: object = adapter.dump_python(p)
        reloaded = adapter.validate_python(dumped)
        assert reloaded == p


# ── GeographicArea stub ─────────────────────────────────────────────────────


def test_geographic_area_minimum_fields() -> None:
    ga = GeographicArea(kind=GeoKind.CITY, name="Fremont", slug="fremont")
    assert ga.kind is GeoKind.CITY
    assert ga.parent_id is None


def test_geographic_area_rejects_uppercase_slug() -> None:
    with pytest.raises(ValidationError):
        GeographicArea(kind=GeoKind.CITY, name="Fremont", slug="Fremont")


def test_geographic_area_immutable() -> None:
    ga = GeographicArea(kind=GeoKind.CITY, name="Fremont", slug="fremont")
    with pytest.raises(ValidationError):
        ga.name = "Other"  # type: ignore[misc]


# ── End-to-end: a snapshot built programmatically validates ─────────────────


def test_programmatic_snapshot_validates() -> None:
    snap = SnapshotFile(
        as_of_period="2026-W19",
        scraped_at=datetime(2026, 5, 8, 18, 0, 0, tzinfo=UTC),
        cities=[
            CitySnapshot(
                slug="fremont",
                name="Fremont",
                county="Alameda",
                metro="bay-area",
                sfh=MetricsBlock(median_price=Decimal("1500000")),
                data_quality=DataQuality(
                    sources=["redfin_csv:2026-w17"],
                    as_of=date(2026, 5, 4),
                    confidence=88,
                    freshness_tier=FreshnessTier.WEEKLY,
                ),
            )
        ],
    )
    payload = snap.model_dump(mode="json")
    revalidated = TypeAdapter(SnapshotFile).validate_python(payload)
    assert revalidated == snap
