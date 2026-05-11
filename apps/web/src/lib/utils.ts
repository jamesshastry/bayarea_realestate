/**
 * Shared frontend utilities.
 */

import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/**
 * Standard shadcn `cn` helper — concatenates classnames, dedupes Tailwind
 * conflicts (e.g. `p-2 p-4` → `p-4`).
 *
 * Per docs/design.md §10.7.4.1, *direct* `cn(` calls overriding shadcn
 * primitives outside `components/ui/` are flagged by
 * `apps/web/scripts/check-shadcn-overrides.sh` for review.
 */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
