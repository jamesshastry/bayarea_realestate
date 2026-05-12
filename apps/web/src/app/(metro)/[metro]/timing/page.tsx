/**
 * Metro timing page (e.g. `/bay-area/timing`).
 *
 * Phase 2 scaffold: lists every city with snapshot history depth + Market
 * Phase classification when computable. Per `docs/design.md` §5.3.1,
 * `computePhase` needs ≥3 monthly snapshots (4-week and 12-week trailing
 * medians); we don't have that yet (the cron just started accumulating
 * monthly), so most cities will show "Accumulating" until ~2026-08.
 *
 * The per-city phase classification, fragmentation viz, and clock-face
 * component (F-TIM-06) come online automatically as history fills in.
 */

import { Decimal } from "@bayre/finance";
import { computePhase } from "@bayre/finance";
import type { MarketPhase, PhaseResult } from "@bayre/finance";
import Link from "next/link";
import { notFound } from "next/navigation";

import {
  getMetroSummary,
  listMetroCitiesForTiming,
  type CityPhaseInput,
} from "@/lib/areas";

export const dynamic = "force-dynamic";

const MIN_HISTORY_FOR_PHASE = 3;

export default async function TimingPage({
  params,
}: {
  params: Promise<{ metro: string }>;
}) {
  const { metro } = await params;

  const [summary, cities] = await Promise.all([
    getMetroSummary(metro),
    listMetroCitiesForTiming(metro),
  ]);

  if (!summary) notFound();

  const ready = cities.filter((c) => c.history_months >= MIN_HISTORY_FOR_PHASE);
  const accumulating = cities.filter(
    (c) => c.history_months < MIN_HISTORY_FOR_PHASE,
  );

  return (
    <div className="mx-auto max-w-7xl px-4 py-8">
      <h1 className="text-3xl font-mono mb-1">{summary.name} — Market timing</h1>
      <p className="text-tx-muted text-sm mb-6">
        Per-city Market Phase computed from snapshot history (
        <Link href="/learn/market-phase" className="underline">
          how this works
        </Link>
        ). Phase 2 scaffold — fragmentation viz (F-TIM-06) lands once every
        city has ≥{MIN_HISTORY_FOR_PHASE} monthly snapshots.
      </p>

      {ready.length > 0 ? (
        <section className="mb-10">
          <h2 className="text-xl mb-3">Phase classifications</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {ready.map((c) => (
              <PhaseCard key={c.slug} metro={metro} city={c} />
            ))}
          </div>
        </section>
      ) : null}

      {accumulating.length > 0 ? (
        <section>
          <h2 className="text-xl mb-3">Accumulating data</h2>
          <p className="text-tx-muted text-sm mb-3">
            These cities don&apos;t have enough snapshot history yet to
            classify a Market Phase. The monthly cron adds one snapshot per
            city per month — this section shrinks as data fills in.
          </p>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {accumulating.map((c) => (
              <AccumulatingCard key={c.slug} metro={metro} city={c} />
            ))}
          </div>
        </section>
      ) : null}

      <p className="mt-12 text-xs text-tx-muted">
        Source: Redfin Data Center monthly city tracker. Phase formula per{" "}
        <code className="font-mono">packages/finance/timing.py</code>.
        Confidence inherits from the source snapshot.
      </p>
    </div>
  );
}

function AccumulatingCard({
  metro,
  city,
}: {
  metro: string;
  city: CityPhaseInput;
}) {
  return (
    <Link
      href={`/${metro}/cities/${city.slug}`}
      className="block p-4 bg-surface border border-border rounded hover:border-info transition-colors"
    >
      <div className="font-mono text-tx">{city.name}</div>
      <div className="text-xs text-tx-muted mt-1">{city.county_name}</div>
      <div className="mt-3 flex items-baseline gap-2">
        <span className="text-2xl font-mono">{city.history_months}</span>
        <span className="text-xs text-tx-muted">
          {city.history_months === 1 ? "month" : "months"} of history
        </span>
      </div>
      <div className="text-xs text-tx-muted mt-1">
        Need ≥{MIN_HISTORY_FOR_PHASE} for phase classification
      </div>
    </Link>
  );
}

function PhaseCard({
  metro,
  city,
}: {
  metro: string;
  city: CityPhaseInput;
}) {
  const phase = tryComputePhase(city);
  return (
    <Link
      href={`/${metro}/cities/${city.slug}`}
      className="block p-4 bg-surface border border-border rounded hover:border-info transition-colors"
    >
      <div className="flex items-baseline justify-between">
        <div className="font-mono text-tx">{city.name}</div>
        {phase ? <PhaseBadge phase={phase.phase} /> : null}
      </div>
      <div className="text-xs text-tx-muted mt-1">{city.county_name}</div>

      {phase ? (
        <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
          <div>
            <div className="text-tx-muted">Buyer pressure</div>
            <div className="font-mono text-tx">{phase.buyer_pressure}/100</div>
          </div>
          <div>
            <div className="text-tx-muted">Seller pressure</div>
            <div className="font-mono text-tx">{phase.seller_pressure}/100</div>
          </div>
          <div className="col-span-2">
            <div className="text-tx-muted">Clock position</div>
            <div className="font-mono text-tx">
              {Number(phase.clock_position.toString()).toFixed(1)}/12
            </div>
          </div>
        </div>
      ) : (
        <div className="text-xs text-tx-muted mt-2">
          History present but missing fields — phase unavailable.
        </div>
      )}
    </Link>
  );
}

const PHASE_COLORS: Record<MarketPhase, string> = {
  peak: "bg-tier-stale/20 text-tier-stale border-tier-stale/40",
  cooling: "bg-tier-daily/20 text-tier-daily border-tier-daily/40",
  trough: "bg-tier-realtime/20 text-tier-realtime border-tier-realtime/40",
  recovery:
    "bg-tier-near-realtime/20 text-tier-near-realtime border-tier-near-realtime/40",
  unknown: "bg-border/40 text-tx-muted border-border/40",
};

function PhaseBadge({ phase }: { phase: MarketPhase }) {
  return (
    <span
      className={`text-xs px-2 py-0.5 rounded border font-mono uppercase tracking-wide ${PHASE_COLORS[phase]}`}
    >
      {phase}
    </span>
  );
}

function tryComputePhase(c: CityPhaseInput): PhaseResult | null {
  if (
    c.s2l_1m === null ||
    c.s2l_3m === null ||
    c.months_of_supply === null ||
    c.pct_with_price_drops === null ||
    c.median_dom === null ||
    c.active_listings === null ||
    c.sample_size === null ||
    c.confidence_score === null
  ) {
    return null;
  }
  try {
    return computePhase(
      {
        months_of_supply: new Decimal(c.months_of_supply),
        s2l_4w: new Decimal(c.s2l_1m),
        s2l_12w: new Decimal(c.s2l_3m),
        pct_with_price_drops: new Decimal(c.pct_with_price_drops),
        median_dom: c.median_dom,
        active_listings: c.active_listings,
        sample_size: c.sample_size,
        confidence_score: c.confidence_score,
      },
      {
        baseline_dom: c.median_dom,
        inv_yoy: new Decimal("0"),
        previous_phase: "unknown",
      },
    );
  } catch {
    return null;
  }
}
