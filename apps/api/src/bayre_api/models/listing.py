"""Listing (`docs/datamodel.md` §5.2)."""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from bayre_api.models.base import Base, listing_status_enum, property_type_enum


class Listing(Base):
    """One listing event in a parcel's lifetime.

    `parcel_id` is nullable on purpose: sometimes we ingest a listing before we
    can match it to a parcel (parcel ingest lags Redfin). The matcher backfills
    the FK once the parcel exists.
    """

    __tablename__ = "listing"
    __table_args__ = (UniqueConstraint("source", "source_listing_id", name="uq_listing_source_id"),)

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    parcel_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("parcel.id"),
        nullable=True,
    )
    source: Mapped[str] = mapped_column(String, nullable=False)
    source_listing_id: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(listing_status_enum, nullable=False)
    property_type: Mapped[str] = mapped_column(property_type_enum, nullable=False)
    list_price: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    sold_price: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    list_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    pending_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    sold_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    off_market_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    beds: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    baths: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    sqft: Mapped[int | None] = mapped_column(Integer, nullable=True)
    year_built: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    days_on_market: Mapped[int | None] = mapped_column(Integer, nullable=True)
    price_drops: Mapped[list | None] = mapped_column(
        JSONB().with_variant(JSON, "sqlite"),
        nullable=True,
    )
    raw_payload: Mapped[dict | None] = mapped_column(
        JSONB().with_variant(JSON, "sqlite"),
        nullable=True,
    )
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
