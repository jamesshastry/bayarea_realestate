"""Sale (`docs/datamodel.md` §5.3) — materialized view.

Mapped read-only here so the ORM can query it. The actual `CREATE
MATERIALIZED VIEW` lives in the Alembic migration; SQLAlchemy autogenerate
won't see it as a table.
"""

from __future__ import annotations

from datetime import date
from uuid import UUID

from geoalchemy2 import Geometry
from sqlalchemy import Date, Integer, Numeric, SmallInteger
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from bayre_api.models.base import Base, property_type_enum


class Sale(Base):
    """Read-only mapping of the `sale` materialized view."""

    __tablename__ = "sale"
    # Tell autogenerate not to emit DDL for this — the migration creates it
    # explicitly as a MATERIALIZED VIEW.
    __table_args__ = {"info": {"is_view": True}}  # noqa: RUF012  # SQLAlchemy convention

    listing_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    parcel_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    sold_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    sold_price: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    list_price: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    sale_to_list: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    days_on_market: Mapped[int | None] = mapped_column(Integer, nullable=True)
    property_type: Mapped[str | None] = mapped_column(property_type_enum, nullable=True)
    beds: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    baths: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    sqft: Mapped[int | None] = mapped_column(Integer, nullable=True)
    price_per_sqft: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    city_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    neighborhood_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True
    )
    county_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    location: Mapped[object | None] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326),
        nullable=True,
    )
