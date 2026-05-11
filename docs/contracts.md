# Inter-track contracts

> Status: Living doc · Owner: project lead · Last updated: 2026-05-11
> When parallel agents/teams build different layers, each layer's *interface* must be agreed before implementation. This file is that agreement. Update it in the same PR that changes the contract.

Cross-references: `docs/design.md` §3.1, §5.1, §6; `docs/datamodel.md` §6, §6a, §6b, §10.

---

## C1. `RawSnapshot` — adapter output

Every `DataSourceAdapter.fetch(area, period) -> RawSnapshot` must return the shape below. Bronze tier (raw payload caching) is the adapter's responsibility; the resolver consumes only the normalized fields.

```python
@dataclass(frozen=True)
class RawSnapshot:
    area_slug: str                  # matches GeographicArea.slug
    period: Period                  # week or month identifier
    metrics: dict[Capability, MetricValue]
    source: str                     # e.g. "redfin_csv"
    fetched_at: datetime            # UTC, when we pulled
    source_published_at: datetime   # UTC, when source publicly published
    bronze_path: str                # relative path to cached raw payload
```

```python
@dataclass(frozen=True)
class MetricValue:
    value: Decimal | int | None
    sample_size: int | None         # required for confidence scoring (design §5.2)
    unit: str                       # "USD", "USD/sqft", "days", "ratio", "months", "pct"
```

`Period` is a typed alias: `Week(year, iso_week)` or `Month(year, month)` per `datamodel.md` §6.

---

## C2. JSON snapshot file format (Phase 0 deliverable)

The Phase 0 weekly artifact is `data/YYYY-MM-DD.json` (date = ETL run date). Schema lives in `packages/domain/snapshot.py` as a Pydantic v2 model. Schema **MUST** match `datamodel.md` §10:

```json
{
  "schema_version": 1,
  "as_of_week": "2026-W19",
  "scraped_at": "2026-05-08T18:00:00Z",
  "cities": [
    {
      "slug": "fremont",
      "name": "Fremont",
      "county": "Alameda",
      "metro": "bay-area",
      "sfh": { "median_price": 1500000, "median_ppsf": 950, ... },
      "condo": { ... } | null,
      "data_quality": {
        "sources": ["redfin_csv:2026-w17"],
        "as_of": "2026-05-04",
        "confidence": 88,
        "freshness_tier": "weekly"
      }
    }
  ]
}
```

The `data_quality` block is **non-optional** per NF-DAT-01. `freshness_tier ∈ {"realtime", "near_realtime", "daily", "weekly", "monthly", "quarterly", "annual"}` per NF-DAT-06.

Validation: `pydantic.TypeAdapter(SnapshotFile).validate_python(payload)` must pass on every committed file. CI gate.

---

## C3. Finance function signatures (Python ↔ TS parity)

Every function below has identical input/output shape in Python (`packages/finance/`) and TS (`packages/finance/_ts_export/`). Golden-file tests in CI assert byte-equal JSON for a fixed 100-row input matrix; CI fails on drift.

| Function | Module | Signature |
|----------|--------|-----------|
| `affordability` | `affordability.py` | `(buyer: Buyer, market_ctx: MarketContext) -> AffordabilityResult` |
| `monthly_cost` | `affordability.py` | `(price: Decimal, area_ctx: AreaContext) -> MonthlyCost` |
| `compute_phase` | `timing.py` | `(snapshot: SnapshotForPhase, history: PhaseHistory) -> PhaseResult` |
| `cost_of_waiting` | `cost_of_waiting.py` | `(buyer: Buyer, area_id: str, params: WaitParams) -> WaitGrid` |
| `confidence_score` | `confidence.py` | `(metric: MetricValue, age_days: int, disagreement: float \| None) -> ConfidenceResult` |

Dataclass field names match exactly between Python and TS. Money is `Decimal` in Python and a string in TS JSON (no float drift).

---

## C4. `MarketSignal` row shape (Phase 2+, but shape pinned now)

Every signal-emitter (Phase 2 SignalDetector, Phase 6 MLS adapter) writes the same shape:

```python
@dataclass(frozen=True)
class MarketSignal:
    id: UUID
    occurred_at: datetime           # UTC; the moment the signal logically fired
    area_id: UUID                   # GeographicArea.id
    kind: Literal[
        "phase_transition", "mos_threshold", "s2l_threshold",
        "dom_threshold", "rate_threshold",
        # Phase 6 (MLS) additions:
        "new_listing", "price_change", "status_flip", "sold",
    ]
    payload: dict                   # kind-specific structured fields
    snapshot_id: UUID | None        # link back to triggering snapshot if any
    source: str
    confidence: int                 # 0–100
```

---

## C5. Postgres LISTEN/NOTIFY channel

- Channel name: `market_signal_inserted`
- Payload: stringified `MarketSignal.id` (UUID); subscribers fetch the row.
- Single channel for MVP; partition later if subscriber count > ~10K (per design §4.4).

---

## C6. OpenAPI spec generation

Backend (`apps/api`) generates `apps/api/openapi.json` on every API change. Frontend (`apps/web`) generates a typed client into `apps/web/src/api/generated/` from that spec. Both regen steps are part of `make precommit`. CI fails if either is out of date.

---

## Update protocol

If you need to change a contract:

1. Open a **contract-change PR** that updates this doc + both sides of the interface.
2. Land that PR before any feature PR depending on the change.
3. Bump `schema_version` in `packages/domain/snapshot.py` if the JSON contract changes.
