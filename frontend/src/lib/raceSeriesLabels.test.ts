/**
 * Tests unitarios para raceSeriesLabels.ts (feature 023).
 *
 * Módulo puro: sin React, sin I/O, sin efectos secundarios.
 * Cubre ambos niveles (`departmental` | `national`) para cada función
 * exportada.
 */
import { describe, expect, it } from "vitest";

import {
  championshipLabel,
  championshipShortLabel,
  seriesChipLabel,
} from "./raceSeriesLabels";

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

// ---------------------------------------------------------------------------
// seriesChipLabel — hotfix multicopa (identidad de válida)
// ---------------------------------------------------------------------------

describe("seriesChipLabel", () => {
  it("prefiere short_name cuando está presente", () => {
    expect(seriesChipLabel("Copa Let's Go Interdepartamental XCO", "Let's GO")).toBe(
      "Let's GO",
    );
  });

  it("cae al name completo cuando short_name es null", () => {
    expect(seriesChipLabel("Copa Valle de Ciclomontañismo", null)).toBe(
      "Copa Valle de Ciclomontañismo",
    );
  });

  it("cae al name completo cuando short_name es undefined", () => {
    expect(seriesChipLabel("Copa Valle de Ciclomontañismo", undefined)).toBe(
      "Copa Valle de Ciclomontañismo",
    );
  });

  it("cae al name completo cuando short_name es una cadena en blanco", () => {
    expect(seriesChipLabel("Copa Valle de Ciclomontañismo", "   ")).toBe(
      "Copa Valle de Ciclomontañismo",
    );
  });
});
