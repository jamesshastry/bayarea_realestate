/**
 * Metro overview page (e.g. `/bay-area`).
 *
 * Phase 2 stub — wire to `GET /v1/metros/{slug}` once that endpoint exists
 * (currently scoped to /v1/areas/{id} from the metro lookup). The list of
 * 7 priority cities is hard-coded here from docs/seed-data.md §2.1; the API
 * version pulls it from `geographic_area` filtered by metro_id + kind='city'.
 */

import Link from "next/link";

const SEED_CITIES = [
  { slug: "dublin", name: "Dublin", county: "Alameda" },
  { slug: "pleasanton", name: "Pleasanton", county: "Alameda" },
  { slug: "fremont", name: "Fremont", county: "Alameda" },
  { slug: "milpitas", name: "Milpitas", county: "Santa Clara" },
  { slug: "sunnyvale", name: "Sunnyvale", county: "Santa Clara" },
  { slug: "mountain-view", name: "Mountain View", county: "Santa Clara" },
  { slug: "campbell", name: "Campbell", county: "Santa Clara" },
] as const;

export default async function MetroOverviewPage({
  params,
}: {
  params: Promise<{ metro: string }>;
}) {
  const { metro } = await params;

  return (
    <div className="mx-auto max-w-7xl px-4 py-8">
      <h1 className="text-3xl font-mono mb-2">Bay Area</h1>
      <p className="text-tx-muted text-sm mb-8">
        Phase 2 scaffold — TODO: wire to <code>/v1/areas/search</code> +{" "}
        <code>/v1/metros/{metro}/timing/fragmentation</code>.
      </p>

      <h2 className="text-xl mb-4">Cities</h2>
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
        {SEED_CITIES.map((c) => (
          <Link
            key={c.slug}
            href={`/${metro}/cities/${c.slug}`}
            className="block p-4 bg-surface border border-border rounded hover:border-info transition-colors"
          >
            <div className="font-mono text-tx">{c.name}</div>
            <div className="text-xs text-tx-muted mt-1">{c.county} County</div>
          </Link>
        ))}
      </div>
    </div>
  );
}
