/**
 * City page (e.g. `/bay-area/cities/fremont`).
 *
 * Phase 2 stopgap: queries Neon directly via Server Component. Migrates to
 * `/v1/areas/{id}/snapshot` once apps/api lands on Railway.
 */

import { Decimal } from "@bayre/finance";
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
import { DEFAULTS, medianMonthlyCost } from "@/lib/finance";

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

      {snap?.median_sale_price ? (
        <MonthlyCostSection
          medianPrice={snap.median_sale_price}
          countyName={city.county_name}
        />
      ) : null}

      <p className="mt-12 text-xs text-tx-muted">
        Data live from Neon. Property type{" "}
        <code className="font-mono">All Residential</code> (rolled up under{" "}
        <code className="font-mono">sfh</code> until the Phase 2 SFH/condo
        split). Source: Redfin Data Center monthly city tracker.
      </p>
    </div>
  );
}

function MonthlyCostSection({
  medianPrice,
  countyName,
}: {
  medianPrice: string;
  countyName: string;
}) {
  const cost = medianMonthlyCost(new Decimal(medianPrice), countyName);
  if (cost === null) return null;

  return (
    <section className="mt-12">
      <h2 className="text-xl mb-1">Monthly cost on the median home</h2>
      <p className="text-tx-muted text-sm mb-4">
        Show-the-math: P&amp;I + tax + Mello-Roos + HOA + insurance + PMI for
        the median sale price above. Defaults: 20% down, 30-year fixed at{" "}
        {(Number(DEFAULTS.rateAnnual.toString()) * 100).toFixed(2)}%,{" "}
        ${Number(DEFAULTS.insuranceAnnual.toString()).toLocaleString()} annual
        insurance, no Mello-Roos / no HOA. Per-buyer affordability calculator
        coming next.
      </p>
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
        <CostCell label="P&I" value={cost.p_and_i.toString()} />
        <CostCell label="Property tax" value={cost.tax.toString()} />
        <CostCell label="Mello-Roos" value={cost.mello.toString()} />
        <CostCell label="HOA" value={cost.hoa.toString()} />
        <CostCell label="Insurance" value={cost.insurance.toString()} />
        <CostCell
          label="PMI"
          value={cost.pmi.toString()}
          hint={
            cost.pmi.toString() === "0" || cost.pmi.toString() === "0.00"
              ? "no PMI at 20% down"
              : undefined
          }
        />
      </div>
      <div className="mt-4 p-4 bg-surface border border-border rounded">
        <div className="text-xs text-tx-muted">Total monthly cost</div>
        <div className="text-2xl font-mono mt-1">
          ${Math.round(Number(cost.total.toString())).toLocaleString()}
        </div>
        <div className="text-xs text-tx-muted mt-1">
          on a $
          {Math.round(Number(medianPrice)).toLocaleString()} home, ${" "}
          {Math.round(
            Number(medianPrice) *
              Number(DEFAULTS.downPaymentPct.toString()),
          ).toLocaleString()}{" "}
          down
        </div>
      </div>
    </section>
  );
}

function CostCell({
  label,
  value,
  hint,
}: {
  label: string;
  value: string;
  hint?: string;
}) {
  const n = Number(value);
  const display = Number.isFinite(n)
    ? `$${Math.round(n).toLocaleString()}`
    : "—";
  return (
    <div className="p-3 bg-surface border border-border rounded">
      <div className="text-xs text-tx-muted">{label}</div>
      <div className="text-lg font-mono mt-1">{display}</div>
      {hint ? <div className="text-xs text-tx-muted mt-1">{hint}</div> : null}
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
