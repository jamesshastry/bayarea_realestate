"""Declarative base + shared SQL types.

Postgres ENUMs declared here (rather than per-model) so Alembic autogenerate
can detect them in one place and emit `CREATE TYPE` correctly. Every ENUM uses
``create_type=False`` because the initial migration creates them by hand to
control name + ordering; otherwise SQLAlchemy would emit an unnamed type per
column reuse.
"""

from __future__ import annotations

from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base; every model inherits from this."""


# ── Enum surfaces (mirror `docs/datamodel.md`) ─────────────────────────────
#
# `name=` values are the on-disk Postgres TYPE names. Keep these stable —
# renaming requires an Alembic migration with a `RENAME TYPE` step.
GEO_KIND_VALUES = (
    "metro",
    "county",
    "city",
    "neighborhood",
    "zip",
    "school_zone",
    "school_district",
    "custom_polygon",
)
geo_kind_enum = SAEnum(
    *GEO_KIND_VALUES,
    name="geo_kind",
    create_type=False,
    native_enum=True,
    validate_strings=True,
)

SCHOOL_LEVEL_VALUES = ("elementary", "middle", "high", "k12")
school_level_enum = SAEnum(
    *SCHOOL_LEVEL_VALUES,
    name="school_level",
    create_type=False,
    native_enum=True,
    validate_strings=True,
)

LISTING_STATUS_VALUES = (
    "active",
    "pending",
    "sold",
    "withdrawn",
    "expired",
    "unknown",
)
listing_status_enum = SAEnum(
    *LISTING_STATUS_VALUES,
    name="listing_status",
    create_type=False,
    native_enum=True,
    validate_strings=True,
)

PROPERTY_TYPE_VALUES = (
    "sfh",
    "condo",
    "townhome",
    "multifamily",
    "land",
    "mobile",
    "other",
)
property_type_enum = SAEnum(
    *PROPERTY_TYPE_VALUES,
    name="property_type",
    create_type=False,
    native_enum=True,
    validate_strings=True,
)

PERIOD_KIND_VALUES = ("weekly", "monthly", "quarterly", "yearly")
period_kind_enum = SAEnum(
    *PERIOD_KIND_VALUES,
    name="period_kind",
    create_type=False,
    native_enum=True,
    validate_strings=True,
)

MARKET_PHASE_VALUES = ("peak", "cooling", "trough", "recovery", "unknown")
market_phase_enum = SAEnum(
    *MARKET_PHASE_VALUES,
    name="market_phase",
    create_type=False,
    native_enum=True,
    validate_strings=True,
)

SIGNAL_KIND_VALUES = (
    # Phase 2+ (computed from snapshots)
    "phase_transition",
    "mos_threshold",
    "s2l_threshold",
    "dom_threshold",
    "inventory_spike",
    "price_drop_pct",
    # Phase 2+ (rate)
    "rate_threshold",
    # Phase 6 (MLS realtime)
    "new_listing",
    "price_change",
    "status_flip",
    "sold",
)
signal_kind_enum = SAEnum(
    *SIGNAL_KIND_VALUES,
    name="signal_kind",
    create_type=False,
    native_enum=True,
    validate_strings=True,
)
