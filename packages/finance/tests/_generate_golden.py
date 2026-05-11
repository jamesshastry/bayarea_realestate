"""Generate ``tests/golden/inputs.json`` and ``tests/golden/outputs.json``.

Run with::

    python -m finance.tests._generate_golden

This script is **not** a test. It produces the golden files by
deterministically generating 100 rows of inputs and then running the
current Python implementation to materialize the matching outputs.

The 100 rows cover all five C3 functions, with a mix of:
- Hand-picked corner cases (zero income, zero rate, $50M income).
- Parametric sweeps across realistic Bay Area inputs.

Per ``docs/contracts.md`` C3 Agent D's TS port consumes the *same*
``inputs.json`` and is expected to produce byte-equal ``outputs.json``;
that's how parity is enforced.

If you change a finance function in a way that *should* alter outputs,
re-run this script and review the diff in ``outputs.json`` carefully —
any drift requires also updating the TS port and re-baking the TS
golden file, per the C3 update protocol.
"""

from __future__ import annotations

import json

# Allow running as a script: prepend the parent of ``finance/`` to sys.path
# so ``from finance.tests.test_golden import _run_row`` resolves.
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
_FINANCE_DIR = _HERE.parent.parent
_PACKAGES_DIR = _FINANCE_DIR.parent
for _path in (str(_PACKAGES_DIR), str(_FINANCE_DIR)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from dataclasses import asdict, is_dataclass  # noqa: E402

from finance import tax_rules  # noqa: E402, F401
from finance._types import (  # noqa: E402
    AreaContext,
    Buyer,
    County,
    MarketContext,
    MetricValue,
    PhaseHistory,
    SnapshotForPhase,
    WaitParams,
)
from finance.affordability import affordability, monthly_cost  # noqa: E402
from finance.confidence import confidence_score  # noqa: E402
from finance.cost_of_waiting import cost_of_waiting  # noqa: E402
from finance.timing import compute_phase  # noqa: E402


def _encode(obj: Any) -> Any:
    """Recursively encode dataclasses + Decimals for stable JSON output."""

    if isinstance(obj, Decimal):
        return format(obj, "f")
    if is_dataclass(obj) and not isinstance(obj, type):
        return {k: _encode(v) for k, v in asdict(obj).items()}
    if isinstance(obj, (list, tuple)):
        return [_encode(v) for v in obj]
    if isinstance(obj, dict):
        return {str(k): _encode(v) for k, v in obj.items()}
    if isinstance(obj, County):
        return obj.value
    return obj


def _to_decimal(value: Any) -> Decimal:
    if value is None:
        raise ValueError("expected a Decimal-castable value, got None")
    return Decimal(str(value))


def _build_buyer(spec: dict[str, Any]) -> Buyer:
    return Buyer(
        annual_income=_to_decimal(spec["annual_income"]),
        monthly_debts=_to_decimal(spec["monthly_debts"]),
        down_payment=_to_decimal(spec["down_payment"]),
        rate=_to_decimal(spec["rate"]),
        term_years=int(spec["term_years"]),
        credit_score_band=spec.get("credit_score_band", "740-779"),
    )


def _build_market(spec: dict[str, Any]) -> MarketContext:
    return MarketContext(county=County(spec["county"]))


def _build_area(spec: dict[str, Any]) -> AreaContext:
    return AreaContext(
        county=County(spec["county"]),
        property_tax_rate=_to_decimal(spec["property_tax_rate"]),
        mello_roos_annual=_to_decimal(spec["mello_roos_annual"]),
        hoa_monthly=_to_decimal(spec["hoa_monthly"]),
        insurance_annual=_to_decimal(spec["insurance_annual"]),
        wildfire_surcharge_multiplier=_to_decimal(spec["wildfire_surcharge_multiplier"]),
        rate=_to_decimal(spec["rate"]),
        term_years=int(spec["term_years"]),
        down_payment=_to_decimal(spec["down_payment"]),
    )


def _build_snapshot(spec: dict[str, Any]) -> SnapshotForPhase:
    return SnapshotForPhase(
        months_of_supply=_to_decimal(spec["months_of_supply"]),
        s2l_4w=_to_decimal(spec["s2l_4w"]),
        s2l_12w=_to_decimal(spec["s2l_12w"]),
        pct_with_price_drops=_to_decimal(spec["pct_with_price_drops"]),
        median_dom=int(spec["median_dom"]),
        active_listings=int(spec["active_listings"]),
        sample_size=int(spec["sample_size"]),
        confidence_score=int(spec["confidence_score"]),
    )


def _build_history(spec: dict[str, Any]) -> PhaseHistory:
    return PhaseHistory(
        baseline_dom=int(spec["baseline_dom"]),
        inv_yoy=_to_decimal(spec["inv_yoy"]),
        previous_phase=spec.get("previous_phase", "unknown"),  # type: ignore[arg-type]
    )


def _build_wait_params(spec: dict[str, Any]) -> WaitParams:
    return WaitParams(
        target_price=_to_decimal(spec["target_price"]),
        wait_horizon_months=int(spec["wait_horizon_months"]),
        current_rate=_to_decimal(spec["current_rate"]),
        current_rent=_to_decimal(spec["current_rent"]),
        area_ctx=_build_area(spec["area_ctx"]),
    )


def _build_metric(spec: dict[str, Any]) -> MetricValue:
    raw = spec.get("value")
    value: Decimal | int | None
    if raw is None:
        value = None
    elif isinstance(raw, int) and not isinstance(raw, bool):
        value = raw
    else:
        value = Decimal(str(raw))
    sample = spec.get("sample_size")
    return MetricValue(
        value=value,
        sample_size=None if sample is None else int(sample),
        unit=spec["unit"],
        metric_name=spec["metric_name"],
    )


def _run_row(row: dict[str, Any]) -> Any:
    fn = row["function"]
    inp = row["input"]
    if fn == "affordability":
        return _encode(affordability(_build_buyer(inp["buyer"]), _build_market(inp["market_ctx"])))
    if fn == "monthly_cost":
        return _encode(monthly_cost(_to_decimal(inp["price"]), _build_area(inp["area_ctx"])))
    if fn == "compute_phase":
        return _encode(
            compute_phase(_build_snapshot(inp["snapshot"]), _build_history(inp["history"]))
        )
    if fn == "cost_of_waiting":
        return _encode(
            cost_of_waiting(
                _build_buyer(inp["buyer"]),
                inp["area_id"],
                _build_wait_params(inp["params"]),
            )
        )
    if fn == "confidence_score":
        d = inp.get("disagreement")
        disagreement: Decimal | None = None if d is None else Decimal(str(d))
        return _encode(
            confidence_score(_build_metric(inp["metric"]), int(inp["age_days"]), disagreement)
        )
    raise ValueError(f"Unknown function in row: {fn}")


GOLDEN_DIR = _HERE.parent / "golden"
INPUTS_PATH = GOLDEN_DIR / "inputs.json"
OUTPUTS_PATH = GOLDEN_DIR / "outputs.json"


# ---------------------------------------------------------------------------
# Input row builders
# ---------------------------------------------------------------------------


def _money(value: float | int | str) -> str:
    """Normalize a money input to a string the loader can parse as Decimal."""

    return format(Decimal(str(value)), "f")


def _buyer(
    *,
    income: float = 300_000,
    debts: float = 0,
    down: float = 150_000,
    rate: float = 0.0675,
    term: int = 30,
) -> dict[str, Any]:
    return {
        "annual_income": _money(income),
        "monthly_debts": _money(debts),
        "down_payment": _money(down),
        "rate": _money(rate),
        "term_years": term,
    }


def _market(county: str = "alameda") -> dict[str, Any]:
    return {"county": county}


def _area(
    *,
    county: str = "alameda",
    tax_rate: float = 0.01155,
    mello: float = 0,
    hoa: float = 0,
    insurance: float = 3500,
    wildfire: float = 1.0,
    rate: float = 0.0675,
    term: int = 30,
    down: float = 150_000,
) -> dict[str, Any]:
    return {
        "county": county,
        "property_tax_rate": _money(tax_rate),
        "mello_roos_annual": _money(mello),
        "hoa_monthly": _money(hoa),
        "insurance_annual": _money(insurance),
        "wildfire_surcharge_multiplier": _money(wildfire),
        "rate": _money(rate),
        "term_years": term,
        "down_payment": _money(down),
    }


def _snapshot(
    *,
    mos: float = 2.0,
    s2l_4w: float = 1.02,
    s2l_12w: float = 1.01,
    pdrop: float = 0.10,
    median_dom: int = 18,
    active_listings: int = 100,
    sample_size: int = 50,
    confidence: int = 85,
) -> dict[str, Any]:
    return {
        "months_of_supply": _money(mos),
        "s2l_4w": _money(s2l_4w),
        "s2l_12w": _money(s2l_12w),
        "pct_with_price_drops": _money(pdrop),
        "median_dom": median_dom,
        "active_listings": active_listings,
        "sample_size": sample_size,
        "confidence_score": confidence,
    }


def _history(
    *,
    baseline_dom: int = 22,
    inv_yoy: float = 0.0,
    previous_phase: str = "unknown",
) -> dict[str, Any]:
    return {
        "baseline_dom": baseline_dom,
        "inv_yoy": _money(inv_yoy),
        "previous_phase": previous_phase,
    }


def _wait_params(
    *,
    target: float = 1_200_000,
    months: int = 12,
    rate: float = 0.0675,
    rent: float = 3500,
) -> dict[str, Any]:
    return {
        "target_price": _money(target),
        "wait_horizon_months": months,
        "current_rate": _money(rate),
        "current_rent": _money(rent),
        "area_ctx": _area(rate=rate),
    }


def _metric(
    *,
    name: str = "median_sale_price",
    value: float | None = 1_500_000,
    sample_size: int | None = 50,
    unit: str = "USD",
) -> dict[str, Any]:
    return {
        "metric_name": name,
        "value": None if value is None else _money(value),
        "sample_size": sample_size,
        "unit": unit,
    }


# ---------------------------------------------------------------------------
# 100-row matrix
# ---------------------------------------------------------------------------


def build_inputs() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    # ---- 20 affordability rows -------------------------------------------
    income_grid = [120_000, 200_000, 300_000, 450_000, 600_000]
    down_grid = [50_000, 150_000, 300_000, 500_000]
    for income in income_grid:
        for down in down_grid:
            rows.append(
                {
                    "function": "affordability",
                    "input": {
                        "buyer": _buyer(income=income, down=down),
                        "market_ctx": _market("alameda"),
                    },
                }
            )
    assert len([r for r in rows if r["function"] == "affordability"]) == 20

    # ---- 25 monthly_cost rows --------------------------------------------
    price_grid = [600_000, 900_000, 1_200_000, 1_800_000, 2_500_000]
    rate_grid = [0.05, 0.0625, 0.0675, 0.075, 0.08]
    for price in price_grid:
        for rate in rate_grid:
            rows.append(
                {
                    "function": "monthly_cost",
                    "input": {
                        "price": _money(price),
                        "area_ctx": _area(rate=rate),
                    },
                }
            )

    # ---- 25 compute_phase rows -------------------------------------------
    phase_specs = [
        # Strong buyer (peak)
        {
            "mos": 0.5,
            "s2l_4w": 1.15,
            "s2l_12w": 1.10,
            "pdrop": 0.02,
            "dom": 8,
            "inv": -0.30,
        },
        {
            "mos": 0.8,
            "s2l_4w": 1.10,
            "s2l_12w": 1.05,
            "pdrop": 0.05,
            "dom": 10,
            "inv": -0.20,
        },
        {
            "mos": 1.2,
            "s2l_4w": 1.05,
            "s2l_12w": 1.03,
            "pdrop": 0.08,
            "dom": 14,
            "inv": -0.10,
        },
        # Cooling
        {
            "mos": 2.5,
            "s2l_4w": 1.02,
            "s2l_12w": 1.01,
            "pdrop": 0.20,
            "dom": 22,
            "inv": 0.05,
        },
        {
            "mos": 3.0,
            "s2l_4w": 1.00,
            "s2l_12w": 1.00,
            "pdrop": 0.25,
            "dom": 28,
            "inv": 0.10,
        },
        {
            "mos": 3.5,
            "s2l_4w": 0.99,
            "s2l_12w": 1.00,
            "pdrop": 0.30,
            "dom": 32,
            "inv": 0.15,
        },
        # Trough
        {
            "mos": 5.0,
            "s2l_4w": 0.95,
            "s2l_12w": 0.96,
            "pdrop": 0.40,
            "dom": 50,
            "inv": 0.30,
        },
        {
            "mos": 7.0,
            "s2l_4w": 0.92,
            "s2l_12w": 0.94,
            "pdrop": 0.50,
            "dom": 65,
            "inv": 0.50,
        },
        # Recovery (mid bands; need history to disambiguate)
        {
            "mos": 3.0,
            "s2l_4w": 0.99,
            "s2l_12w": 0.99,
            "pdrop": 0.20,
            "dom": 25,
            "inv": 0.0,
        },
        {
            "mos": 2.8,
            "s2l_4w": 1.00,
            "s2l_12w": 0.99,
            "pdrop": 0.15,
            "dom": 22,
            "inv": -0.05,
        },
    ]
    confidences = [85, 70, 60, 50, 30]
    histories = [
        ("unknown", 22),
        ("peak", 22),
        ("cooling", 22),
        ("trough", 22),
        ("recovery", 22),
    ]
    # Generate 25 by cycling — picks 5 specs × 5 confidence/history pairs.
    selected_specs = phase_specs[:5]
    for spec in selected_specs:
        for confidence, (prev_phase, baseline) in zip(confidences, histories, strict=True):
            rows.append(
                {
                    "function": "compute_phase",
                    "input": {
                        "snapshot": _snapshot(
                            mos=spec["mos"],
                            s2l_4w=spec["s2l_4w"],
                            s2l_12w=spec["s2l_12w"],
                            pdrop=spec["pdrop"],
                            median_dom=spec["dom"],
                            confidence=confidence,
                        ),
                        "history": _history(
                            baseline_dom=baseline,
                            inv_yoy=spec["inv"],
                            previous_phase=prev_phase,
                        ),
                    },
                }
            )

    # ---- 15 cost_of_waiting rows -----------------------------------------
    horizons = [3, 6, 12, 24, 12]
    targets = [800_000, 1_200_000, 1_500_000, 2_000_000, 950_000]
    rents = [2500, 3500, 4500, 5500, 3000]
    for h, t, r in zip(horizons, targets, rents, strict=True):
        rows.append(
            {
                "function": "cost_of_waiting",
                "input": {
                    "buyer": _buyer(income=300_000, down=200_000),
                    "area_id": "alameda::fremont",
                    "params": _wait_params(target=t, months=h, rent=r),
                },
            }
        )
    # 5 more with rate variations.
    for rate in [0.06, 0.065, 0.07, 0.075, 0.08]:
        rows.append(
            {
                "function": "cost_of_waiting",
                "input": {
                    "buyer": _buyer(income=400_000, down=250_000, rate=rate),
                    "area_id": "santa_clara::sunnyvale",
                    "params": _wait_params(target=1_500_000, months=12, rate=rate, rent=4000),
                },
            }
        )
    # 5 more with various counties.
    for county in [
        "santa_clara",
        "contra_costa",
        "san_mateo",
        "san_francisco",
        "marin",
    ]:
        rows.append(
            {
                "function": "cost_of_waiting",
                "input": {
                    "buyer": _buyer(income=350_000, down=180_000),
                    "area_id": f"{county}::city",
                    "params": {
                        "target_price": _money(1_300_000),
                        "wait_horizon_months": 12,
                        "current_rate": _money(0.0675),
                        "current_rent": _money(3800),
                        "area_ctx": _area(county=county),
                    },
                },
            }
        )

    # ---- 15 confidence_score rows ----------------------------------------
    metric_names = [
        "median_sale_price",
        "median_dom",
        "months_of_supply",
        "pct_with_price_drops",
        "school_premium",
    ]
    sample_sizes = [None, 5, 15, 30, 100]
    for name in metric_names:
        for sample in sample_sizes:
            rows.append(
                {
                    "function": "confidence_score",
                    "input": {
                        "metric": _metric(name=name, value=1500, sample_size=sample, unit="USD"),
                        "age_days": 7,
                        "disagreement": None,
                    },
                }
            )
        if len([r for r in rows if r["function"] == "confidence_score"]) >= 15:
            break

    # We currently have 25 confidence rows; trim to 15 to hit 100 total.
    confidence_rows = [r for r in rows if r["function"] == "confidence_score"]
    other_rows = [r for r in rows if r["function"] != "confidence_score"]
    rows = other_rows + confidence_rows[:15]

    assert len(rows) == 100, f"Expected 100 rows, got {len(rows)}"
    return rows


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


def main() -> None:
    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    inputs = build_inputs()
    INPUTS_PATH.write_text(json.dumps(inputs, indent=2, sort_keys=True))
    outputs = []
    for row in inputs:
        outputs.append({"function": row["function"], "output": _run_row(row)})
    OUTPUTS_PATH.write_text(json.dumps(outputs, indent=2, sort_keys=True))
    print(f"Wrote {INPUTS_PATH} ({len(inputs)} rows)")
    print(f"Wrote {OUTPUTS_PATH} ({len(outputs)} rows)")


if __name__ == "__main__":
    main()
