"""Minimal Pydantic stub for `GeographicArea` (`docs/datamodel.md` §3.1).

Phase 0 only needs the navigational fields — `id`, `slug`, `kind`, `name`,
`parent_id`. PostGIS columns (`geometry`, `centroid`, `area_sqkm`, etc.) are
deferred to Phase 2 when Postgres + PostGIS are provisioned and Alembic owns
the schema.

The `kind` enum here is the full list from `datamodel.md`; not all variants are
used in Phase 0 but pinning the surface now means downstream packages can
depend on it.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class GeoKind(StrEnum):
    METRO = "metro"
    COUNTY = "county"
    CITY = "city"
    NEIGHBORHOOD = "neighborhood"
    ZIP = "zip"
    SCHOOL_ZONE = "school_zone"
    SCHOOL_DISTRICT = "school_district"
    CUSTOM_POLYGON = "custom_polygon"


class GeographicArea(BaseModel):
    """Polymorphic area row (Phase 0 navigational subset).

    `id` is auto-generated via `default_factory=uuid4` so callers can omit it
    at construction time. We annotate `id` as `UUID | None` rather than
    `UUID` because pyright (strict, no Pydantic plugin) doesn't see Pydantic's
    runtime default-factory injection — declaring it Optional sidesteps that
    without changing runtime behavior (Pydantic still always supplies a UUID).
    Downstream consumers can rely on `id is not None` after construction.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID = Field(default_factory=uuid4)
    kind: GeoKind
    name: Annotated[str, Field(min_length=1)]
    slug: Annotated[str, Field(pattern=r"^[a-z0-9-]+$", min_length=1)]
    parent_id: UUID | None = None
