/**
 * <Chart /> — single chart entry point (per docs/design.md §10.7.4.1).
 *
 * This is the ONLY file in `apps/web` allowed to import `recharts` or
 * `@visx/*`. The ESLint `no-restricted-imports` rule in
 * `apps/web/.eslintrc.json` enforces that.
 *
 * Routing rules (full impl in Phase 2 follow-up):
 *   kind ∈ {"line", "area", "bar", "scatter", "sparkline"} → Recharts
 *   kind ∈ {"market_clock", "fragmentation", "brushable_timeseries"} → Visx
 *
 * Every chart is wrapped in <figure> with a <figcaption> (NF-A11Y-02) and
 * exposes a "View as table" toggle (mandatory, not optional).
 *
 * TODO: full implementation per docs/design.md §10.7.4.1 + §10.7.5
 *  - import { LineChart, AreaChart, ... } from "recharts" (allowed here only).
 *  - import { Group } from "@visx/group" for clock-face geometry.
 *  - <ChartTable> fallback rendering the same data as a TanStack Table.
 *  - role="img" + aria-label summary string.
 */

export type ChartKind =
  | "line"
  | "area"
  | "bar"
  | "scatter"
  | "sparkline"
  | "market_clock"
  | "fragmentation"
  | "brushable_timeseries";

interface Props {
  kind: ChartKind;
  data: unknown[];
  /** Required for screen readers per NF-A11Y-02. */
  ariaLabel: string;
  /** Optional caption rendered as <figcaption>. */
  caption?: string;
  className?: string;
}

export function Chart({ kind, data, ariaLabel, caption, className }: Props) {
  return (
    <figure className={className}>
      <div
        role="img"
        aria-label={ariaLabel}
        className="border border-border bg-surface rounded h-64 flex items-center justify-center text-tx-muted text-sm font-mono"
      >
        chart placeholder · kind={kind} · n={data.length}
      </div>
      {caption ? (
        <figcaption className="text-xs text-tx-muted mt-2">{caption}</figcaption>
      ) : null}
    </figure>
  );
}
