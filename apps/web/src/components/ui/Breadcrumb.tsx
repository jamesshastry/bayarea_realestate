/**
 * <Breadcrumb /> — every sub-metro page (F-NAV-03).
 *
 * Phase 2 stub. Renders a simple right-arrow chain for now; the shadcn
 * Breadcrumb primitive (which wraps Radix' navigation menu) replaces this in
 * Phase 2 follow-up so keyboard navigation + ARIA semantics are correct out
 * of the box.
 *
 * TODO: full implementation per docs/design.md §10.7.4
 *  - shadcn Breadcrumb primitives (BreadcrumbList, BreadcrumbItem, BreadcrumbLink).
 *  - aria-current="page" on the last item.
 *  - truncation + dropdown for deep hierarchies (school zone inside city inside county inside metro).
 */

import Link from "next/link";

export interface BreadcrumbItem {
  href: string;
  label: string;
}

interface Props {
  items: BreadcrumbItem[];
}

export function Breadcrumb({ items }: Props) {
  return (
    <nav aria-label="Breadcrumb" className="text-xs text-tx-muted font-mono">
      <ol className="flex items-center gap-2 flex-wrap">
        {items.map((item, idx) => {
          const isLast = idx === items.length - 1;
          return (
            <li key={item.href} className="flex items-center gap-2">
              {isLast ? (
                <span aria-current="page" className="text-tx">
                  {item.label}
                </span>
              ) : (
                <Link href={item.href} className="hover:text-tx">
                  {item.label}
                </Link>
              )}
              {!isLast ? <span aria-hidden>›</span> : null}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
