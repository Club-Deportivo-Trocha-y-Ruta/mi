/**
 * AI identity rename sweep (feature 033 / T054, US4, SC-003).
 *
 * contracts/ai-identity.md §1 promotes a single naming/icon standard for
 * every AI entry point: noun "Insights IA", launch verb "Analizar con IA",
 * icon `Sparkles` everywhere except `CompetitionChatPanel.tsx` (the one
 * documented exception — chat is conversational, not a launched/tracked
 * run, and keeps `MessageSquare`).
 *
 * T045-T047 renamed the known offenders (SessionAssistantPage's h1,
 * AthleteAIAnalysisTab's h2 + sub-tab, AnalyzeAthleteButton's icon/label/
 * modal title) — those have per-component render assertions in
 * `aiIdentityRenameTable.test.tsx` and their own component test suites.
 *
 * This file is the repo-wide *sweep*, catching any straggler beyond that
 * known list, the same way `slate-remediation-sweep.test.ts` does for
 * `slate-*` classes: shell out to `grep` over every AI-related directory
 * and assert zero matches for the two retired variants (`BrainCircuit`
 * icon import, and the launch label "Lanzar").
 *
 * Scope is "AI-related component" per the task text, not the whole repo
 * (a coach note button elsewhere in ResultsTable.tsx legitimately uses
 * `MessageSquare` for an unrelated feature) and not test files (an `it()`
 * description referencing the old copy for narrative purposes is not a
 * rendered label — asserting on it would make this sweep enforce test
 * *prose*, not app behavior).
 */
import { execFileSync } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

const FRONTEND_ROOT = process.cwd();
const SRC_DIR = path.resolve(FRONTEND_ROOT, "src");

/** Every AI entry point named in contracts/ai-identity.md's intro. */
const AI_RELATED_TARGETS = [
  "components/ai",
  "components/competitions/insights",
  "components/competitions/chat",
  "components/athletes/ai",
  "routes/training/SessionAssistantPage.tsx",
  "routes/admin/AIHealthPage.tsx",
];

/**
 * Runs `grep -rnE <pattern> <target>` (recursive if `target` is a directory,
 * single-file otherwise) and returns matching lines, excluding anything
 * under a `__tests__` directory or a `.test.ts(x)` file — this sweep is
 * about rendered app copy/icons, not test descriptions or mock scaffolding.
 * grep's exit code 1 ("no matches") is normalized to an empty array; any
 * other exit code re-throws.
 */
function grepAiDir(target: string, pattern: string): string[] {
  const absoluteTarget = path.join(SRC_DIR, target);
  try {
    const output = execFileSync("grep", ["-rnE", pattern, absoluteTarget], {
      encoding: "utf-8",
    });
    return output
      .split("\n")
      .filter((line) => line.length > 0)
      .filter((line) => !line.includes("__tests__"))
      .filter((line) => !/\.test\.tsx?:/.test(line));
  } catch (err: unknown) {
    const execErr = err as { status?: number };
    if (execErr.status === 1) return [];
    throw err;
  }
}

describe("AI identity rename sweep (T054) — BrainCircuit fully retired", () => {
  for (const target of AI_RELATED_TARGETS) {
    const absoluteTarget = path.join(SRC_DIR, target);
    const exists = existsSync(absoluteTarget);

    it(`src/${target} has zero BrainCircuit references${exists ? "" : " (path absent — vacuously clean)"}`, () => {
      if (!exists) {
        expect(exists).toBe(false);
        return;
      }
      expect(grepAiDir(target, "BrainCircuit")).toEqual([]);
    });
  }
});

describe('AI identity rename sweep (T054) — "Lanzar" launch label retired', () => {
  for (const target of AI_RELATED_TARGETS) {
    const absoluteTarget = path.join(SRC_DIR, target);
    const exists = existsSync(absoluteTarget);

    it(`src/${target} has zero standalone "Lanzar" matches${exists ? "" : " (path absent — vacuously clean)"}`, () => {
      if (!exists) {
        expect(exists).toBe(false);
        return;
      }
      // Word boundary: must not catch "Lanzando" (in-flight state copy,
      // unrelated to the retired launch-verb label) or "lanza"/"lanzamiento"
      // used as ordinary Spanish prose elsewhere.
      expect(grepAiDir(target, String.raw`\bLanzar\b`)).toEqual([]);
    });
  }
});

describe("AI identity rename sweep (T054) — MessageSquare allowlisted only for CompetitionChatPanel.tsx", () => {
  const CHAT_PANEL = "components/competitions/chat/CompetitionChatPanel.tsx";

  for (const target of AI_RELATED_TARGETS) {
    if (target === "components/competitions/chat") continue; // handled below, scoped to the allowlisted file only

    const absoluteTarget = path.join(SRC_DIR, target);
    const exists = existsSync(absoluteTarget);

    it(`src/${target} has zero MessageSquare references${exists ? "" : " (path absent — vacuously clean)"}`, () => {
      if (!exists) {
        expect(exists).toBe(false);
        return;
      }
      expect(grepAiDir(target, "MessageSquare")).toEqual([]);
    });
  }

  it("components/competitions/chat: MessageSquare appears only inside CompetitionChatPanel.tsx", () => {
    const matches = grepAiDir("components/competitions/chat", "MessageSquare");
    expect(matches.length).toBeGreaterThan(0); // the allowlisted usage itself
    for (const line of matches) {
      expect(line).toContain(CHAT_PANEL.split("/").pop() as string);
    }
  });
});
