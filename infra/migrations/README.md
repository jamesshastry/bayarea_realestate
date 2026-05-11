# Alembic migrations

Owns the entire Postgres schema for the Bay Area RE tool. The schema is
authoritative — `apps/api/src/bayre_api/models/` mirrors it for the ORM, but
DDL changes land **here first**.

## Conventions

- **Direct connection only.** Migrations require `DATABASE_URL_DIRECT` (the
  non-pooled Neon endpoint). pgBouncer transaction-mode pooling breaks
  `CREATE TYPE`, advisory locks, server-managed cursors. See
  `docs/design.md` §9.1.2.
- **Forward-only.** No `DROP COLUMN` until two releases of deprecation
  (per `docs/datamodel.md` §12). `downgrade()` is best-effort and is meant
  for local-dev rollbacks, not production.
- **Hand-edit autogenerate output.** PostGIS columns, materialized views,
  EXCLUDE constraints, and expression indexes don't survive
  `alembic revision --autogenerate`. Always review the generated file and
  add raw `op.execute(...)` for those.

## Run

From the repo root:

```bash
# 1. Make sure the env has the DIRECT (non-pooled) Neon URL.
export DATABASE_URL_DIRECT='postgresql://USER:PASSWORD@HOST.REGION.aws.neon.tech/neondb?sslmode=require'

# 2. Apply all pending migrations.
uv run alembic -c infra/migrations/alembic.ini upgrade head

# 3. Roll back one revision (local dev only).
uv run alembic -c infra/migrations/alembic.ini downgrade -1

# 4. Generate a new revision after changing models.
uv run alembic -c infra/migrations/alembic.ini revision --autogenerate -m "add foo column"
```

A `make migrate` target wraps step 2; see the root `Makefile`.

## Revisions

| File | Purpose |
|------|---------|
| `0001_initial_schema.py` | Full `datamodel.md` §3–§7 schema (extensions, enums, tables, indexes, materialized view, current_market_phase view). |
| `0002_seed_geographic_areas.py` | The 18 priority `GeographicArea` rows from `docs/seed-data.md` §6. Geometry left NULL — boundary ingest is a separate Phase 2 ETL job. |

## Acceptance test (Phase 2 exit gate)

After `upgrade head`, the queries in `docs/seed-data.md` §9 must return:

- `geographic_area` row counts: metro=1, county=2, city=7, school_district=5, school_zone=3 (= 18 total).

Schools and attendance zones are added in Phase 3 — the corresponding §9 row
counts (3 schools, 3 zones) are *not* expected at Phase 2 exit.
