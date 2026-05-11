/**
 * Public status page — same data as `/v1/status` (NF-DAT-08).
 *
 * Phase 2 stub: hits the API in production; in the empty-checkout case the
 * API returns `{overall: "unknown", sources: []}`. Wire to API_BASE_URL once
 * `apps/web/src/lib/api/client.ts` is fully populated.
 */

import { apiClient } from "@/lib/api/client";

interface StatusResponse {
  overall: "green" | "yellow" | "red" | "unknown";
  generated_at: string;
  sources: Array<{
    name: string;
    display_name: string;
    health: "green" | "yellow" | "red" | "unknown";
    freshness_tier: string;
    last_fetch_at: string | null;
    last_success_at: string | null;
    last_error: string | null;
    expected_next_at: string | null;
  }>;
}

const HEALTH_DOT: Record<StatusResponse["overall"], string> = {
  green: "bg-positive",
  yellow: "bg-warning",
  red: "bg-negative",
  unknown: "bg-tx-muted",
};

export default async function StatusPage() {
  let data: StatusResponse | null = null;
  let fetchError: string | null = null;

  try {
    data = await apiClient.get<StatusResponse>("/v1/status");
  } catch (err) {
    fetchError = (err as Error).message;
  }

  return (
    <div className="mx-auto max-w-3xl px-4 py-8">
      <h1 className="text-3xl font-mono mb-2">Status</h1>
      <p className="text-tx-muted text-sm mb-8">
        Per-source ingest health for the data behind the dashboards.
      </p>

      {fetchError ? (
        <div className="p-4 bg-surface border border-negative rounded">
          <div className="text-negative text-sm">
            Could not reach API: {fetchError}
          </div>
          <div className="text-tx-muted text-xs mt-2">
            (Phase 2 scaffold — set NEXT_PUBLIC_API_BASE_URL or run the API
            locally with <code>uv run uvicorn bayre_api.main:app</code>.)
          </div>
        </div>
      ) : data ? (
        <>
          <div className="flex items-center gap-2 mb-6">
            <span
              className={`inline-block w-3 h-3 rounded-full ${HEALTH_DOT[data.overall]}`}
              aria-label={`overall status: ${data.overall}`}
            />
            <span className="font-mono text-sm uppercase">{data.overall}</span>
            <span className="text-xs text-tx-muted ml-auto">
              {new Date(data.generated_at).toLocaleString()}
            </span>
          </div>

          {data.sources.length === 0 ? (
            <div className="text-tx-muted text-sm">
              No sources registered yet (Phase 0 <code>data/sources.json</code>{" "}
              not present).
            </div>
          ) : (
            <ul className="divide-y divide-border bg-surface border border-border rounded">
              {data.sources.map((s) => (
                <li
                  key={s.name}
                  className="px-4 py-3 flex items-center gap-3"
                >
                  <span
                    className={`inline-block w-2 h-2 rounded-full ${HEALTH_DOT[s.health]}`}
                  />
                  <div className="font-mono text-sm">{s.display_name}</div>
                  <div className="text-xs text-tx-muted ml-auto">
                    {s.last_success_at
                      ? `last ok: ${new Date(s.last_success_at).toLocaleString()}`
                      : "no successful fetch"}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </>
      ) : null}
    </div>
  );
}
