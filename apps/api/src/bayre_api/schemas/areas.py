"""Wire schemas for `/v1/areas/*` (per `docs/design.md` §6.1)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# Wire-shape literals duplicated from `packages/domain/` rather than imported,
# so the API package doesn't take a hard dependency on the domain package's
# internal module layout (dev workspace vs. built wheel differ subtly). The
# string values are pinned in `apps/api/src/bayre_api/models/base.py` and in
# `packages/domain/snapshot.py::FreshnessTier`; the round-trip is enforced by
# the smoke test (which validates that `/openapi.json` parses).
GeoKind = Literal[
    "metro",
    "county",
    "city",
    "neighborhood",
    "zip",
    "school_zone",
    "school_district",
    "custom_polygon",
]
FreshnessTier = Literal[
    "realtime",
    "near_realtime",
    "daily",
    "weekly",
    "monthly",
    "quarterly",
    "annual",
]
PropertyType = Literal["sfh", "condo", "townhome", "multifamily", "land", "mobile", "other"]
PeriodKind = Literal["weekly", "monthly", "quarterly", "yearly"]
MarketPhase = Literal["peak", "cooling", "trough", "recovery", "unknown"]


class AreaSummary(BaseModel):
    """Compact representation used in search results + nav."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    kind: GeoKind
    name: str
    slug: Annotated[str, Field(pattern=r"^[a-z0-9-]+$")]
    parent_id: UUID | None = None
    metro_id: UUID | None = None


class AreaDetail(AreaSummary):
    """Full area row — adds population, denormalized centroid, etc."""

    population: int | None = None
    median_household_income: Decimal | None = None
    centroid_lon: float | None = None
    centroid_lat: float | None = None
    area_sqkm: float | None = None
    effective_from: date | None = None
    effective_to: date | None = None


class AreaSearchResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[AreaSummary]
    next_cursor: str | None = None


class DataQualityBlock(BaseModel):
    """Mirrors `docs/contracts.md` C2 `data_quality` shape."""

    model_config = ConfigDict(extra="forbid")

    sources: list[str]
    as_of: date
    confidence: Annotated[int, Field(ge=0, le=100)]
    freshness_tier: FreshnessTier


class SnapshotMetrics(BaseModel):
    """Metrics block for one (area, property_type, period) cell.

    Subset of `MarketSnapshot` columns — fields are individually optional so
    partial snapshots (small samples, missing source) round-trip cleanly.
    """

    model_config = ConfigDict(extra="forbid")

    median_sale_price: Decimal | None = None
    median_list_price: Decimal | None = None
    median_ppsf: Decimal | None = None
    sale_to_list_ratio: Decimal | None = None
    pct_sold_over_asking: Decimal | None = None
    median_dom: int | None = None
    homes_sold: int | None = None
    active_listings: int | None = None
    new_listings: int | None = None
    pending_sales: int | None = None
    months_of_supply: Decimal | None = None
    pct_with_price_drops: Decimal | None = None
    median_drop_pct: Decimal | None = None


class SnapshotResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    area_id: UUID
    property_type: PropertyType
    period_kind: PeriodKind
    period_start: date
    period_end: date
    metrics: SnapshotMetrics
    sample_size: int
    confidence_score: Annotated[int, Field(ge=0, le=100)]
    phase: MarketPhase | None = None
    clock_position: Decimal | None = None
    data_quality: DataQualityBlock
    computed_at: datetime


class TimeseriesPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    period_start: date
    value: Decimal | None
    sample_size: int
    confidence_score: int


class TimeseriesResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    area_id: UUID
    property_type: PropertyType
    metric: str
    period_kind: PeriodKind
    points: list[TimeseriesPoint]
