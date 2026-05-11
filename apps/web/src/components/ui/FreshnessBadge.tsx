/**
 * <FreshnessBadge /> — every metric (NF-DAT-01).
 *
 * Phase 2 stub. Real implementation uses shadcn Badge styled by freshness
 * tier, with `asOf` rendered relative ("3h ago", "last Thursday").
 *
 * Color tokens are defined in src/app/globals.css (--tier-*) per
 * docs/design.md §10.7.3.
 *
 * TODO: full implementation per docs/design.md §10.7.4
 *  - shadcn Badge primitive.
 *  - relative-time formatting via date-fns.
 *  - turn red ("stale") when asOf > expected_next_at + grace per NF-DAT-06 SLA.
 */

export type FreshnessTier =
  | "realtime"
  | "near_realtime"
  | "daily"
  | "weekly"
  | "monthly"
  | "quarterly"
  | "annual";

const TIER_LABEL: Record<FreshnessTier, string> = {
  realtime: "RT",
  near_realtime: "near-RT",
  daily: "daily",
  weekly: "weekly",
  monthly: "monthly",
  quarterly: "qtrly",
  annual: "annual",
};

const TIER_COLOR: Record<FreshnessTier, string> = {
  realtime: "bg-tier-realtime/20 text-tier-realtime border-tier-realtime/40",
  near_realtime: "bg-tier-near-realtime/20 text-tier-near-realtime border-tier-near-realtime/40",
  daily: "bg-tier-daily/20 text-tier-daily border-tier-daily/40",
  weekly: "bg-tier-daily/20 text-tier-daily border-tier-daily/40",
  monthly: "bg-tier-stale/20 text-tier-stale border-tier-stale/40",
  quarterly: "bg-tier-stale/20 text-tier-stale border-tier-stale/40",
  annual: "bg-tier-stale/20 text-tier-stale border-tier-stale/40",
};

interface Props {
  tier: FreshnessTier;
  asOf: string | null;
}

export function FreshnessBadge({ tier, asOf }: Props) {
  return (
    <span
      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded border text-[10px] font-mono uppercase ${TIER_COLOR[tier]}`}
      title={asOf ? `as of ${asOf}` : undefined}
    >
      {TIER_LABEL[tier]}
    </span>
  );
}
