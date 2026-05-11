"""`/v1/finance/*` routes (per `docs/design.md` §6.1).

Phase 2 scaffold — these routes will eventually call into `packages/finance/`,
which is pure-function Python (95% coverage gate). The current handlers raise
501 NotImplemented; shapes are stable per `docs/contracts.md` C3.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from bayre_api.schemas.finance import (
    AffordabilityRequest,
    AffordabilityResult,
    CostOfWaitingRequest,
    CostOfWaitingResult,
    MonthlyCostRequest,
    MonthlyCostResult,
)

router = APIRouter(prefix="/v1/finance", tags=["finance"])


@router.post(
    "/affordability",
    response_model=AffordabilityResult,
    summary="Compute comfortable / stretch / max-by-loan-type for a buyer",
)
async def affordability(req: AffordabilityRequest) -> AffordabilityResult:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Phase 2: finance.affordability calls packages/finance — wire in Phase 1",
    )


@router.post(
    "/monthly-cost",
    response_model=MonthlyCostResult,
    summary="Decompose monthly housing cost (P&I + tax + Mello + HOA + insurance + PMI)",
)
async def monthly_cost(req: MonthlyCostRequest) -> MonthlyCostResult:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Phase 2: finance.monthly_cost calls packages/finance — wire in Phase 1",
    )


@router.post(
    "/cost-of-waiting",
    response_model=CostOfWaitingResult,
    summary="3×3 grid of (appreciation × rate) scenarios for waiting horizon",
)
async def cost_of_waiting(req: CostOfWaitingRequest) -> CostOfWaitingResult:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Phase 2: finance.cost_of_waiting calls packages/finance — wire in Phase 1",
    )
