/**
 * <MetricCell /> — every number, everywhere (operating principle #1: show the math).
 *
 * Phase 2 stub. Real implementation puts a shadcn Tooltip over the value
 * exposing source attribution, fetched-at, confidence, and the underlying
 * formula on click. Numbers without a confidence score render as `—`,
 * never as a misleading zero (NF-DAT-03).
 *
 * TODO: full implementation per docs/design.md §10.7.4 + operating principle #1
 *  - shadcn Tooltip with sources + freshness + confidence + formula.
 *  - <SourceAttribution> popover on click.
 *  - Decimal formatting via `Intl.NumberFormat` with locale.
 *  - low-confidence visual de-emphasis (NF-DAT-03).
 */

import { FreshnessBadge, type FreshnessTier } from "@/components/ui/FreshnessBadge";

interface Props {
  label: string;
  value: number | string | null;
  source: string | null;
  asOf: string | null;
  confidence: number | null;
  tier?: FreshnessTier;
  unit?: string;
}

export function MetricCell({
  label,
  value,
  source,
  asOf,
  confidence,
  tier,
  unit,
}: Props) {
  const display = value === null || value === undefined ? "—" : value.toString();
  const lowConfidence = confidence !== null && confidence < 60;

  return (
    <div className="bg-surface border border-border rounded p-3">
      <div className="text-xs text-tx-muted uppercase tracking-wider">
        {label}
      </div>
      <div
        className={`mt-1 font-mono text-2xl ${lowConfidence ? "text-tx-muted" : "text-tx"}`}
        title={source ? `${source} · as of ${asOf ?? "—"}` : undefined}
      >
        {display}
        {unit && value !== null ? (
          <span className="text-sm text-tx-muted ml-1">{unit}</span>
        ) : null}
      </div>
      <div className="mt-2 flex items-center gap-2 text-xs text-tx-muted">
        {tier ? <FreshnessBadge tier={tier} asOf={asOf} /> : null}
        {confidence !== null ? <span>conf {confidence}</span> : null}
      </div>
    </div>
  );
}
