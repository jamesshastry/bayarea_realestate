"""Pydantic v2 models for the Phase 0 weekly snapshot file format.

Implements `docs/contracts.md` C2 and `docs/datamodel.md` §10. The shape produced
by `packages/adapters/cli.py redfin --week current` (writing
`data/YYYY-MM-DD.json`) MUST round-trip through:

    pydantic.TypeAdapter(SnapshotFile).validate_python(payload)

CI runs that on every committed file (see `.github/workflows/ci.yml`).

The `data_quality` block on every `CitySnapshot` is non-optional per NF-DAT-01.
`freshness_tier` enum follows NF-DAT-06.

Bumping any field here requires bumping `SCHEMA_VERSION` (per `docs/contracts.md`
"Update protocol").
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Bump on any breaking change to the JSON shape below.
# v1: as_of_week (ISO YYYY-Www) — original Redfin weekly source.
# v2: as_of_period (ISO YYYY-Www OR YYYY-MM) — Redfin retired the public
#     weekly file in 2026; we shifted to the monthly city tracker, which
#     emits month-keyed periods instead of ISO weeks.
SCHEMA_VERSION: int = 2


# ── Enums ───────────────────────────────────────────────────────────────────


class FreshnessTier(StrEnum):
    """Per NF-DAT-06: how fresh data of this tier should be at any given time.

    The adapter that produced a metric is responsible for stamping it with its
    own tier (e.g. Redfin CSV is `weekly`, FRED rates are `daily`, MLS feed is
    `realtime`). The serving layer uses this for freshness badges and for the
    per-tier SLA tracker on the status page.
    """

    REALTIME = "realtime"
    NEAR_REALTIME = "near_realtime"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    ANNUAL = "annual"


# ── Building blocks ─────────────────────────────────────────────────────────


# Money modeled as `Decimal` (no float drift); JSON serializes as string per
# `docs/contracts.md` C3 ("Money is `Decimal` in Python and a string in TS JSON").
Money = Annotated[Decimal, Field(ge=0)]


class MetricsBlock(BaseModel):
    """Per-property-type market stats for a single city + period.

    Mirrors `MarketSnapshot` columns from `docs/datamodel.md` §6 but trimmed to
    the subset Redfin's weekly CSV exposes today. Fields are individually
    optional because Redfin's CSV occasionally drops a metric for a week (small
    metro, holiday); we want a partial record over a parse failure.
    """

    model_config = ConfigDict(extra="forbid")

    median_price: Money | None = None
    median_ppsf: Money | None = None
    yoy_pct: Decimal | None = None
    dom: int | None = Field(default=None, ge=0)
    sale_to_list: Decimal | None = Field(default=None, ge=0)
    homes_sold: int | None = Field(default=None, ge=0)
    active_listings: int | None = Field(default=None, ge=0)
    new_listings: int | None = Field(default=None, ge=0)
    months_of_supply: Decimal | None = Field(default=None, ge=0)
    pct_with_price_drops: Decimal | None = Field(default=None, ge=0, le=100)
    median_drop_pct: Decimal | None = Field(default=None, ge=0, le=100)


class DataQuality(BaseModel):
    """Provenance + confidence block, non-optional per NF-DAT-01.

    `sources` is a list of `"<source_name>:<source_period>"` strings — e.g.
    `"redfin_csv:2026-w17"`. The status page reads this to render per-source
    health. `confidence` is 0-100 (`packages/finance/confidence.py` formula).
    """

    model_config = ConfigDict(extra="forbid")

    sources: Annotated[list[str], Field(min_length=1)]
    as_of: date
    confidence: Annotated[int, Field(ge=0, le=100)]
    freshness_tier: FreshnessTier

    @field_validator("sources")
    @classmethod
    def _no_blank_sources(cls, v: list[str]) -> list[str]:
        if any(not s or not s.strip() for s in v):
            raise ValueError("`sources` entries must be non-empty strings")
        return v


class CitySnapshot(BaseModel):
    """One city's row in the snapshot file.

    `condo` is intentionally `None` (omitted) when no real condo data is
    available — Phase 2's design.md §10.7.6 explicitly forbids the
    `MANUAL_CONDO_NOTES` hack from the prototype.
    """

    model_config = ConfigDict(extra="forbid")

    slug: Annotated[str, Field(pattern=r"^[a-z0-9-]+$", min_length=1)]
    name: Annotated[str, Field(min_length=1)]
    county: Annotated[str, Field(min_length=1)]
    metro: Annotated[str, Field(pattern=r"^[a-z0-9-]+$", min_length=1)]
    sfh: MetricsBlock | None = None
    condo: MetricsBlock | None = None
    data_quality: DataQuality


class SnapshotFile(BaseModel):
    """Top-level container for `data/YYYY-MM-DD.json`.

    Filename date == ETL run date (UTC) per Phase 0 plan.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: int = SCHEMA_VERSION
    # Either ISO week (`2026-W19`) or ISO month (`2026-04`) — the adapter
    # producing the file picks one based on its source's native cadence.
    # Redfin's monthly city tracker → month; future weekly sources → week.
    as_of_period: Annotated[str, Field(pattern=r"^(\d{4}-W\d{2}|\d{4}-\d{2})$")]
    scraped_at: datetime
    cities: Annotated[list[CitySnapshot], Field(min_length=1)]

    @field_validator("schema_version")
    @classmethod
    def _check_schema_version(cls, v: int) -> int:
        if v != SCHEMA_VERSION:
            raise ValueError(
                f"schema_version {v} does not match current SCHEMA_VERSION {SCHEMA_VERSION}; "
                "this file may be from a different release. Upgrade or migrate."
            )
        return v
