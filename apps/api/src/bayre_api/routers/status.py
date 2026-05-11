"""`/v1/status` (per `docs/design.md` §6.1, NF-DAT-08).

Public status page data: per-source last-fetch time + green/red health
indicator. Reads from `data/sources.json` (Phase 0 artifact). When that file
is absent (fresh checkout), returns an empty status with `overall='unknown'`
so the route is always green for the smoke test.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends

from bayre_api.config import Settings, get_settings
from bayre_api.schemas.status import SourceStatus, StatusResponse

router = APIRouter(prefix="/v1", tags=["status"])


def _load_sources_json(repo_root: Path) -> dict[str, Any] | None:
    """Read `data/sources.json` if present; otherwise return None.

    The file is the Phase 0 status-page artifact (see
    `docs/implementation-plan.md` Phase 0 → "status page stub"). Phase 2
    deliberately keeps the same on-disk shape so this endpoint can serve
    until the `data_source` / `source_fetch` tables are populated.
    """
    path = repo_root / "data" / "sources.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


@router.get(
    "/status",
    response_model=StatusResponse,
    summary="Per-source ingest health (NF-DAT-08)",
)
async def get_status(settings: Settings = Depends(get_settings)) -> StatusResponse:
    raw = _load_sources_json(settings.repo_root)
    if raw is None:
        return StatusResponse(
            overall="unknown",
            generated_at=datetime.now(tz=UTC),
            sources=[],
        )

    # `data/sources.json` is written by `packages/observability/status_page.py`
    # using an *operational* shape (status: ok/partial/error, last_run_at,
    # successful_areas, failed_areas). The API surfaces a *consumer* shape
    # (health: green/yellow/red, last_fetch_at, last_success_at, last_error).
    # Mapping lives here so the on-disk format stays ergonomic for the static
    # status-page generator. Phase 2 ETL will replace this whole file with
    # `data_source` / `source_fetch` rows.
    raw_sources = raw.get("sources", [])
    items = list(raw_sources.values()) if isinstance(raw_sources, dict) else raw_sources
    sources = [_to_source_status(item) for item in items]

    # Overall = worst tier among sources.
    rank = {"red": 0, "yellow": 1, "unknown": 2, "green": 3}
    overall: str = "green"
    for s in sources:
        if rank.get(s.health, 2) < rank.get(overall, 2):
            overall = s.health

    return StatusResponse(
        overall=overall,  # type: ignore[arg-type]
        generated_at=datetime.now(tz=UTC),
        sources=sources,
    )


@router.get("/health", summary="Liveness probe", tags=["meta"])
async def health() -> dict[str, str]:
    """Cheap liveness probe — does NOT touch the DB."""
    return {"status": "ok"}


_OP_TO_HEALTH = {"ok": "green", "partial": "yellow", "error": "red"}
_DISPLAY_NAMES = {
    "redfin_csv": "Redfin Data Center (weekly CSV)",
    "fred_rates": "FRED 30Y mortgage rate",
    "cde_schools": "CA Dept of Education",
    "greatschools": "GreatSchools",
}


def _to_source_status(item: dict[str, Any]) -> SourceStatus:
    """Map the on-disk `SourceStatus` (operational) to the API one (consumer)."""
    name = str(item["name"])
    op_status = str(item.get("status", "ok"))
    last_run = item.get("last_run_at")
    failed = item.get("failed_areas") or {}
    first_error = next(iter(failed.values()), None) if failed else None
    return SourceStatus(
        name=name,
        display_name=_DISPLAY_NAMES.get(name) or name.replace("_", " ").title(),
        health=_OP_TO_HEALTH.get(op_status, "unknown"),  # type: ignore[arg-type]
        freshness_tier=item["freshness_tier"],
        last_fetch_at=last_run,
        last_success_at=last_run if op_status in {"ok", "partial"} else None,
        last_error=first_error,
        expected_next_at=None,  # Computed in Phase 2 from cron schedule
    )
