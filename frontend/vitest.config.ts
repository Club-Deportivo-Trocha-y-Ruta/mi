import { defineConfig } from "vitest/config";
import path from "node:path";

export default defineConfig({
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
    coverage: {
      provider: "v8",
      reporter: ["text", "lcov"],
      include: [
        "src/lib/**",
        "src/store/**",
        "src/hooks/**",
        "src/components/**",
        "src/routes/training/**",
        "src/routes/parents/training/**",
        "src/api/trainingSessions.ts",
      ],
      all: true,
      thresholds: {
        "src/components/training/**": { lines: 75, functions: 75, branches: 70 },
        "src/components/parents/**": { lines: 50, functions: 40, branches: 45 },
        "src/api/trainingSessions.ts": { lines: 50, functions: 50 },
      },
      exclude: ["**/*.test.tsx", "**/*.test.ts", "**/*.a11y.test.tsx", "**/test/**"],
    },
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
});
