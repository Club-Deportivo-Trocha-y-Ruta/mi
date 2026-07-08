/**
 * Tests unitarios para raceSeriesLabels.ts (feature 023).
 *
 * Módulo puro: sin React, sin I/O, sin efectos secundarios.
 * Cubre ambos niveles (`departmental` | `national`) para cada función
 * exportada.
 */
import { describe, expect, it } from "vitest";

import { championshipLabel, championshipShortLabel } from "./raceSeriesLabels";

// ---------------------------------------------------------------------------
// championshipLabel — etiqueta larga
// ---------------------------------------------------------------------------

describe("championshipLabel", () => {
  it("devuelve 'Campeonato Nacional' para level 'national'", () => {
    expect(championshipLabel("national")).toBe("Campeonato Nacional");
  });

  it("devuelve 'Campeonato Departamental' para level 'departmental'", () => {
    expect(championshipLabel("departmental")).toBe("Campeonato Departamental");
  });
});

// ---------------------------------------------------------------------------
// championshipShortLabel — etiqueta corta
// ---------------------------------------------------------------------------

describe("championshipShortLabel", () => {
  it("devuelve 'Cto. Nal.' para level 'national'", () => {
    expect(championshipShortLabel("national")).toBe("Cto. Nal.");
  });

  it("devuelve 'Cto. Dep.' para level 'departmental'", () => {
    expect(championshipShortLabel("departmental")).toBe("Cto. Dep.");
  });
});
