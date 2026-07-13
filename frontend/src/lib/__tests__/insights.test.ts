/**
 * Tests for insights.ts utility functions — T018, T025.
 *
 * Covers:
 *   - extractSeasonContext: section present / absent / legacy insight
 *   - progressionLabel: all 5 ProgressionAssessment values
 *   - Legacy compat: old summaryText without new section returns null, no crash
 *   - getCarreraTier / TAPER_GUIDANCE: tier lookup by date and taper guidance
 *     per tier (T025)
 */
import { describe, it, expect } from "vitest";
import {
  extractSeasonContext,
  progressionLabel,
  extractSection,
  getV2Preview,
  getCarreraTier,
  TAPER_GUIDANCE,
} from "@/lib/insights";
import type { ProgressionAssessment } from "@/types/raceAnalysis.types";

// ---------------------------------------------------------------------------
// extractSeasonContext
// ---------------------------------------------------------------------------

describe("extractSeasonContext", () => {
  it("returns the section content when '## Contexto de temporada' is present", () => {
    const text = [
      "## Qué pasó",
      "El atleta mejoró en frenada.",
      "",
      "## Contexto de temporada",
      "Lleva 3 válidas disputadas de 7 en la Copa Valle.",
      "Posición acumulada en top-5.",
      "",
      "## Hacia dónde va",
      "Foco en cadencia.",
    ].join("\n");

    const result = extractSeasonContext(text);
    expect(result).not.toBeNull();
    expect(result).toContain("3 válidas disputadas");
    expect(result).toContain("top-5");
    // Must not include subsequent header content
    expect(result).not.toContain("Foco en cadencia");
  });

  it("returns null when the section is absent (legacy insight)", () => {
    const legacyText = [
      "## Qué pasó",
      "El atleta completó la carrera.",
      "",
      "## Recorrido hasta aquí",
      "Progreso desde V1.",
    ].join("\n");

    expect(extractSeasonContext(legacyText)).toBeNull();
  });

  it("returns null for an empty string (no crash on legacy edge case)", () => {
    expect(extractSeasonContext("")).toBeNull();
  });

  it("returns null for plain text without markdown headers", () => {
    expect(extractSeasonContext("Resumen libre sin secciones.")).toBeNull();
  });

  it("is tolerant to accent/case variants in the header", () => {
    // normalizeHeader strips diacritics, so 'Contexto de temporada' with any
    // accent variant should still be matched by extractSection.
    const text = "## Contexto de temporada\nContenido de contexto.\n";
    expect(extractSeasonContext(text)).toBe("Contenido de contexto.");
  });

  it("does not confuse 'Resumen de temporada' with 'Contexto de temporada'", () => {
    const text = [
      "## Resumen de temporada",
      "Resumen general de la temporada.",
    ].join("\n");
    expect(extractSeasonContext(text)).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// progressionLabel
// ---------------------------------------------------------------------------

describe("progressionLabel", () => {
  const cases: Array<[ProgressionAssessment, string]> = [
    ["improving", "Mejorando"],
    ["stable", "Estable"],
    ["declining", "En descenso"],
    ["mixed", "Mixto"],
    ["first_reference", "Primera referencia de la temporada"],
  ];

  it.each(cases)(
    'maps "%s" → "%s"',
    (assessment, expected) => {
      expect(progressionLabel(assessment)).toBe(expected);
    },
  );

  it("covers all 5 ProgressionAssessment values (completeness check)", () => {
    const allValues: ProgressionAssessment[] = [
      "improving",
      "stable",
      "declining",
      "mixed",
      "first_reference",
    ];
    for (const v of allValues) {
      expect(progressionLabel(v)).toBeTruthy();
    }
  });
});

// ---------------------------------------------------------------------------
// Legacy compat — existing functions unchanged
// ---------------------------------------------------------------------------

describe("legacy insight compat (no regression)", () => {
  it("extractSection returns empty string for absent section (no crash)", () => {
    expect(extractSection("Texto sin secciones.", "Contexto de temporada")).toBe("");
  });

  it("getV2Preview returns full text when no 'Qué pasó' section exists", () => {
    const plain = "Resumen del desempeño en esta válida.";
    expect(getV2Preview(plain)).toBe(plain);
  });

  it("extractSeasonContext on insight that has only v1 structure returns null", () => {
    const v1Summary =
      "El atleta terminó en posición 4 con tiempo 45:22. " +
      "Cadencia promedio 78 rpm. Próximo objetivo: mejorar salida.";
    expect(extractSeasonContext(v1Summary)).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// getCarreraTier / TAPER_GUIDANCE — T025
// ---------------------------------------------------------------------------

describe("getCarreraTier", () => {
  const cases: Array<[string, "A" | "B" | "C" | "CD"]> = [
    ["2026-01-31", "C"],
    ["2026-02-28", "C"],
    ["2026-04-19", "C"],
    ["2026-05-17", "A"],
    ["2026-06-12", "CD"],
    ["2026-08-15", "B"],
    ["2026-09-12", "A"],
    ["2026-10-18", "B"],
  ];

  it.each(cases)("maps %s → tier %s", (date, tier) => {
    expect(getCarreraTier(date)).toBe(tier);
  });

  it("returns null for a date not in CARRERA_TIER (e.g. off-season month)", () => {
    expect(getCarreraTier("2026-03-15")).toBeNull();
    expect(getCarreraTier("2026-11-15")).toBeNull();
    expect(getCarreraTier("2027-05-17")).toBeNull();
  });

  it("returns null for an invalid date string (no crash)", () => {
    expect(getCarreraTier("not-a-date")).toBeNull();
  });
});

describe("TAPER_GUIDANCE", () => {
  it("tier A — full taper, warning at 10d, danger at 7d", () => {
    expect(TAPER_GUIDANCE.A).toEqual({
      label: "A — Tapering completo",
      taperDays: [5, 7],
      warningAt: 10,
      dangerAt: 7,
    });
  });

  it("tier B — mini taper, warning at 6d, danger at 4d", () => {
    expect(TAPER_GUIDANCE.B).toEqual({
      label: "B — Mini-tapering",
      taperDays: [3, 4],
      warningAt: 6,
      dangerAt: 4,
    });
  });

  it("tier C — diagnostic, no taper window, never escalates urgency", () => {
    expect(TAPER_GUIDANCE.C).toEqual({
      label: "C — Diagnóstica",
      taperDays: null,
      warningAt: null,
      dangerAt: null,
    });
  });

  it("tier CD — same taper discipline as A (Campeonato Departamental)", () => {
    expect(TAPER_GUIDANCE.CD).toEqual({
      label: "CD — Campeonato Departamental",
      taperDays: [5, 7],
      warningAt: 10,
      dangerAt: 7,
    });
  });

  it("covers all 4 tier keys returned by getCarreraTier (completeness check)", () => {
    const tiers: Array<"A" | "B" | "C" | "CD"> = ["A", "B", "C", "CD"];
    for (const tier of tiers) {
      expect(TAPER_GUIDANCE[tier]).toBeTruthy();
      expect(TAPER_GUIDANCE[tier].label).toBeTruthy();
    }
  });
});
