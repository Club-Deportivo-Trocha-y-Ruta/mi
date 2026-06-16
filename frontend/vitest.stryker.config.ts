import { defineConfig } from "vitest/config";
import path from "node:path";

/**
 * Standalone Vitest config used ONLY by the Stryker mutation-testing gate
 * (feature 012). It does NOT extend vitest.config.ts on purpose: mergeConfig
 * concatenates `test.include`, which would re-introduce the full suite and
 * time out Stryker's initial run. Here `include` is restricted to the suites
 * that exercise the mutated modules (persistAllowList, queryPersister,
 * serverWaking.store, and — feature 015 — useImportPrefill). Not used by
 * `npm test`.
 */
export default defineConfig({
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    include: [
      "src/lib/__tests__/persistAllowList.test.ts",
      "src/lib/__tests__/queryPersister.test.ts",
      "src/test/integration/persistence-privacy.test.tsx",
      "src/store/__tests__/serverWaking.store.test.ts",
      "src/components/layout/__tests__/ServerWakingBanner.test.tsx",
      "src/hooks/__tests__/usePrefetchOnIntent.test.tsx",
      "src/hooks/race/__tests__/useImportPrefill.test.ts",
    ],
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
});
