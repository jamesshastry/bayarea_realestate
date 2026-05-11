"use client";

/**
 * <CommandPalette /> — global Cmd+K palette (F-NAV-02).
 *
 * Phase 2 stub. Real implementation uses `cmdk` (which shadcn re-exports
 * as <Command>) for fuzzy search across:
 *   - GeographicArea search (cities, neighborhoods, zips, school zones)
 *   - Saved areas / scenarios (when authed)
 *   - Education topics (MDX glossary)
 *
 * TODO: full implementation per docs/design.md §10.7.4
 *  - mount as a Radix Dialog + cmdk Command list.
 *  - Cmd/Ctrl+K global keybinding handler.
 *  - server-side endpoint /v1/areas/search?q=... wired via TanStack Query.
 *  - recent + pinned sections.
 */

import { useEffect, useState } from "react";

export function CommandPalette() {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    function onKeydown(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setOpen((o) => !o);
      }
      if (e.key === "Escape") setOpen(false);
    }
    window.addEventListener("keydown", onKeydown);
    return () => window.removeEventListener("keydown", onKeydown);
  }, []);

  if (!open) return null;

  return (
    <div
      role="dialog"
      aria-label="Command palette"
      className="fixed inset-0 z-50 flex items-start justify-center pt-24 bg-black/40"
      onClick={() => setOpen(false)}
    >
      <div
        className="bg-surface border border-border rounded shadow-xl w-full max-w-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <input
          type="text"
          autoFocus
          placeholder="Search areas, schools, scenarios…"
          className="w-full bg-transparent border-0 px-4 py-3 text-tx focus:outline-none"
        />
        <div className="border-t border-border px-4 py-6 text-tx-muted text-sm font-mono">
          (stub) results will land in Phase 2 — wire to /v1/areas/search
        </div>
      </div>
    </div>
  );
}
