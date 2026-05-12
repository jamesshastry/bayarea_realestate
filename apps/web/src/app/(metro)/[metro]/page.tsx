/**
 * Metro overview page (e.g. `/bay-area`).
 *
 * Phase 2 stopgap: queries Neon directly via Server Component. Migrates to
 * `GET /v1/metros/{slug}` when `apps/api` lands on Railway.
 */

import Link from "next/link";
import { notFound } from "next/navigation";

import { getMetroSummary, listCitiesInMetro } from "@/lib/areas";

// Always render at request time — the seed list is small but the data is
// not in the build output.
export const dynamic = "force-dynamic";

export default async function MetroOverviewPage({
  params,
}: {
  params: Promise<{ metro: string }>;
}) {
  const { metro } = await params;

  const [summary, cities] = await Promise.all([
    getMetroSummary(metro),
    listCitiesInMetro(metro),
  ]);

  if (!summary) {
    notFound();
  }

  return (
    <div className="mx-auto max-w-7xl px-4 py-8">
      <h1 className="text-3xl font-mono mb-2">{summary.name}</h1>
      <p className="text-tx-muted text-sm mb-8">
        {summary.total_cities} cities · {summary.total_counties} counties ·{" "}
        {summary.total_areas} total areas tracked
      </p>

      <h2 className="text-xl mb-4">Cities</h2>
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
        {cities.map((c) => (
          <Link
            key={c.slug}
            href={`/${metro}/cities/${c.slug}`}
            className="block p-4 bg-surface border border-border rounded hover:border-info transition-colors"
          >
            <div className="font-mono text-tx">{c.name}</div>
            <div className="text-xs text-tx-muted mt-1">{c.county_name} County</div>
          </Link>
        ))}
      </div>

      <p className="mt-8 text-xs text-tx-muted">
        Data live from Neon. Snapshot ingest, school zones, and timing pages
        wire in over Phase 2 / 3.
      </p>
    </div>
  );
}
