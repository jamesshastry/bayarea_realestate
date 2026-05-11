"""Typed period identifiers per `docs/datamodel.md` §6.

`Week` and `Month` are immutable value objects that round-trip cleanly through
JSON (ISO formats) and serve as the `Period` parameter on
`DataSourceAdapter.fetch(area, period)` (see `docs/contracts.md` C1).

We keep these as Pydantic models (rather than `dataclass(frozen=True)`) so they
serialize identically to the snapshot file format and can be embedded in other
Pydantic schemas without custom encoders.
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

# ── Week ────────────────────────────────────────────────────────────────────

_ISO_WEEK_RE = re.compile(r"^(?P<year>\d{4})-W(?P<week>\d{2})$")


class Week(BaseModel):
    """ISO-8601 calendar week: `YYYY-Www` (e.g. `2026-W19`).

    Following ISO-8601 / Python's `date.isocalendar()`:
    - weeks 1-53 (53 in long years)
    - week starts Monday
    - week 1 contains the year's first Thursday
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["week"] = "week"
    year: Annotated[int, Field(ge=1900, le=2999)]
    week: Annotated[int, Field(ge=1, le=53)]

    @model_validator(mode="after")
    def _validate_week_for_year(self) -> Self:
        # ISO weeks: a year has 52 or 53 weeks. Reject e.g. 2026-W53 if 2026 only has 52.
        max_week = date(self.year, 12, 28).isocalendar().week  # Dec 28 is always in last ISO week
        if self.week > max_week:
            raise ValueError(
                f"ISO week {self.week} does not exist in year {self.year} (max {max_week})"
            )
        return self

    @classmethod
    def parse(cls, s: str) -> Week:
        m = _ISO_WEEK_RE.match(s)
        if not m:
            raise ValueError(f"Not an ISO week string: {s!r} (expected YYYY-Www)")
        return cls(year=int(m["year"]), week=int(m["week"]))

    @classmethod
    def from_date(cls, d: date) -> Week:
        iso = d.isocalendar()
        return cls(year=iso.year, week=iso.week)

    @classmethod
    def current(cls, today: date | None = None) -> Week:
        return cls.from_date(today or date.today())

    def __str__(self) -> str:
        return f"{self.year}-W{self.week:02d}"

    def monday(self) -> date:
        """Date of the Monday that begins this ISO week."""
        return date.fromisocalendar(self.year, self.week, 1)

    def sunday(self) -> date:
        """Date of the Sunday that ends this ISO week."""
        return self.monday() + timedelta(days=6)


# ── Month ───────────────────────────────────────────────────────────────────

_MONTH_RE = re.compile(r"^(?P<year>\d{4})-(?P<month>\d{2})$")


class Month(BaseModel):
    """Calendar month: `YYYY-MM` (e.g. `2026-04`)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["month"] = "month"
    year: Annotated[int, Field(ge=1900, le=2999)]
    month: Annotated[int, Field(ge=1, le=12)]

    @classmethod
    def parse(cls, s: str) -> Month:
        m = _MONTH_RE.match(s)
        if not m:
            raise ValueError(f"Not a month string: {s!r} (expected YYYY-MM)")
        return cls(year=int(m["year"]), month=int(m["month"]))

    @classmethod
    def from_date(cls, d: date) -> Month:
        return cls(year=d.year, month=d.month)

    def __str__(self) -> str:
        return f"{self.year}-{self.month:02d}"


# Period union — what `DataSourceAdapter.fetch(area, period)` accepts.
# Discriminated by `kind` so JSON round-trip is unambiguous.
Period = Annotated[Week | Month, Field(discriminator="kind")]
