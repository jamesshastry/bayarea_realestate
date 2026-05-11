import { defineConfig } from "tsup";

export default defineConfig({
  entry: ["src/index.ts"],
  format: ["esm"],
  target: "es2022",
  dts: true,
  sourcemap: true,
  clean: true,
  splitting: false,
  treeshake: true,
  // Zero runtime deps; the Decimal implementation is in-tree so the
  // bundle stays browser-safe and free of external taint.
  noExternal: [],
});
