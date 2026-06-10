import { defineConfig, mergeConfig } from "vitest/config";

import base from "./vitest.config";

/**
 * Vitest config used ONLY by the Stryker mutation-testing gate (feature 012).
 * Restricts the test run to the suites that exercise the mutated modules
 * (persistAllowList, queryPersister, serverWaking.store) so Stryker's dry run
 * is fast — the full 2131-test suite times out Stryker's initial run.
 * Not used by `npm test` (which uses vitest.config.ts).
 */
export default mergeConfig(
  base,
  defineConfig({
    test: {
      include: [
        "src/lib/__tests__/persistAllowList.test.ts",
        "src/lib/__tests__/queryPersister.test.ts",
        "src/test/integration/persistence-privacy.test.tsx",
        "src/store/__tests__/serverWaking.store.test.ts",
        "src/components/layout/__tests__/ServerWakingBanner.test.tsx",
      ],
      coverage: { enabled: false },
    },
  }),
);
