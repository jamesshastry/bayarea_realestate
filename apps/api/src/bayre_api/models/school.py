"""School (`docs/datamodel.md` §4.2)."""

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
    SmallInteger,
    String,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import INT4RANGE, JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from bayre_api.models.base import Base, school_level_enum


class School(Base):
    __tablename__ = "school"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    district_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("school_district.id"),
        nullable=False,
    )
    cds_code: Mapped[str | None] = mapped_column(String, unique=True, nullable=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    level: Mapped[str] = mapped_column(school_level_enum, nullable=False)
    # `INT4RANGE` per spec — e.g. '[9,12]' for a high school.
    grades: Mapped[object | None] = mapped_column(INT4RANGE, nullable=True)
    address: Mapped[str | None] = mapped_column(String, nullable=True)
    location: Mapped[object | None] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326),
        nullable=True,
    )
    enrollment: Mapped[int | None] = mapped_column(Integer, nullable=True)
    student_teacher_ratio: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    ratings: Mapped[dict] = mapped_column(
        JSONB().with_variant(JSON, "sqlite"),
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    data_quality_score: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    feeder_pattern: Mapped[dict | None] = mapped_column(
        JSONB().with_variant(JSON, "sqlite"),
        nullable=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
