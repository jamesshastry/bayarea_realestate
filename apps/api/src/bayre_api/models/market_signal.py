"""MarketSignal (`docs/datamodel.md` §6b) — append-only event log.

`BIGSERIAL` (not UUID) so cursor-based subscription replay (`WHERE id > :n`)
is monotonic and cheap; mirrors RESO's EntityEventSequence pattern.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    SmallInteger,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from bayre_api.models.base import Base, property_type_enum, signal_kind_enum


class MarketSignal(Base):
    __tablename__ = "market_signal"
    __table_args__ = (
        # Hot path: per-area "what changed" feed.
        Index("idx_signal_area_time", "area_id", "computed_at"),
        # Per-kind queries.
        Index("idx_signal_kind_time", "kind", "computed_at"),
        # Note: the dedupe UNIQUE constraint
        #   UNIQUE (area_id, kind, (payload->>'dedupe_key'), computed_at::date)
        # involves expression indexes that SQLAlchemy can't ergonomically express;
        # it lives in the Alembic migration as raw DDL.
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )
    area_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("geographic_area.id"),
        nullable=False,
    )
    property_type: Mapped[str | None] = mapped_column(property_type_enum, nullable=True)
    kind: Mapped[str] = mapped_column(signal_kind_enum, nullable=False)
    severity: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    source_snapshot_ids: Mapped[list[UUID]] = mapped_column(
        ARRAY(PGUUID(as_uuid=True)),
        nullable=False,
    )
    source_fetch_ids: Mapped[list[UUID] | None] = mapped_column(
        ARRAY(PGUUID(as_uuid=True)),
        nullable=True,
    )
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    # Phase 6 slot-in: MLS-driven listing signals carry the source listing.
    source_listing_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("listing.id"),
        nullable=True,
    )
