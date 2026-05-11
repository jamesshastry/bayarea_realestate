"""Wire schemas for `/v1/status` (per `docs/design.md` §6.1, NF-DAT-08)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

SourceHealth = Literal["green", "yellow", "red", "unknown"]
FreshnessTier = Literal[
    "realtime",
    "near_realtime",
    "daily",
    "weekly",
    "monthly",
    "quarterly",
    "annual",
]


class SourceStatus(BaseModel):
    """Per-source last-fetch summary."""

    model_config = ConfigDict(extra="forbid")

    name: str
    display_name: str
    health: SourceHealth
    freshness_tier: FreshnessTier
    last_fetch_at: datetime | None = None
    last_success_at: datetime | None = None
    last_error: str | None = None
    expected_next_at: datetime | None = None


class StatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    overall: SourceHealth
    generated_at: datetime
    sources: list[SourceStatus]
