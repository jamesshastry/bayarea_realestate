"""SourceFetch (`docs/datamodel.md` §7.2) — every fetch logged."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Integer,
    String,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from bayre_api.models.base import Base


class SourceFetch(Base):
    __tablename__ = "source_fetch"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    source_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("data_source.id"),
        nullable=False,
    )
    area_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("geographic_area.id"),
        nullable=True,
    )
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    status: Mapped[str] = mapped_column(String, nullable=False)
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    payload_uri: Mapped[str | None] = mapped_column(String, nullable=True)
    payload_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rows_parsed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    parse_anomalies: Mapped[list | None] = mapped_column(
        JSONB().with_variant(JSON, "sqlite"),
        nullable=True,
    )
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(String, nullable=True)
