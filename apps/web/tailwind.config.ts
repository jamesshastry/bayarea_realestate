import type { Config } from "tailwindcss";

/**
 * Tailwind v4 config. Most theme tokens are defined as CSS custom properties
 * in `src/app/globals.css` (per docs/design.md §10.7.3 — OKLCH semantic
 * tokens for surfaces, text, money sentiment, market phase, freshness tier).
 * This file just declares content paths and a thin alias layer so utility
 * classes like `bg-surface`, `text-tx-muted`, `border-border` resolve to the
 * tokens.
 */
const config: Config = {
  content: ["./src/**/*.{ts,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        bg: "var(--bg)",
        surface: "var(--surface)",
        border: "var(--border)",
        tx: "var(--tx)",
        "tx-muted": "var(--tx-muted)",
        positive: "var(--positive)",
        negative: "var(--negative)",
        warning: "var(--warning)",
        info: "var(--info)",
        "phase-peak": "var(--phase-peak)",
        "phase-cooling": "var(--phase-cooling)",
        "phase-trough": "var(--phase-trough)",
        "phase-recovery": "var(--phase-recovery)",
        "tier-realtime": "var(--tier-realtime)",
        "tier-near-realtime": "var(--tier-near-realtime)",
        "tier-daily": "var(--tier-daily)",
        "tier-stale": "var(--tier-stale)",
      },
      fontFamily: {
        // The "Wall Street terminal" aesthetic from the prototype.
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
    },
  },
  plugins: [],
};

export default config;
