"""`/v1/areas/*` routes (per `docs/design.md` §6.1).

Phase 2 scaffold — every route returns 501 NotImplemented but with the full
Pydantic response model attached, so the OpenAPI spec is complete from day
one and the Next.js codegen has typed clients to generate against.

Endpoints to implement:
- GET  /search                       AreaSearchResponse
- GET  /{id}                         AreaDetail
- GET  /{id}/snapshot                SnapshotResponse
- GET  /{id}/timeseries              TimeseriesResponse
"""

from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

from bayre_api.schemas.areas import (
    AreaDetail,
    AreaSearchResponse,
    PeriodKind,
    PropertyType,
    SnapshotResponse,
    TimeseriesResponse,
)

router = APIRouter(prefix="/v1/areas", tags=["areas"])


@router.get(
    "/search",
    response_model=AreaSearchResponse,
    summary="Search areas by name + kind",
)
async def search_areas(
    q: str = Query(..., min_length=1, max_length=100),
    kind: str | None = Query(None, description="Filter by GeoKind"),
    metro: str | None = Query(None, description="Filter by metro slug"),
    cursor: str | None = Query(None, description="Opaque pagination cursor"),
    limit: int = Query(20, ge=1, le=100),
) -> AreaSearchResponse:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Phase 2: areas.search not yet implemented",
    )


@router.get(
    "/{area_id}",
    response_model=AreaDetail,
    summary="Get one area by id",
)
async def get_area(area_id: UUID) -> AreaDetail:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Phase 2: areas.get not yet implemented",
    )


@router.get(
    "/{area_id}/snapshot",
    response_model=SnapshotResponse,
    summary="Latest snapshot for (area, property_type, period)",
)
async def get_snapshot(
    area_id: UUID,
    property_type: PropertyType = Query("sfh"),
    period_kind: PeriodKind = Query("weekly"),
    period: str | None = Query(
        None,
        description="ISO period identifier (e.g. '2026-W19' or '2026-04'). Defaults to latest.",
    ),
) -> SnapshotResponse:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Phase 2: areas.snapshot not yet implemented",
    )


@router.get(
    "/{area_id}/timeseries",
    response_model=TimeseriesResponse,
    summary="Timeseries of one metric over a date range",
)
async def get_timeseries(
    area_id: UUID,
    metric: str = Query(..., examples=["median_sale_price"]),
    property_type: PropertyType = Query("sfh"),
    period_kind: PeriodKind = Query("monthly"),
    date_from: date | None = Query(None, alias="from"),
    date_to: date | None = Query(None, alias="to"),
) -> TimeseriesResponse:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Phase 2: areas.timeseries not yet implemented",
    )
