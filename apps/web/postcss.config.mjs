/**
 * PostCSS pipeline for Tailwind v4.
 *
 * v4 ships its own PostCSS plugin (`@tailwindcss/postcss`) — the v3-era
 * `tailwindcss` + `autoprefixer` pair is no longer required. We keep
 * autoprefixer here to handle vendor-prefixing for OKLCH fallbacks on
 * older Safari versions.
 */
const config = {
  plugins: {
    "@tailwindcss/postcss": {},
    autoprefixer: {},
  },
};

export default config;
