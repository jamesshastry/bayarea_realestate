/**
 * <DataNotice /> — explicit empty / error / stale / disagree / low-confidence
 * states (F-DATA-01–03).
 *
 * Per docs/design.md §10.7.4: every place a metric *could* be missing or
 * suspect, the page renders a DataNotice rather than a misleading zero.
 *
 * TODO: full implementation per docs/design.md §10.7.4
 *  - shadcn Alert as the underlying primitive (not a div).
 *  - lucide icon per variant.
 *  - retry CTA hook for "fetch failed".
 *  - links to /sources for license / freshness drilldown.
 */

import { cn } from "@/lib/utils";

export type DataNoticeVariant =
  | "empty"
  | "error"
  | "stale"
  | "disagree"
  | "low_confidence"
  | "info";

interface Props {
  variant: DataNoticeVariant;
  title: string;
  body?: string;
  className?: string;
}

const VARIANT_STYLES: Record<DataNoticeVariant, string> = {
  empty: "border-border bg-surface text-tx-muted",
  error: "border-negative bg-surface text-negative",
  stale: "border-warning bg-surface text-warning",
  disagree: "border-warning bg-surface text-warning",
  low_confidence: "border-warning bg-surface text-tx-muted",
  info: "border-info bg-surface text-info",
};

export function DataNotice({ variant, title, body, className }: Props) {
  return (
    <div
      role="status"
      className={cn(
        "border rounded p-4 text-sm",
        VARIANT_STYLES[variant],
        className,
      )}
    >
      <div className="font-mono uppercase text-xs tracking-wider mb-1">
        {title}
      </div>
      {body ? <div className="text-tx text-sm">{body}</div> : null}
    </div>
  );
}
