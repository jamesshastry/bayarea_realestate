/**
 * Direct Postgres client for Server Components.
 *
 * **Stopgap.** Phase 2 doesn't yet have `apps/api` deployed (Railway is
 * pending), so the Next.js Server Components query Neon directly to validate
 * the end-to-end Vercel → Neon path. When the FastAPI backend is reachable,
 * switch every consumer of this module to `apps/web/src/lib/api/client.ts`
 * and remove this file.
 *
 * - Uses `DATABASE_URL` (the **pooled** connection — `-pooler` host). Server
 *   Components fan out across many serverless invocations, so connection
 *   pooling at the Neon side is the right default.
 * - `idle_timeout: 0` because Neon's pooler manages the upstream lifetime.
 * - `prepare: false` because pgBouncer transaction-mode pooling (Neon's
 *   default) doesn't support server-side prepared statements.
 */

import postgres, { type Sql } from "postgres";

declare global {
  // Reuse the client across hot reloads in dev to avoid leaking connections.
  // eslint-disable-next-line no-var
  var __sql: Sql | undefined;
}

function makeClient(): Sql {
  const url = process.env.DATABASE_URL;
  if (!url) {
    throw new Error(
      "DATABASE_URL is not set. Add the Neon **pooled** connection string " +
        "(host has `-pooler` in it) to your environment.",
    );
  }
  return postgres(url, {
    max: 5,
    idle_timeout: 0,
    prepare: false,
  });
}

/**
 * Lazy accessor — only touches `process.env.DATABASE_URL` when a query
 * actually runs, never at module-import time. This matters because Next.js
 * evaluates page modules during `next build` to collect static metadata,
 * and the build environment usually doesn't have DB credentials. Throwing
 * at import time would fail the whole build instead of just a single page.
 */
export function getSql(): Sql {
  if (!globalThis.__sql) {
    globalThis.__sql = makeClient();
  }
  return globalThis.__sql;
}
