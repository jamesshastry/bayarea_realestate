import type { NextConfig } from "next";

const config: NextConfig = {
  reactStrictMode: true,
  // App Router is the default; explicit settings live here as Phase 2 wires
  // them in (image domains, redirects, headers, env passthrough).
  experimental: {
    // Server Actions are stable in 15 — leave default; this block is left as
    // a hook for Phase 4 features (PPR, partial prerendering).
  },
};

export default config;
