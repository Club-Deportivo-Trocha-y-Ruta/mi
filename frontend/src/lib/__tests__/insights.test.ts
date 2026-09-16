/**
 * Tests for insights.ts utility functions — T018, T025.
 *
 * Covers:
 *   - extractSeasonContext: section present / absent / legacy insight
 *   - progressionLabel: all 5 ProgressionAssessment values
 *   - Legacy compat: old summaryText without new section returns null, no crash
 *   - TAPER_GUIDANCE: taper guidance per tier (T025) — `getCarreraTier`
 *     (hardcoded Copa Valle calendar) retired Wave 3 (hotfix multicopa,
 *     2026-09-16), tier now comes from `race_events.priority`.
 */
import { describe, it, expect } from "vitest";
import {
  extractSeasonContext,
  progressionLabel,
  extractSection,
  getV2Preview,
  TAPER_GUIDANCE,
  confidenceStatus,
  raceLabel,
  raceLabelForInsight,
} from "@/lib/insights";
import type { ProgressionAssessment } from "@/types/raceAnalysis.types";
import type { InsightConfidence } from "@/types/athleteRaceAnalysis.types";

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
// TAPER_GUIDANCE — T025. `getCarreraTier`/`CARRERA_TIER` (calendario Copa
// Valle hardcodeado por mes) se retiraron en Wave 3 del hotfix multicopa
// (2026-09-16) — el tier ahora viene de `race_events.priority`, real por
// evento; ver `NextRaceTile.tsx`/`InsightsTimeline.tsx`.
// ---------------------------------------------------------------------------

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

  it("has no 'CD' entry — call sites read a championship's priority as tier A, not a 4th tier", () => {
    expect(Object.keys(TAPER_GUIDANCE).sort()).toEqual(["A", "B", "C"]);
  });

  it("covers all 3 tiers of RaceEventPriority ('CD' excluded, see above)", () => {
    const tiers: Array<"A" | "B" | "C"> = ["A", "B", "C"];
    for (const tier of tiers) {
      expect(TAPER_GUIDANCE[tier]).toBeTruthy();
      expect(TAPER_GUIDANCE[tier].label).toBeTruthy();
    }
  });
});

// ---------------------------------------------------------------------------
// confidenceStatus — canonical adapter, contracts/status-vocabulary-sweep.md §4
// ---------------------------------------------------------------------------

describe("confidenceStatus", () => {
  it.each<[InsightConfidence, { status: string; label: string }]>([
    ["high", { status: "success", label: "Confianza alta" }],
    ["medium", { status: "warning", label: "Confianza media" }],
    ["low", { status: "danger", label: "Confianza baja" }],
  ])("%s → %o", (confidence, expected) => {
    expect(confidenceStatus(confidence)).toEqual(expected);
  });
});

// ---------------------------------------------------------------------------
// raceLabel / raceLabelForInsight — hotfix multicopa (2026-09-16, plans/
// multicopa-identidad-valida.md). Reemplaza a `validaLabel` como fuente
// única de verdad: SIEMPRE nombra la copa cuando el dato está disponible,
// para que dos copas con la misma Válida IV en la misma temporada no se
// lean (ni se agrupen) como si fueran la misma carrera.
// ---------------------------------------------------------------------------

describe("raceLabel", () => {
  it("form long: nombra la copa completa + válida romana + sede", () => {
    expect(
      raceLabel(
        {
          seriesName: "Copa Let's GO",
          seriesShortName: "Let's GO",
          validaNum: 4,
          isChampionship: false,
          location: "Alcalá",
        },
        { form: "long" },
      ),
    ).toBe("Copa Let's GO · Válida IV — Alcalá");
  });

  it("form chip: usa la abreviación + válida arábiga compacta", () => {
    expect(
      raceLabel(
        {
          seriesName: "Copa Let's GO",
          seriesShortName: "Let's GO",
          validaNum: 4,
          isChampionship: false,
        },
        { form: "chip" },
      ),
    ).toBe("Let's GO · V4");
  });

  it("dos copas comparten valida_num=4 pero producen etiquetas distintas (bug original)", () => {
    const copaValle = raceLabel(
      {
        seriesName: "Copa Valle de Ciclomontañismo",
        seriesShortName: "Copa Valle",
        validaNum: 4,
        isChampionship: false,
      },
      { form: "chip" },
    );
    const letsGo = raceLabel(
      {
        seriesName: "Copa Let's GO",
        seriesShortName: "Let's GO",
        validaNum: 4,
        isChampionship: false,
      },
      { form: "chip" },
    );
    expect(copaValle).toBe("Copa Valle · V4");
    expect(letsGo).toBe("Let's GO · V4");
    expect(copaValle).not.toBe(letsGo);
  });

  it("series_name/series_short_name ausentes (insight legacy) cae al rótulo sin copa, nunca inventa una", () => {
    expect(
      raceLabel({ validaNum: 4, isChampionship: false }, { form: "long" }),
    ).toBe("Válida IV");
    expect(
      raceLabel({ validaNum: 4, isChampionship: false }, { form: "chip" }),
    ).toBe("Válida IV");
  });

  it("chip prefiere seriesShortName sobre seriesName; long prefiere seriesName sobre seriesShortName", () => {
    const input = {
      seriesName: "Copa Let's GO",
      seriesShortName: "Let's GO",
      validaNum: 2,
      isChampionship: false,
    };
    expect(raceLabel(input, { form: "chip" })).toContain("Let's GO");
    expect(raceLabel(input, { form: "long" })).toContain("Copa Let's GO");
  });

  it("campeonato nunca lleva nombre de copa así se pase seriesName", () => {
    expect(
      raceLabel(
        {
          seriesName: "Copa Let's GO",
          seriesShortName: "Let's GO",
          validaNum: 1,
          isChampionship: true,
          seriesLevel: "national",
        },
        { form: "long" },
      ),
    ).toBe("Cto. Nacional");
  });

  it("seriesLevel='departmental' explícito → Cto. Departamental (feature 039, T039)", () => {
    expect(
      raceLabel(
        { validaNum: 1, isChampionship: true, seriesLevel: "departmental" },
        { form: "chip" },
      ),
    ).toBe("Cto. Departamental");
  });

  it("seriesLevel null/undefined cae al default histórico 'Cto. Departamental'", () => {
    expect(
      raceLabel({ validaNum: 1, isChampionship: true, seriesLevel: null }, { form: "chip" }),
    ).toBe("Cto. Departamental");
    expect(
      raceLabel({ validaNum: 1, isChampionship: true }, { form: "chip" }),
    ).toBe("Cto. Departamental");
  });

  it("valida_num=0 sigue siendo Resumen de temporada sin importar la copa", () => {
    expect(
      raceLabel(
        { seriesName: "Copa Let's GO", validaNum: 0, isChampionship: false },
        { form: "chip" },
      ),
    ).toBe("Resumen de temporada");
  });

  it("null/undefined validaNum → guión", () => {
    expect(raceLabel({ validaNum: null }, { form: "chip" })).toBe("—");
    expect(raceLabel({ validaNum: undefined }, { form: "long" })).toBe("—");
  });
});

describe("raceLabelForInsight", () => {
  it("deriva isChampionship de series_kind cuando está presente", () => {
    expect(
      raceLabelForInsight(
        {
          valida_num: 4,
          series_kind: "cup",
          series_name: "Copa Let's GO",
          series_short_name: "Let's GO",
        },
        "chip",
      ),
    ).toBe("Let's GO · V4");
  });

  it("sin series_kind cae al fallback legacy valida_num===99 (ej. ClubInsightByRaceItem)", () => {
    expect(raceLabelForInsight({ valida_num: 99 }, "chip")).toBe(
      "Cto. Departamental",
    );
    expect(raceLabelForInsight({ valida_num: 3 }, "chip")).toBe("Válida III");
  });

  it("series_id/series_name/series_short_name en null (fila previa a esta columna) no inventa una copa", () => {
    expect(
      raceLabelForInsight(
        {
          valida_num: 4,
          series_kind: "cup",
          series_name: null,
          series_short_name: null,
        },
        "long",
      ),
    ).toBe("Válida IV");
  });
});
