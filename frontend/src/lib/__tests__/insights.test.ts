/**
 * Tests for insights.ts utility functions — T018.
 *
 * Covers:
 *   - extractSeasonContext: section present / absent / legacy insight
 *   - progressionLabel: all 5 ProgressionAssessment values
 *   - Legacy compat: old summaryText without new section returns null, no crash
 */
import { describe, it, expect } from "vitest";
import {
  extractSeasonContext,
  progressionLabel,
  extractSection,
  getV2Preview,
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
