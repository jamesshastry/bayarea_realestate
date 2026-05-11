/**
 * <Tappable /> — wrapper enforcing min tap target sizes per NF-A11Y-04.
 *
 * Per docs/design.md §11 mapping table, every interactive element on touch
 * viewports goes through this component; an ESLint rule (added Phase 4) will
 * flag bare `<button>` / `<a>` outside whitelisted contexts.
 *
 * Sizes:
 *   sm  → 32×32 (desktop-only contexts)
 *   md  → 44×44 (Apple HIG minimum)
 *   lg  → 48×48 (preferred for primary CTAs)
 *
 * TODO: full implementation per docs/design.md §10.7.4 + NF-A11Y-04
 *  - polymorphic `as` prop (button | a | NextLink) preserving accessibility.
 *  - haptic feedback hook for PWA installs.
 *  - integrate with shadcn Button variants.
 */

import { cn } from "@/lib/utils";

interface Props extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  size?: "sm" | "md" | "lg";
  children: React.ReactNode;
}

const SIZE_CLASSES: Record<NonNullable<Props["size"]>, string> = {
  sm: "min-w-[32px] min-h-[32px] px-3 py-1 text-sm",
  md: "min-w-[44px] min-h-[44px] px-4 py-2 text-sm",
  lg: "min-w-[48px] min-h-[48px] px-5 py-3 text-base",
};

export function Tappable({
  size = "md",
  className,
  children,
  ...rest
}: Props) {
  return (
    <button
      className={cn(
        "inline-flex items-center justify-center rounded border border-border bg-surface text-tx hover:border-info transition-colors",
        SIZE_CLASSES[size],
        className,
      )}
      {...rest}
    >
      {children}
    </button>
  );
}
