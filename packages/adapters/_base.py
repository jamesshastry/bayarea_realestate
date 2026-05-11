"""Adapter protocol + value objects per `docs/contracts.md` C1 and `docs/design.md` §3.1.

`DataSourceAdapter` is a runtime-checkable Protocol — concrete adapters
(`redfin_csv.py`, future `fred_rates.py`, etc.) implement it as plain classes
without inheritance. The `Capability` enum is the closed set of "things an
adapter can produce"; downstream code switches on it rather than on adapter
class name.

`RawSnapshot` and `MetricValue` are frozen dataclasses (not Pydantic models)
because they're internal value objects that don't need to JSON-serialize
through the public schema — Pydantic models live in `packages/domain/`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Literal, Protocol, runtime_checkable

from domain.geographic_area import GeographicArea
from domain.period import Period


class Capability(StrEnum):
    """Closed set of metric "kinds" an adapter can advertise.

    Mirrors `docs/design.md` §3.1. The string values are stable — they appear
    in logs, in `data_source.reliability` JSONB, and in resolver code.
    """

    MEDIAN_PRICE = "median_price"
    INVENTORY = "inventory"
    DOM = "dom"
    SALE_TO_LIST = "sale_to_list"
    PPSF = "ppsf"
    BY_PROPERTY_TYPE = "by_property_type"
    BY_BEDROOMS = "by_bedrooms"
    BY_SCHOOL_ZONE = "by_school_zone"
    SCHOOL_RATING = "school_rating"
    PARCEL_TAX = "parcel_tax"
    MELLO_ROOS = "mello_roos"
    RENT = "rent"
    MORTGAGE_RATE = "mortgage_rate"
    FLOOD_RISK = "flood_risk"
    WILDFIRE_RISK = "wildfire_risk"
    HOMES_SOLD = "homes_sold"
    NEW_LISTINGS = "new_listings"
    MONTHS_OF_SUPPLY = "months_of_supply"
    PCT_PRICE_DROPS = "pct_price_drops"


# License values mirror the `data_source.license` column in datamodel.md §7.1.
# Keep aligned when adding new values.
License = Literal["public_domain", "attribution", "commercial", "internal_only"]


# Unit strings are intentionally a small closed set — adding a new unit means
# updating the consumer (UI, export). Per docs/contracts.md C1 the canonical
# values are: USD, USD/sqft, days, ratio, months, pct, count.
MetricUnit = Literal["USD", "USD/sqft", "days", "ratio", "months", "pct", "count"]


@dataclass(frozen=True, slots=True)
class MetricValue:
    """One observed metric. `sample_size` is required for confidence scoring
    (see `docs/design.md` §5.2)."""

    value: Decimal | int | None
    sample_size: int | None
    unit: MetricUnit


@dataclass(frozen=True, slots=True)
class RawSnapshot:
    """Adapter output shape — exactly `docs/contracts.md` C1.

    `bronze_path` is the relative path to the cached raw payload (relative to
    repo root or to a provided `data_root`); the resolver does not read it,
    but it's included for traceability and the per-source page on the status
    UI.
    """

    area_slug: str
    period: Period
    metrics: dict[Capability, MetricValue]
    source: str
    fetched_at: datetime
    source_published_at: datetime
    bronze_path: str


@runtime_checkable
class DataSourceAdapter(Protocol):
    """Contract every adapter implements. Class-attribute fields (`name`,
    `license`, `capabilities`) are part of the Protocol — runtime introspection
    code in the resolver depends on them."""

    name: str
    license: License
    capabilities: set[Capability]

    def can_fetch(self, area: GeographicArea, capability: Capability) -> bool:
        """Cheap predicate — does this adapter cover the (area, capability)
        pair? Implementations should NOT do I/O here."""
        ...

    def fetch(self, area: GeographicArea, period: Period) -> RawSnapshot:
        """Pull data for (area, period), cache to Bronze, return RawSnapshot.

        Failure modes: raise `AdapterError` (or subclasses defined per-adapter)
        — the resolver catches and falls back. NEVER swallow errors silently;
        a stale snapshot is worse than a missing one.
        """
        ...

    def reliability(self, capability: Capability) -> float:
        """0.0-1.0 reliability rating for (this adapter, capability). Used by
        the resolver to break ties between sources."""
        ...


class AdapterError(Exception):
    """Base class for adapter-specific failures. Subclasses can carry context
    (e.g. HTTP status, parse anomaly list)."""


class FetchError(AdapterError):
    """Network / HTTP failure during fetch."""


class ParseError(AdapterError):
    """Payload was downloaded but couldn't be parsed into the expected shape."""
