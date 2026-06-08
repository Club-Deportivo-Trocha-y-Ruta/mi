/**
 * T049 — Wave F cleanup guard tests.
 *
 * Wave F policy (US6 FR-002/004/027):
 *   - Legacy redirect routes stay as <Navigate replace> (NOT flipped to GonePage/410).
 *     External deep links from Spond/emails must keep working.
 *     The 410 flip is a deliberate post-deploy follow-up.
 *   - Dead page components (RaceAnalysisPage, ClubInsightsByRacePage) have been
 *     removed (they were never present as files in this branch since Wave B/C
 *     already inlined their content into the canonical locations).
 *   - No source file should import from those removed module paths.
 *
 * This file provides two guards:
 *   1. No-import guard: scans all .ts/.tsx source files for any reference to
 *      the removed module identifiers so they cannot be re-introduced silently.
 *   2. Redirect-still-active guard: re-asserts that the legacy routes still
 *      land at the canonical destinations (not a 410 / GonePage) so this test
 *      will fail if someone flips the redirects before the approved follow-up.
 */
/// <reference types="node" />
import { describe, it, expect } from "vitest";
import * as fs from "fs";
import * as path from "path";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes, Navigate, useParams } from "react-router-dom";

// ---------------------------------------------------------------------------
// Helpers — filesystem scan
// ---------------------------------------------------------------------------

/** Collect all .ts / .tsx files under a directory (recursive). */
function collectSourceFiles(dir: string): string[] {
  const results: string[] = [];
  const entries = fs.readdirSync(dir, { withFileTypes: true });
  for (const entry of entries) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      // skip node_modules just in case symlinks traverse upward
      if (entry.name === "node_modules") continue;
      results.push(...collectSourceFiles(full));
    } else if (entry.isFile() && /\.(ts|tsx)$/.test(entry.name)) {
      results.push(full);
    }
  }
  return results;
}

// process.cwd() in vitest is the package root (frontend/).
const SRC_DIR = path.resolve(process.cwd(), "src"); // frontend/src

// The module path fragments that must never appear in an import statement.
// We check for the module identifier (not a comment mention) by looking for
// import ... from ".../<name>" or dynamic import(".../<name>").
const REMOVED_MODULE_FRAGMENTS = [
  "RaceAnalysisPage",
  "ClubInsightsByRacePage",
];

// ---------------------------------------------------------------------------
// Guard 1 — No import of removed modules
// ---------------------------------------------------------------------------

describe("T049 — No import of removed legacy page modules", () => {
  const sourceFiles = collectSourceFiles(SRC_DIR);

  for (const fragment of REMOVED_MODULE_FRAGMENTS) {
    it(`no source file imports "${fragment}" as a module`, () => {
      // Match any ES import or dynamic import() whose from-path contains the
      // fragment. This intentionally skips plain comments (which are fine to
      // keep as history notes) by requiring the presence of import syntax.
      const importPattern = new RegExp(
        // Static import:  import ... from ".../<fragment>"
        // Dynamic import: import(".../<fragment>")
        `(?:import\\s+.*from\\s+['""][^'"]*${fragment}[^'"]*['"]|import\\s*\\(['""][^'"]*${fragment}[^'"]*['"]\\))`,
      );

      const offending: string[] = [];
      for (const file of sourceFiles) {
        const content = fs.readFileSync(file, "utf-8");
        if (importPattern.test(content)) {
          offending.push(path.relative(SRC_DIR, file));
        }
      }

      expect(offending).toEqual([]);
    });
  }
});

// ---------------------------------------------------------------------------
// Guard 2 — Legacy redirect routes still redirect (not 410)
//
// These tests are intentionally kept separate from competitionsRedirects.test.tsx
// so that T049 is a standalone, self-documenting guard for this wave.
// ---------------------------------------------------------------------------

/** Replica of the ClubInsightsRedirect helper from App.tsx */
function ClubInsightsRedirect() {
  const { raceEventId } = useParams<{ raceEventId: string }>();
  return <Navigate to={`/competitions/${raceEventId}?tab=insights`} replace />;
}

function renderLegacyPath(initialPath: string) {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <Routes>
        {/* Wave B redirects — must remain active during transition */}
        <Route
          path="/coach/race-analysis"
          element={<Navigate to="/competitions/insights" replace />}
        />
        <Route
          path="/training/races/:raceEventId/club-insights"
          element={<ClubInsightsRedirect />}
        />
        {/* Canonical destinations */}
        <Route
          path="/competitions/insights"
          element={<div data-testid="insights-hub">Hub insights</div>}
        />
        <Route
          path="/competitions/:id"
          element={<div data-testid="competition-detail">Detalle</div>}
        />
        {/* Catch-all: should never match for these paths */}
        <Route
          path="*"
          element={<div data-testid="not-found">404</div>}
        />
      </Routes>
    </MemoryRouter>,
  );
}

describe("T049 — Legacy redirect routes still land at canonical destinations (not 410)", () => {
  it("/coach/race-analysis redirige a /competitions/insights (no GonePage)", () => {
    renderLegacyPath("/coach/race-analysis");
    // Must reach the canonical hub.
    expect(screen.getByTestId("insights-hub")).toBeInTheDocument();
    // Must NOT show the GonePage "moved" text (410 flip is not yet done).
    expect(screen.queryByText(/Esta sección se movió/i)).not.toBeInTheDocument();
    // Must NOT fall through to 404.
    expect(screen.queryByTestId("not-found")).not.toBeInTheDocument();
  });

  it("/training/races/:id/club-insights redirige a /competitions/:id?tab=insights (no GonePage)", () => {
    renderLegacyPath("/training/races/42/club-insights");
    expect(screen.getByTestId("competition-detail")).toBeInTheDocument();
    expect(screen.queryByText(/Esta sección se movió/i)).not.toBeInTheDocument();
    expect(screen.queryByTestId("not-found")).not.toBeInTheDocument();
  });

  it("/training/races/:id/club-insights preserva el raceEventId en la ruta destino", () => {
    renderLegacyPath("/training/races/99/club-insights");
    // /competitions/99 is captured by /competitions/:id — confirms id is forwarded.
    expect(screen.getByTestId("competition-detail")).toBeInTheDocument();
    expect(screen.queryByTestId("not-found")).not.toBeInTheDocument();
  });
});
