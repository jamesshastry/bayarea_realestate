"""SchoolDistrict (`docs/datamodel.md` §4.1)."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import JSON, ForeignKey, Integer, Numeric, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from bayre_api.models.base import Base


class SchoolDistrict(Base):
    __tablename__ = "school_district"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    cds_code: Mapped[str | None] = mapped_column(String, unique=True, nullable=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    # `area_id` points to a GeographicArea row of kind='school_district' — that
    # row holds the boundary geometry (per the polymorphic design).
    area_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("geographic_area.id"),
        nullable=False,
    )
    total_enrollment: Mapped[int | None] = mapped_column(Integer, nullable=True)
    per_pupil_spending: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    extra: Mapped[dict] = mapped_column(
        "metadata",
        JSONB().with_variant(JSON, "sqlite"),
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
