# ADR 0001: Monorepo foundation

- **Status:** Accepted
- **Date:** 2026-05-11
- **Decisions covered:** D1 (`uv`), D2 (TS hand-port + golden-file), D3 (Vercel + Neon + Railway), D5 (Dagster self-host on Railway)

## Context

Per `docs/implementation-plan.md`, Phase 0 starts the greenfield rebuild. The existing `scrape.py` / `generate_dashboard.py` prototype at the repo root is moved to `legacy/` (kept for parsing-pattern reference per `CLAUDE.md`).

## Decision

1. **Layout** matches `docs/design.md` §2: `apps/{web,api}` + `packages/{finance,adapters,domain,etl,geometry,observability}` + `data/{seeds,bronze,silver}` + `infra/{migrations,github-actions}` + `docs/{runbooks,glossary,adr,references}`.
2. **Python packaging:** `uv` workspaces. Single root `pyproject.toml` declares dev deps + workspace members; each package has its own `pyproject.toml` with runtime deps and entry points.
3. **TypeScript packaging:** `pnpm` workspaces (added in Phase 2 scaffold). Per-app `package.json`; shared types via `packages/domain/_ts_export/`.
4. **Python ↔ TS finance parity:** hand-port (not transpile). Golden-file harness in CI: identical input matrix → byte-equal JSON outputs.
5. **Hosting:** Vercel (Next.js), Railway (FastAPI + Dagster), Neon (Postgres+PostGIS). All confirmed by `.env.example`.
6. **Tooling:** `ruff` (lint+format), `pyright` strict (typecheck), `pytest` + `hypothesis` + `responses` (test).

## Consequences

- New code lives in the monorepo from day one — no migration churn later.
- The 95% coverage gate is enforced by `pyproject.toml::tool.coverage.report.fail_under` and bites every PR that touches `packages/finance/`.
- The `legacy/` directory is excluded from lint/typecheck/coverage so it doesn't gate quality on dead code.
- Decisions D4, D6–D10 remain open and will get their own ADRs at the relevant phase boundary.
