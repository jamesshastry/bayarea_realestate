/**
 * City page (e.g. `/bay-area/cities/fremont`).
 *
 * Phase 2 stub — TODO: wire to `/v1/areas/{id}/snapshot` (current period) +
 * `/v1/areas/{id}/timeseries` (last 24 months) + `/v1/areas/{id}/timing`.
 */

import { Breadcrumb } from "@/components/ui/Breadcrumb";
import { DataNotice } from "@/components/ui/DataNotice";
import { FreshnessBadge } from "@/components/ui/FreshnessBadge";
import { MetricCell } from "@/components/ui/MetricCell";

export default async function CityPage({
  params,
}: {
  params: Promise<{ metro: string; slug: string }>;
}) {
  const { metro, slug } = await params;
  const cityName = prettyName(slug);

  return (
    <div className="mx-auto max-w-7xl px-4 py-8">
      <Breadcrumb
        items={[
          { href: `/${metro}`, label: "Bay Area" },
          { href: `/${metro}#cities`, label: "Cities" },
          { href: `/${metro}/cities/${slug}`, label: cityName },
        ]}
      />

      <div className="flex items-baseline gap-3 mt-4 mb-6">
        <h1 className="text-3xl font-mono">{cityName}</h1>
        <FreshnessBadge tier="weekly" asOf={null} />
      </div>

      <DataNotice
        variant="info"
        title="Stub page"
        body={`TODO: wire to /v1/areas/{id}/snapshot for ${slug} (Phase 2).`}
      />

      <section className="mt-8 grid grid-cols-2 md:grid-cols-4 gap-4">
        <MetricCell
          label="Median sale price"
          value={null}
          source={null}
          asOf={null}
          confidence={null}
        />
        <MetricCell
          label="$ / sqft"
          value={null}
          source={null}
          asOf={null}
          confidence={null}
        />
        <MetricCell
          label="Median DOM"
          value={null}
          source={null}
          asOf={null}
          confidence={null}
        />
        <MetricCell
          label="Months of supply"
          value={null}
          source={null}
          asOf={null}
          confidence={null}
        />
      </section>
    </div>
  );
}

function prettyName(slug: string): string {
  return slug
    .split("-")
    .map((s) => s.charAt(0).toUpperCase() + s.slice(1))
    .join(" ");
}
