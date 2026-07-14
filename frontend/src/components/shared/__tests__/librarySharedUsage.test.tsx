/**
 * Cross-module guard (feature 033 / T043): técnica and fuerza must render
 * their catalog experience through the shared `CatalogGrid`/
 * `LibraryFilterBar`/`LibraryEntityCard` (T040), not through two parallel
 * hand-rolled implementations.
 *
 * Two complementary checks, same pattern as `src/__tests__/T049-wave-f-cleanup.test.tsx`:
 *
 *   1. Source-level guard — each of técnica's and fuerza's `CatalogGrid.tsx`
 *      / `FilterBar.tsx` / `ExerciseCard.tsx` wrappers must import the
 *      corresponding shared component. This is what actually prevents a
 *      future regression back to two parallel copies: it fails the instant
 *      someone reintroduces a self-contained loading/error/empty grid, a
 *      duplicated RHF filter form, or a duplicated card layout in either
 *      module, even if the reintroduced markup happens to look identical.
 *   2. Runtime guard — técnica's and fuerza's wrapper `CatalogGrid`s, given
 *      equivalent props, produce the same shared skeleton/empty markup
 *      (role, aria-busy, default grid layout) — proving the shared shell is
 *      actually what's mounted, not merely imported and unused.
 */
import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";

import { CatalogGrid as TechniqueCatalogGrid } from "@/components/technique/CatalogGrid";
import { CatalogGrid as StrengthCatalogGrid } from "@/components/strength/CatalogGrid";
import { renderWithProviders } from "@/test/helpers/renderWithProviders";

// process.cwd() is the `frontend/` package root under vitest.
const SRC_DIR = path.resolve(process.cwd(), "src");

function readSource(relativePath: string): string {
  return readFileSync(path.join(SRC_DIR, relativePath), "utf-8");
}

// ---------------------------------------------------------------------------
// 1. Source-level guard — both modules' wrappers import the shared components
// ---------------------------------------------------------------------------

const WRAPPER_FILES: {
  module: "technique" | "strength";
  file: string;
  sharedImportPath: string;
}[] = [
  { module: "technique", file: "components/technique/CatalogGrid.tsx", sharedImportPath: "@/components/shared/CatalogGrid" },
  { module: "technique", file: "components/technique/FilterBar.tsx", sharedImportPath: "@/components/shared/LibraryFilterBar" },
  { module: "technique", file: "components/technique/ExerciseCard.tsx", sharedImportPath: "@/components/shared/LibraryEntityCard" },
  { module: "strength", file: "components/strength/CatalogGrid.tsx", sharedImportPath: "@/components/shared/CatalogGrid" },
  { module: "strength", file: "components/strength/FilterBar.tsx", sharedImportPath: "@/components/shared/LibraryFilterBar" },
  { module: "strength", file: "components/strength/ExerciseCard.tsx", sharedImportPath: "@/components/shared/LibraryEntityCard" },
];

describe("Técnica y fuerza renderizan a través de los componentes compartidos (no dos implementaciones paralelas)", () => {
  for (const { module, file, sharedImportPath } of WRAPPER_FILES) {
    it(`${file} (${module}) importa "${sharedImportPath}"`, () => {
      const source = readSource(file);
      const importPattern = new RegExp(`from\\s+["']${sharedImportPath.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}["']`);
      expect(source).toMatch(importPattern);
    });
  }

  it("ninguno de los seis wrappers reimplementa su propio bloque loading/error/empty (sin 'role=\"status\"' hardcodeado propio)", () => {
    // The shared CatalogGrid owns every role="status"/"alert" state marker.
    // A wrapper hardcoding its own would signal a parallel implementation
    // creeping back in alongside the shared one.
    const catalogGridWrappers = ["components/technique/CatalogGrid.tsx", "components/strength/CatalogGrid.tsx"];
    for (const file of catalogGridWrappers) {
      const source = readSource(file);
      expect(source).not.toMatch(/role=["']status["']/);
      expect(source).not.toMatch(/role=["']alert["']/);
    }
  });

  it("ninguno de los dos FilterBar reimplementa su propio useForm/RHF (el shell RHF vive solo en LibraryFilterBar)", () => {
    const filterBarWrappers = ["components/technique/FilterBar.tsx", "components/strength/FilterBar.tsx"];
    for (const file of filterBarWrappers) {
      const source = readSource(file);
      expect(source).not.toMatch(/useForm/);
    }
  });
});

// ---------------------------------------------------------------------------
// 2. Runtime guard — the shared shell is what actually mounts
// ---------------------------------------------------------------------------

describe("Técnica y fuerza montan el mismo shell CatalogGrid en tiempo de ejecución", () => {
  it("ambos wrappers producen el mismo patrón de skeleton (role=status + aria-busy) en loading", () => {
    const { unmount } = renderWithProviders(
      <TechniqueCatalogGrid
        items={undefined}
        total={undefined}
        isLoading
        isFetching={false}
        isError={false}
        error={null}
        hasActiveFilters={false}
      />,
    );
    const techniqueStatus = screen.getByRole("status");
    expect(techniqueStatus).toHaveAttribute("aria-busy", "true");
    unmount();

    renderWithProviders(
      <StrengthCatalogGrid
        items={undefined}
        total={undefined}
        isLoading
        isFetching={false}
        isError={false}
        error={null}
        hasActiveFilters={false}
      />,
    );
    const strengthStatus = screen.getByRole("status");
    expect(strengthStatus).toHaveAttribute("aria-busy", "true");
  });

  it("ambos wrappers detectan cold-start (network error) con la misma copy compartida 'servidor está iniciando'", () => {
    const { unmount } = renderWithProviders(
      <TechniqueCatalogGrid
        items={undefined}
        total={undefined}
        isLoading={false}
        isFetching={false}
        isError
        error={new Error("Network Error")}
        hasActiveFilters={false}
      />,
    );
    expect(screen.getByRole("status")).toHaveTextContent("El servidor está iniciando");
    unmount();

    renderWithProviders(
      <StrengthCatalogGrid
        items={undefined}
        total={undefined}
        isLoading={false}
        isFetching={false}
        isError
        error={new Error("Network Error")}
        hasActiveFilters={false}
      />,
    );
    expect(screen.getByRole("status")).toHaveTextContent("El servidor está iniciando");
  });
});
