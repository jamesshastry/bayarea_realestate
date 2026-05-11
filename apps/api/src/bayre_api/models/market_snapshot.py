"""MarketSnapshot (`docs/datamodel.md` §6 + §6a).

Includes the Phase columns (`phase`, `clock_position`, `buyer_pressure`,
`seller_pressure`, `phase_components`) — these are populated by
`packages/finance/timing.py::compute_phase` after each insert.
"""

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
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from bayre_api.models.base import (
    Base,
    market_phase_enum,
    period_kind_enum,
    property_type_enum,
)


class MarketSnapshot(Base):
    __tablename__ = "market_snapshot"
    __table_args__ = (
        UniqueConstraint(
            "area_id",
            "property_type",
            "period_kind",
            "period_start",
            name="uq_snapshot_area_type_period",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    area_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("geographic_area.id"),
        nullable=False,
    )
    property_type: Mapped[str] = mapped_column(property_type_enum, nullable=False)
    period_kind: Mapped[str] = mapped_column(period_kind_enum, nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)

    # Core stats
    median_sale_price: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    median_list_price: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    median_ppsf: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    sale_to_list_ratio: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    pct_sold_over_asking: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    median_dom: Mapped[int | None] = mapped_column(Integer, nullable=True)
    homes_sold: Mapped[int | None] = mapped_column(Integer, nullable=True)
    active_listings: Mapped[int | None] = mapped_column(Integer, nullable=True)
    new_listings: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pending_sales: Mapped[int | None] = mapped_column(Integer, nullable=True)
    months_of_supply: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    pct_with_price_drops: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    median_drop_pct: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    median_size_sqft: Mapped[int | None] = mapped_column(Integer, nullable=True)
    median_year_built: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)

    # Breakouts
    by_bedrooms: Mapped[dict | None] = mapped_column(
        JSONB().with_variant(JSON, "sqlite"),
        nullable=True,
    )
    percentiles: Mapped[dict | None] = mapped_column(
        JSONB().with_variant(JSON, "sqlite"),
        nullable=True,
    )

    # Provenance
    sample_size: Mapped[int] = mapped_column(Integer, nullable=False)
    confidence_score: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    source_versions: Mapped[dict] = mapped_column(
        JSONB().with_variant(JSON, "sqlite"),
        nullable=False,
    )
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # Phase classification (§6a)
    phase: Mapped[str | None] = mapped_column(market_phase_enum, nullable=True)
    clock_position: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    buyer_pressure: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    seller_pressure: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    phase_components: Mapped[dict | None] = mapped_column(
        JSONB().with_variant(JSON, "sqlite"),
        nullable=True,
    )
