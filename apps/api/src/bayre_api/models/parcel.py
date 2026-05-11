"""Parcel (`docs/datamodel.md` §5.1)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from geoalchemy2 import Geometry
from sqlalchemy import (
    JSON,
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

from bayre_api.models.base import Base


class Parcel(Base):
    """Stable physical lot — house may have many listings over its life.

    `apn` (assessor's parcel number) is unique only within a county; the
    `(county_id, apn)` composite uniqueness reflects California's numbering.
    `city_id` and `neighborhood_id` are denormalized to skip a spatial join on
    the hot path (per `docs/datamodel.md` tenet #6).
    """

    __tablename__ = "parcel"
    __table_args__ = (UniqueConstraint("county_id", "apn", name="uq_parcel_county_apn"),)

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    apn: Mapped[str] = mapped_column(String, nullable=False)
    county_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("geographic_area.id"),
        nullable=False,
    )
    address: Mapped[str | None] = mapped_column(String, nullable=True)
    location: Mapped[object] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326),
        nullable=False,
    )
    lot_sqft: Mapped[int | None] = mapped_column(Integer, nullable=True)
    zoning: Mapped[str | None] = mapped_column(String, nullable=True)
    city_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("geographic_area.id"),
        nullable=True,
    )
    neighborhood_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("geographic_area.id"),
        nullable=True,
    )

    # Tax + special assessments
    base_assessed_value: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    base_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    current_tax_rate: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    mello_roos: Mapped[dict | None] = mapped_column(
        JSONB().with_variant(JSON, "sqlite"),
        nullable=True,
    )
    hoa: Mapped[dict | None] = mapped_column(
        JSONB().with_variant(JSON, "sqlite"),
        nullable=True,
    )
    ada_features: Mapped[dict | None] = mapped_column(
        JSONB().with_variant(JSON, "sqlite"),
        nullable=True,
    )
    raw_assessor: Mapped[dict | None] = mapped_column(
        JSONB().with_variant(JSON, "sqlite"),
        nullable=True,
    )
    source: Mapped[str | None] = mapped_column(String, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
