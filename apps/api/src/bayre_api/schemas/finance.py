"""Wire schemas for `/v1/finance/*` (per `docs/design.md` §6.1, §5.1).

These mirror the function inventory in `packages/finance/` (see
`docs/contracts.md` C3); shapes are pinned now so the frontend codegen and
Phase-1 finance package don't drift.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

LoanType = Literal["conforming", "high_balance", "jumbo", "fha", "va"]
AffordabilityLevel = Literal["comfortable", "stretch", "unaffordable"]


# ── Affordability ──────────────────────────────────────────────────────────


class AffordabilityRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    annual_income: Annotated[Decimal, Field(gt=0)]
    monthly_debt: Annotated[Decimal, Field(ge=0)] = Decimal(0)
    down_payment: Annotated[Decimal, Field(ge=0)]
    rate: Annotated[Decimal, Field(gt=0, lt=1)]  # 0.0625 == 6.25%
    term_years: Annotated[int, Field(ge=10, le=40)] = 30
    county_slug: str | None = None
    property_type: Literal["sfh", "condo", "townhome"] = "sfh"


class AffordabilityResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    comfortable: Decimal
    stretch: Decimal
    max_by_loan_type: dict[LoanType, Decimal]


# ── Monthly cost ───────────────────────────────────────────────────────────


class MonthlyCostRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    price: Annotated[Decimal, Field(gt=0)]
    area_id: UUID
    down_payment: Annotated[Decimal, Field(ge=0)]
    rate: Annotated[Decimal, Field(gt=0, lt=1)]
    term_years: Annotated[int, Field(ge=10, le=40)] = 30


class MonthlyCostResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    p_and_i: Decimal
    tax: Decimal
    mello: Decimal
    hoa: Decimal
    insurance: Decimal
    pmi: Decimal
    total: Decimal


# ── Cost of waiting ────────────────────────────────────────────────────────


class CostOfWaitingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    area_id: UUID
    target_price: Decimal | None = None  # default: median for area
    horizon_months: Literal[3, 6, 12, 24] = 12
    current_rent: Annotated[Decimal, Field(ge=0)] = Decimal(0)
    rate: Annotated[Decimal, Field(gt=0, lt=1)]
    down_payment: Annotated[Decimal, Field(ge=0)]


class CostOfWaitingCell(BaseModel):
    """One cell in the 3×3 (appreciation × rate) grid."""

    model_config = ConfigDict(extra="forbid")

    appreciation_scenario: Literal["low", "base", "high"]
    rate_scenario: Literal["drop_50bp", "flat", "rise_50bp"]
    appreciation_change_dollars: Decimal
    rent_paid_during_wait: Decimal
    monthly_payment_now: Decimal
    monthly_payment_later: Decimal
    cumulative_savings_or_cost: Decimal
    break_even_rate_drop: Decimal
    net_dollar_impact: Decimal


class CostOfWaitingResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    horizon_months: int
    grid: list[CostOfWaitingCell]
