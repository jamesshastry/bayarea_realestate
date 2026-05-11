# Legacy prototype

These files (`scrape.py`, `generate_dashboard.py`) are the throwaway MVP referenced in
`/CLAUDE.md` and `/docs/implementation-plan.md`. They are kept as:

1. **Data-ingest reference** — Redfin/Zillow/Movoto parsing patterns for the new
   `packages/adapters/` rewrites.
2. **Visual aesthetic reference** — the Chart.js layout that the Phase 2+ Next.js
   dashboard takes inspiration from (per `docs/design.md` §10.7.6).

**Do not extend.** Phase 2 is greenfield (decision 2026-05-11). The path bug
documented in `/CLAUDE.md` (Path(__file__).parent.parent) is preserved as-is —
fixing it would imply this code is on the production path. It isn't.
