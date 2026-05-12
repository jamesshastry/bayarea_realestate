"""Phase 0 ETL: file → Postgres loaders.

Phase 2 swaps this module for Dagster assets per `docs/design.md` §4.1; the
function signatures here (`load_snapshot_file`) are designed to slot into a
Dagster `@asset` with no shape change.
"""
