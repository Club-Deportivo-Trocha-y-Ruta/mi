import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";
import { execSync } from "node:child_process";
import { readFileSync } from "node:fs";
import tailwindcss from "@tailwindcss/vite";

/**
 * Resolve a build identifier for the persisted-cache buster (feature 012).
 * Prefers CI-provided commit SHAs (Cloudflare Pages / GitHub Actions / explicit
 * env), then the local git short SHA, then the package version, then "dev".
 * Changes per deploy so a new release invalidates older persisted snapshots.
 */
function resolveAppVersion(): string {
  const fromEnv =
    process.env.CF_PAGES_COMMIT_SHA ??
    process.env.GITHUB_SHA ??
    process.env.VITE_APP_VERSION;
  if (fromEnv) return fromEnv.slice(0, 12);
  try {
    return execSync("git rev-parse --short HEAD", {
      stdio: ["ignore", "pipe", "ignore"],
    })
      .toString()
      .trim();
  } catch {
    try {
      const pkg = JSON.parse(
        readFileSync(new URL("./package.json", import.meta.url), "utf-8"),
      ) as { version?: string };
      return `v${pkg.version ?? "0.0.0"}`;
    } catch {
      return "dev";
    }
  }
}

export default defineConfig({
  plugins: [react(), tailwindcss()],
  define: {
    __APP_VERSION__: JSON.stringify(resolveAppVersion()),
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
      "/health": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
      "/static": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});
