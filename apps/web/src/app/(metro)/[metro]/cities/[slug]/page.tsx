/**
 * City page (e.g. `/bay-area/cities/fremont`).
 *
 * Phase 2 stopgap: queries Neon directly via Server Component. Migrates to
 * `/v1/areas/{id}/snapshot` once apps/api lands on Railway.
 */

import { notFound } from "next/navigation";

import { Breadcrumb } from "@/components/ui/Breadcrumb";
import { DataNotice } from "@/components/ui/DataNotice";
import { FreshnessBadge } from "@/components/ui/FreshnessBadge";
import { MetricCell } from "@/components/ui/MetricCell";
import {
  getCity,
  getLatestCitySnapshot,
  type CitySnapshotRow,
} from "@/lib/areas";

export const dynamic = "force-dynamic";

export default async function CityPage({
  params,
}: {
  params: Promise<{ metro: string; slug: string }>;
}) {
  const { metro, slug } = await params;

  const [city, snap] = await Promise.all([
    getCity(metro, slug),
    getLatestCitySnapshot(slug),
  ]);

  if (!city) {
    notFound();
  }

  return (
    <div className="mx-auto max-w-7xl px-4 py-8">
      <Breadcrumb
        items={[
          { href: `/${metro}`, label: city.metro_name },
          { href: `/${metro}#cities`, label: "Cities" },
          { href: `/${metro}/cities/${slug}`, label: city.name },
        ]}
      />

      <div className="flex items-baseline gap-3 mt-4 mb-1">
        <h1 className="text-3xl font-mono">{city.name}</h1>
        <FreshnessBadge
          tier="monthly"
          asOf={
            snap ? new Date(snap.period_end).toISOString().slice(0, 10) : null
          }
        />
      </div>
      <p className="text-tx-muted text-sm mb-8">{city.county_name}</p>

      {snap ? <SnapshotSection snap={snap} /> : <NoDataNotice />}

      <p className="mt-12 text-xs text-tx-muted">
        Data live from Neon. Property type{" "}
        <code className="font-mono">All Residential</code> (rolled up under{" "}
        <code className="font-mono">sfh</code> until the Phase 2 SFH/condo
        split). Source: Redfin Data Center monthly city tracker.
      </p>
    </div>
  );
}

function NoDataNotice() {
  return (
    <DataNotice
      variant="info"
      title="No snapshot loaded yet"
      body={
        "The geographic_area row exists, but no market_snapshot rows are " +
        "loaded for this city. Run `make ingest && make load-latest` (or " +
        "wait for the monthly cron)."
      }
    />
  );
}

function SnapshotSection({ snap }: { snap: CitySnapshotRow }) {
  const periodLabel = formatPeriod(snap.period_start, snap.period_end);
  const asOfString = new Date(snap.period_end).toISOString().slice(0, 10);

  return (
    <>
      <section className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <MetricCell
          label="Median sale price"
          value={formatMoney(snap.median_sale_price)}
          source="redfin_csv"
          asOf={asOfString}
          confidence={snap.confidence_score}
        />
        <MetricCell
          label="$ / sqft"
          value={formatMoney(snap.median_ppsf)}
          source="redfin_csv"
          asOf={asOfString}
          confidence={snap.confidence_score}
        />
        <MetricCell
          label="Median DOM"
          value={snap.median_dom !== null ? `${snap.median_dom} d` : null}
          source="redfin_csv"
          asOf={asOfString}
          confidence={snap.confidence_score}
        />
        <MetricCell
          label="Sale / list ratio"
          value={formatRatio(snap.sale_to_list_ratio)}
          source="redfin_csv"
          asOf={asOfString}
          confidence={snap.confidence_score}
        />
        <MetricCell
          label="Homes sold"
          value={snap.homes_sold !== null ? snap.homes_sold.toString() : null}
          source="redfin_csv"
          asOf={asOfString}
          confidence={snap.confidence_score}
        />
        <MetricCell
          label="Active listings"
          value={
            snap.active_listings !== null
              ? snap.active_listings.toString()
              : null
          }
          source="redfin_csv"
          asOf={asOfString}
          confidence={snap.confidence_score}
        />
        <MetricCell
          label="Months of supply"
          value={formatDecimal(snap.months_of_supply, 1)}
          source="redfin_csv"
          asOf={asOfString}
          confidence={snap.confidence_score}
        />
        <MetricCell
          label="% with price drops"
          value={formatPercent(snap.pct_with_price_drops)}
          source="redfin_csv"
          asOf={asOfString}
          confidence={snap.confidence_score}
        />
      </section>

      <p className="mt-6 text-xs text-tx-muted">
        Snapshot period {periodLabel} · sample size {snap.sample_size} sales ·
        confidence {snap.confidence_score}/100
      </p>
    </>
  );
}

// ── Formatters ─────────────────────────────────────────────────────────────

function formatMoney(raw: string | null): string | null {
  if (raw === null) return null;
  const n = Number(raw);
  if (!Number.isFinite(n)) return null;
  if (n >= 1_000_000) {
    return `$${(n / 1_000_000).toFixed(2)}M`;
  }
  return `$${Math.round(n).toLocaleString()}`;
}

function formatRatio(raw: string | null): string | null {
  if (raw === null) return null;
  const n = Number(raw);
  if (!Number.isFinite(n)) return null;
  return n.toFixed(3);
}

function formatDecimal(raw: string | null, places: number): string | null {
  if (raw === null) return null;
  const n = Number(raw);
  if (!Number.isFinite(n)) return null;
  return n.toFixed(places);
}

function formatPercent(raw: string | null): string | null {
  // Redfin's `PRICE_DROPS` arrives as a fraction (0.145 = 14.5%).
  if (raw === null) return null;
  const n = Number(raw);
  if (!Number.isFinite(n)) return null;
  return `${(n * 100).toFixed(1)}%`;
}

function formatPeriod(start: Date, end: Date): string {
  const opts: Intl.DateTimeFormatOptions = { month: "short", day: "numeric", year: "numeric" };
  return `${new Date(start).toLocaleDateString(undefined, opts)} – ${new Date(end).toLocaleDateString(
    undefined,
    opts,
  )}`;
}
