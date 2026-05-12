/**
 * School detail page (e.g. `/bay-area/schools/01751010130096`).
 *
 * Phase 3 stub: renders nothing useful until CDE + GreatSchools ingest
 * lands. The slug is the school's CDS code (Phase 3 may swap to a friendly
 * `{city}-{name}` slug, e.g. `pleasanton-foothill-hs`).
 */

import { DataNotice } from "@/components/ui/DataNotice";

export const dynamic = "force-dynamic";

export default async function SchoolDetailPage({
  params,
}: {
  params: Promise<{ metro: string; slug: string }>;
}) {
  const { metro, slug } = await params;

  return (
    <div className="mx-auto max-w-7xl px-4 py-8">
      <h1 className="text-3xl font-mono mb-1">School {slug}</h1>
      <p className="text-tx-muted text-sm mb-6">
        Phase 3 placeholder. Click through is wired; data lands once
        ingest runs.
      </p>

      <DataNotice
        variant="info"
        title="Phase 3 in progress"
        body={
          `No school row exists for CDS ${slug} yet. After Phase 3 ingest, ` +
          "this page will render: school metadata + ratings (multi-source per " +
          "F-GEO-08) + attendance-zone-scoped market snapshot + school " +
          "premium calculation + feeder chain."
        }
      />

      <p className="mt-12 text-xs text-tx-muted">
        Back to <a href={`/${metro}/schools`} className="underline">all schools</a>.
      </p>
    </div>
  );
}
