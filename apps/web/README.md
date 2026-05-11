# `@bayre/web` — Next.js 15 frontend

Phase 2 scaffold. App Router, Tailwind v4, shadcn-style component primitives,
typed API client into a stub `apps/api/openapi.json`. Real ETL + DB wiring
lands as Phase 2 progresses.

## Stack (per `docs/design.md` §10.7)

| Layer | Choice |
|-------|--------|
| Framework | Next.js 15 (App Router, RSC) |
| Language | TypeScript (strict) |
| Styling | Tailwind v4 + OKLCH semantic tokens (`src/app/globals.css`) |
| Component primitives | shadcn-style (Radix + Tailwind), copy-pasted into `src/components/ui/` |
| Charts | Recharts (simple) + Visx (Market Clock, fragmentation) — only `src/components/ui/Chart.tsx` may import them |
| State | URL · localStorage · TanStack Query (Phase 4 for auth) |
| Forms | react-hook-form + zod (Phase 2+ wiring) |
| Tables | TanStack Table v8 (Phase 3 comparison page) |

## Develop

From the repo root:

```bash
# 1. Install (handled by lead — no need for sub-agents to run).
pnpm install

# 2. Run the API in another shell:
uv run uvicorn bayre_api.main:app --reload --port 8000

# 3. Run the web dev server:
pnpm --filter @bayre/web dev

# 4. Typecheck / lint.
pnpm --filter @bayre/web typecheck
pnpm --filter @bayre/web lint
pnpm --filter @bayre/web check:shadcn-overrides
```

## Deploy

Vercel auto-deploys on push to `main`. Preview deployments per PR. Set
`NEXT_PUBLIC_API_BASE_URL` per environment to point at the deployed
`apps/api` (Railway in Phase 2).

## Component-discipline rules

Two enforcement rules prevent the predictable shadcn-copy drift documented
in `docs/design.md` §10.7.4.1:

1. **Single chart entry point.** Direct `recharts` / `@visx/*` imports outside
   `src/components/ui/Chart.tsx` are blocked by ESLint `no-restricted-imports`.
2. **`components/ui/` is the only home for shadcn primitives.** Per-feature
   overrides require a `/* shadcn-override: <reason> */` magic comment;
   `scripts/check-shadcn-overrides.sh` lists them on every PR.

These two — together with the chart-as-table fallback (NF-A11Y-02) and OKLCH
semantic tokens (§10.7.3) — are the difference between a design system that
ages well and one that fragments by month six.

## File layout

```
src/
├── app/                                 App Router pages
│   ├── layout.tsx                       Root layout
│   ├── page.tsx                         Landing → /bay-area redirect
│   ├── globals.css                      OKLCH design tokens
│   ├── status/page.tsx                  Public status (NF-DAT-08)
│   └── (metro)/[metro]/                 Metro-scoped routes
│       ├── layout.tsx                   Top nav (F-NAV-01)
│       ├── page.tsx                     Metro overview
│       └── cities/[slug]/page.tsx       City page
├── components/ui/                       Phase-2-baseline primitives
│   ├── Breadcrumb.tsx
│   ├── Chart.tsx                        ← only file allowed to import recharts
│   ├── CommandPalette.tsx
│   ├── DataNotice.tsx
│   ├── DisclaimerNote.tsx
│   ├── EducationTooltip.tsx
│   ├── FreshnessBadge.tsx
│   ├── MetricCell.tsx
│   └── Tappable.tsx
├── lib/
│   ├── api/client.ts                    typed fetch wrapper
│   └── utils.ts                         cn() helper
└── api/generated/                       openapi-typescript codegen target
```
