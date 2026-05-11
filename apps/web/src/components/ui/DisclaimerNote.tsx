/**
 * <DisclaimerNote /> — "not financial advice" injection (NF-CMP-01).
 *
 * Phase 2 stub. Renders inline on every affordability / TCO / rent-vs-buy
 * surface and inside the `<Scenario>` viewer per docs/design.md §10.4.
 *
 * TODO: full implementation per docs/design.md §10.7.4 + NF-CMP-01
 *  - shadcn Alert as the underlying primitive.
 *  - link to /education/methodology + /education/disclosures.
 *  - jurisdiction-specific copy switches (CA Prop 13 wording).
 */

interface Props {
  surface: "affordability" | "tco" | "rent_vs_buy" | "scenario" | "timing";
}

const COPY: Record<Props["surface"], string> = {
  affordability:
    "Estimates only — affordability depends on lender approval, credit, and reserves. Not financial advice.",
  tco: "Total cost of ownership uses today's tax + insurance assumptions; actual costs vary year to year. Not financial advice.",
  rent_vs_buy:
    "Rent-vs-buy outcomes are sensitive to appreciation, rate, and tenure assumptions. Not financial advice.",
  scenario:
    "Scenarios are descriptive comparisons, never recommendations. Consult a licensed advisor.",
  timing:
    "Market Phase indicators are descriptive, not predictive. We don't know what comes next.",
};

export function DisclaimerNote({ surface }: Props) {
  return (
    <div
      role="note"
      className="text-xs text-tx-muted border-l-2 border-warning pl-3 py-2"
    >
      {COPY[surface]}
    </div>
  );
}
