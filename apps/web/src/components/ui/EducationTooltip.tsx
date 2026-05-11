/**
 * <EducationTooltip /> — inline glossary (F-EDU-02, F-EDU-04).
 *
 * Phase 2 stub. Real implementation uses shadcn HoverCard linking each
 * glossary term to MDX content under `apps/web/src/app/education/`. The MDX
 * source-of-truth for Phase 1 lives in `docs/glossary/`.
 *
 * TODO: full implementation per docs/design.md §10.7.4
 *  - shadcn HoverCard with delay-open of 200ms.
 *  - load MDX summary inline; full term page on click.
 *  - dotted-underline visual signaling per §10.7.5.
 *  - keyboard focus opens hover card (NF-A11Y-01).
 */

interface Props {
  /** Glossary term slug, e.g. "mello-roos", "prop-13", "dti". */
  term: string;
  children: React.ReactNode;
}

export function EducationTooltip({ term, children }: Props) {
  return (
    <span
      className="border-b border-dotted border-tx-muted cursor-help"
      title={`Glossary: ${term}`}
    >
      {children}
    </span>
  );
}
