import Link from "next/link";

/**
 * Metro-scoped layout — provides the top nav (F-NAV-01).
 *
 * Per docs/design.md §10.7.4 and docs/implementation-plan.md Phase 2 exit
 * criteria, the top-nav structure is fixed at:
 *
 *   Areas | Timing | Compare | Map | Saved | Learn
 *
 * Children of this layout are anything under `/[metro]/...`. The `(metro)`
 * route group lets us share this layout across multiple metro slugs without
 * showing up in the URL.
 */

const NAV_ITEMS = [
  { href: "", label: "Areas" },
  { href: "/timing", label: "Timing" },
  { href: "/compare", label: "Compare" },
  { href: "/map", label: "Map" },
  { href: "/saved", label: "Saved" },
  { href: "/learn", label: "Learn" },
] as const;

export default async function MetroLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ metro: string }>;
}) {
  const { metro } = await params;

  return (
    <div className="min-h-screen flex flex-col">
      <header className="border-b border-border bg-surface">
        <div className="mx-auto max-w-7xl px-4 py-3 flex items-center gap-6">
          <Link
            href={`/${metro}`}
            className="font-mono text-tx font-semibold tracking-tight"
          >
            bayre · {prettyMetroName(metro)}
          </Link>
          <nav className="flex items-center gap-4 text-sm">
            {NAV_ITEMS.map((item) => (
              <Link
                key={item.label}
                href={`/${metro}${item.href}`}
                className="text-tx-muted hover:text-tx transition-colors"
              >
                {item.label}
              </Link>
            ))}
          </nav>
          <div className="ml-auto text-xs text-tx-muted font-mono">
            {/* TODO: <CommandPalette /> trigger (F-NAV-02) */}
            ⌘K
          </div>
        </div>
      </header>
      <main className="flex-1">{children}</main>
      <footer className="border-t border-border bg-surface mt-12">
        <div className="mx-auto max-w-7xl px-4 py-4 text-xs text-tx-muted flex items-center gap-4">
          <span>© 2026 Bay Area RE</span>
          <Link href="/status" className="hover:text-tx">
            Status
          </Link>
          <Link href={`/${metro}/sources`} className="hover:text-tx">
            Sources
          </Link>
          <span className="ml-auto">
            Not financial advice — see /learn for methodology.
          </span>
        </div>
      </footer>
    </div>
  );
}

function prettyMetroName(slug: string): string {
  return slug
    .split("-")
    .map((s) => s.charAt(0).toUpperCase() + s.slice(1))
    .join(" ");
}
