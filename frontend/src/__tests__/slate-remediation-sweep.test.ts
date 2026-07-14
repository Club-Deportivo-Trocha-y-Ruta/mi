/**
 * Slate-remediation regression guard (feature 033 / T044).
 *
 * T035-T038 remediated every `slate-*` Tailwind class in técnica, fuerza,
 * intervalos, and ansiedad to the design-token equivalents
 * (`text-charcoal`, `text-mid-gray`, `text-text-disclaimer`, `bg-light-gray`,
 * `border-border-gray` — see `research.md` R4 for the mapping). T039 fixed
 * the two stray occurrences outside those four modules. T040-T042 moved
 * técnica's and fuerza's catalog/filter/card implementations onto the
 * shared components (built with charcoal/mid-gray tokens from the start —
 * no slate ever).
 *
 * This test is the CI-runnable guard against regression: it shells out to
 * `grep -rnE '\bslate-[0-9]'` (the exact pattern named by T044) over each of
 * the eight target directories and asserts zero matches. Directories that
 * don't exist in this branch (e.g. `routes/intervals` — intervalos' routes
 * currently live under `routes/training`, per spec 029's surface
 * subtraction) are skipped rather than failing, since an absent directory
 * trivially has zero `slate-*` occurrences.
 *
 * If this test ever fails, the fix is almost always style-only: swap the
 * reported `slate-*` class for its token equivalent per the remap table
 * above — never touch behavior, and for `components/anxiety`/
 * `routes/anxiety` specifically, never touch instrument selection, scoring,
 * interpretation wording, consent gating, or the human-in-the-loop flow
 * (Principle V / FR-010 of this feature).
 */
import { execFileSync } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

// process.cwd() is the `frontend/` package root under vitest.
const FRONTEND_ROOT = process.cwd();
const SRC_DIR = path.resolve(FRONTEND_ROOT, "src");

// Exact target list from tasks.md T044.
const TARGET_DIRS = [
  "routes/technique",
  "routes/strength",
  "routes/intervals",
  "routes/anxiety",
  "components/technique",
  "components/strength",
  "components/intervals",
  "components/anxiety",
];

const SLATE_PATTERN = String.raw`\bslate-[0-9]`;

/**
 * Runs `grep -rnE '\bslate-[0-9]'` over a directory and returns the matching
 * lines (empty array when clean). Uses `execFileSync` (no shell
 * interpolation) so this is safe to run in CI. grep exits 1 when there are
 * no matches — that's a "clean" result, not a test failure, so it's caught
 * and normalized to an empty match list; any other exit code re-throws.
 */
function grepSlateUsage(dir: string): string[] {
  const absoluteDir = path.join(SRC_DIR, dir);
  try {
    const output = execFileSync("grep", ["-rnE", SLATE_PATTERN, absoluteDir], {
      encoding: "utf-8",
    });
    return output.split("\n").filter((line) => line.length > 0);
  } catch (err: unknown) {
    const execErr = err as { status?: number; stdout?: string };
    if (execErr.status === 1) {
      // grep's "no matches found" exit code — the directory is clean.
      return [];
    }
    throw err;
  }
}

describe("Slate-remediation sweep (T044) — grep -rnE '\\bslate-[0-9]' over técnica/fuerza/intervalos/ansiedad", () => {
  for (const dir of TARGET_DIRS) {
    const absoluteDir = path.join(SRC_DIR, dir);
    const dirExists = existsSync(absoluteDir);

    it(`src/${dir} has zero \\bslate-\\d matches${dirExists ? "" : " (directory absent — vacuously clean)"}`, () => {
      if (!dirExists) {
        // e.g. routes/intervals: intervalos' routes currently live under
        // routes/training post spec-029 surface subtraction. Nothing to scan.
        expect(dirExists).toBe(false);
        return;
      }

      const matches = grepSlateUsage(dir);
      expect(matches).toEqual([]);
    });
  }
});
