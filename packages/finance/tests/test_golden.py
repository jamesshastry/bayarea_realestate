"""Golden-file parity tests.

For each finance function, ``tests/golden/inputs.json`` carries 100
deterministically-generated rows (a mix of hand-picked corner cases and
parametric sweeps). ``tests/golden/outputs.json`` carries the exact
output for each row, computed by running the current Python
implementation.

Per ``docs/contracts.md`` C3 the TS port (Agent D) consumes the *same*
``inputs.json`` and must produce byte-equal ``outputs.json`` content;
golden-file tests on both sides assert byte-equal output for the fixed
input matrix and fail CI on drift.

This test file:
1. Loads ``inputs.json``.
2. Runs the current Python implementation.
3. Compares against ``outputs.json``.

To regenerate ``outputs.json`` after a deliberate change, run
``python -m finance.tests.regen_golden`` (helper exposed below as a
``__main__`` entry point in this module).
"""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from finance._types import (
    AreaContext,
    Buyer,
    County,
    MarketContext,
    MetricValue,
    PhaseHistory,
    SnapshotForPhase,
    WaitParams,
)
from finance.affordability import affordability, monthly_cost
from finance.confidence import confidence_score
from finance.cost_of_waiting import cost_of_waiting
from finance.timing import compute_phase

GOLDEN_DIR = Path(__file__).parent / "golden"
INPUTS_PATH = GOLDEN_DIR / "inputs.json"
OUTPUTS_PATH = GOLDEN_DIR / "outputs.json"


# ---------------------------------------------------------------------------
# JSON encoding (Decimal → string; dataclass → dict)
# ---------------------------------------------------------------------------


def _encode(obj: Any) -> Any:
    """Recursively encode dataclasses and Decimals for stable JSON output.

    - ``Decimal`` → string (preserves precision; matches the TS port's
      ``string`` serialization).
    - dataclass → dict via ``asdict``, then recursively re-encoded.
    - tuple/list → list of encoded items.
    - dict → dict with encoded values; keys are stringified if needed.
    - Enum → ``.value``.
    - Anything else → returned as-is (numbers, strings, bools, None).
    """

    if isinstance(obj, Decimal):
        # Normalize so "1.00" and "1.0" don't drift; quantize sticks.
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


# ---------------------------------------------------------------------------
# Input deserialization
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Run all rows
# ---------------------------------------------------------------------------


def _run_row(row: dict[str, Any]) -> dict[str, Any]:
    """Dispatch on ``row["function"]`` and run the matching call."""

    fn = row["function"]
    inp = row["input"]

    if fn == "affordability":
        result = affordability(_build_buyer(inp["buyer"]), _build_market(inp["market_ctx"]))
        return _encode(result)
    if fn == "monthly_cost":
        result = monthly_cost(_to_decimal(inp["price"]), _build_area(inp["area_ctx"]))
        return _encode(result)
    if fn == "compute_phase":
        result = compute_phase(_build_snapshot(inp["snapshot"]), _build_history(inp["history"]))
        return _encode(result)
    if fn == "cost_of_waiting":
        result = cost_of_waiting(
            _build_buyer(inp["buyer"]),
            inp["area_id"],
            _build_wait_params(inp["params"]),
        )
        return _encode(result)
    if fn == "confidence_score":
        d = inp.get("disagreement")
        disagreement: Decimal | None = None if d is None else Decimal(str(d))
        result = confidence_score(
            _build_metric(inp["metric"]),
            int(inp["age_days"]),
            disagreement,
        )
        return _encode(result)
    raise ValueError(f"Unknown function in row: {fn}")


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text())


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("row_index", range(100))
def test_golden_row(row_index: int) -> None:
    """Each of the 100 rows produces the expected output."""

    inputs = _load_json(INPUTS_PATH)
    outputs = _load_json(OUTPUTS_PATH)
    assert len(inputs) == 100, f"inputs.json must have exactly 100 rows, got {len(inputs)}"
    assert len(outputs) == 100, f"outputs.json must have exactly 100 rows, got {len(outputs)}"

    row = inputs[row_index]
    expected = outputs[row_index]
    actual = _run_row(row)

    assert actual == expected["output"], (
        f"Row {row_index} ({row['function']}): output drift detected. "
        f"Expected {expected['output']!r}, got {actual!r}"
    )


def test_golden_files_have_matching_function_lists() -> None:
    inputs = _load_json(INPUTS_PATH)
    outputs = _load_json(OUTPUTS_PATH)
    in_fns = [r["function"] for r in inputs]
    out_fns = [r["function"] for r in outputs]
    assert in_fns == out_fns


# ---------------------------------------------------------------------------
# Regeneration helper
# ---------------------------------------------------------------------------
#
# Kept here (rather than a separate module) so the golden generator and
# the golden-file consumer evolve as one unit. Run with:
#
#     python -m finance.tests.test_golden --regen
#
# The regen path is gated behind an explicit flag so a stray test
# invocation can never overwrite the golden file.


def _regen() -> None:  # pragma: no cover - dev-only helper
    inputs = _load_json(INPUTS_PATH)
    outputs = []
    for row in inputs:
        output = _run_row(row)
        outputs.append({"function": row["function"], "output": output})
    OUTPUTS_PATH.write_text(json.dumps(outputs, indent=2, sort_keys=True))


if __name__ == "__main__":  # pragma: no cover
    import sys

    if "--regen" in sys.argv:
        _regen()
    else:
        print("Run with --regen to regenerate outputs.json from inputs.json.")
