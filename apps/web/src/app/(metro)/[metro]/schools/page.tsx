/**
 * Schools index page (e.g. `/bay-area/schools`).
 *
 * Phase 3 scaffold: lists every school under a metro from the `school`
 * table. The table is empty until Phase 3 ingest (CDE annual data +
 * GreatSchools adapter) lands — the page renders a clear "ingest pending"
 * notice, and starts populating automatically once the loader runs.
 *
 * The 3 priority schools per `docs/seed-data.md` §3 are the first to land:
 *   - Foothill HS Pleasanton (CDS 01751010130096)
 *   - Fremont HS Sunnyvale (CDS 43694684332474)
 *   - Dublin HS Dublin (CDS 01750930132704)
 */

import Link from "next/link";
import { notFound } from "next/navigation";

import { DataNotice } from "@/components/ui/DataNotice";
import { getMetroSummary, listMetroSchools } from "@/lib/areas";

export const dynamic = "force-dynamic";

export default async function SchoolsIndexPage({
  params,
}: {
  params: Promise<{ metro: string }>;
}) {
  const { metro } = await params;
  const [summary, schools] = await Promise.all([
    getMetroSummary(metro),
    listMetroSchools(metro),
  ]);

  if (!summary) notFound();

  return (
    <div className="mx-auto max-w-7xl px-4 py-8">
      <h1 className="text-3xl font-mono mb-1">{summary.name} — Schools</h1>
      <p className="text-tx-muted text-sm mb-6">
        Public schools, district affiliation, and ratings (CDE + multi-source
        per F-GEO-08). Phase 3.
      </p>

      {schools.length === 0 ? (
        <>
          <DataNotice
            variant="info"
            title="School ingest pending"
            body={
              "The `school` table is empty. Phase 3 ingest (CDE annual data + " +
              "GreatSchools adapter + per-district attendance-zone polygon " +
              "digitization) will populate this. Priority schools per " +
              "docs/seed-data.md §3: Foothill HS Pleasanton (CDS 01751010130096), " +
              "Fremont HS Sunnyvale (CDS 43694684332474), Dublin HS Dublin " +
              "(CDS 01750930132704)."
            }
          />
          <ul className="mt-6 space-y-2 text-sm text-tx-muted">
            <li>
              · Decision needed: GreatSchools API key (free non-commercial
              tier OK pre-monetization).
            </li>
            <li>
              · Decision needed: attendance-zone polygon source per district
              (official PDFs vs. GreatSchools-provided GeoJSON). Per-district
              digitization runbook lands as part of Phase 3.
            </li>
            <li>· Fair Housing UI review checklist runs before launch.</li>
          </ul>
        </>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          {schools.map((s) => (
            <Link
              key={s.cds_code}
              href={`/${metro}/schools/${s.cds_code}`}
              className="block p-4 bg-surface border border-border rounded hover:border-info transition-colors"
            >
              <div className="font-mono text-tx">{s.name}</div>
              <div className="text-xs text-tx-muted mt-1">
                {s.level} · CDS {s.cds_code}
              </div>
              {s.district_name ? (
                <div className="text-xs text-tx-muted mt-1">
                  {s.district_name}
                </div>
              ) : null}
            </Link>
          ))}
        </div>
      )}

      <p className="mt-12 text-xs text-tx-muted">
        Source: California Department of Education (CDE) +
        GreatSchools.org. Attribution per data_source.attribution.
      </p>
    </div>
  );
}
