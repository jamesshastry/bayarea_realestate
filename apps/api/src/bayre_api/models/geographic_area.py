"""GeographicArea — the polymorphic spine (`docs/datamodel.md` §3.1)."""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from geoalchemy2 import Geometry
from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from bayre_api.models.base import Base, geo_kind_enum


class GeographicArea(Base):
    """Cities, counties, neighborhoods, ZIPs, school zones — one table.

    `parent_id` is the *navigation* hierarchy (county → city → neighborhood),
    not the spatial one. Spatial relationships use PostGIS `ST_*` functions on
    `geometry`, which is GIST-indexed in the migration.

    `metro_id` is denormalized to the nearest `kind='metro'` ancestor so
    "everything in the Bay Area" is a single index scan.
    """

    __tablename__ = "geographic_area"
    __table_args__ = (
        UniqueConstraint("kind", "parent_id", "slug", name="uq_geo_kind_parent_slug"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    kind: Mapped[str] = mapped_column(geo_kind_enum, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    slug: Mapped[str] = mapped_column(String, nullable=False)
    parent_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("geographic_area.id"),
        nullable=True,
    )
    metro_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("geographic_area.id"),
        nullable=True,
    )

    # PostGIS columns — `geometry` is required (NOT NULL), but we leave it
    # nullable in the SQLAlchemy model so the Phase 2 seed migration can insert
    # the 18 priority rows without polygons (boundary ingest is a follow-up
    # ETL job). The migration will tighten this to NOT NULL once boundaries land.
    geometry: Mapped[object | None] = mapped_column(
        Geometry(geometry_type="MULTIPOLYGON", srid=4326),
        nullable=True,
    )
    centroid: Mapped[object | None] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326),
        nullable=True,
    )
    area_sqkm: Mapped[float | None] = mapped_column(Numeric, nullable=True)

    population: Mapped[int | None] = mapped_column(Integer, nullable=True)
    median_household_income: Mapped[float | None] = mapped_column(Numeric, nullable=True)

    # `metadata` is a reserved attribute name on Declarative — store as
    # `extra` in the ORM but keep the column name `metadata` per the spec.
    extra: Mapped[dict] = mapped_column(
        "metadata",
        JSONB().with_variant(JSON, "sqlite"),
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )

    source: Mapped[str | None] = mapped_column(String, nullable=True)
    effective_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
