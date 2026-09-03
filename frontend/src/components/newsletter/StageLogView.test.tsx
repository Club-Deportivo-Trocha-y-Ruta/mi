/**
 * StageLogView.test.tsx — feature 038, T301.
 *
 * Cubre: cada bloque se renderiza/oculta correctamente según los 3
 * fixtures (full month, mes sin carrera, mes con cero asistencia), y
 * cero placeholders de "sin información"/"sin datos" en ningún modo
 * (StageLogView es el mismo renderer para parent y para el preview del
 * estudio del coach — T302 es quien añade estados "Vacío"/"Oculto" por
 * fuera de este componente).
 */
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import {
  buildStageLogFullMonth,
  buildStageLogTrainingOnlyMonth,
  buildStageLogZeroAttendanceMonth,
} from "@/test/fixtures/stageLog";
import { StageLogView } from "./StageLogView";

// Frases que NUNCA deben aparecer — legado de NewsletterPreviewBlocks.tsx,
// prohibido explícitamente en la bitácora (AC-1.1).
const FORBIDDEN_PLACEHOLDERS = [
  /sin informaci[oó]n/i,
  /sin datos/i,
  /sin contenido/i,
  /sin novedades/i,
  /sin recomendaciones/i,
];

describe("StageLogView", () => {
  describe.each([
    ["coach", buildStageLogFullMonth()] as const,
    ["parent", buildStageLogFullMonth()] as const,
  ])("mode=%s — mes completo", (mode, stageLog) => {
    it("renderiza todos los bloques presentes en orden AC-1.1", () => {
      render(<StageLogView stageLog={stageLog} mode={mode} />);

      const root = screen.getByTestId("stage-log-view");
      const blocks = Array.from(root.querySelectorAll("[data-block]")).map((el) =>
        el.getAttribute("data-block"),
      );

      expect(blocks).toEqual([
        "header",
        "trail",
        "summit",
        "observations",
        "analyst-reading",
        "effort-profile",
        "next-segment",
        "family-compass",
        "badges",
        "photos",
        "coach-note",
      ]);
    });

    it("no imprime placeholders de 'sin información'", () => {
      render(<StageLogView stageLog={stageLog} mode={mode} />);
      const text = screen.getByTestId("stage-log-view").textContent ?? "";
      for (const pattern of FORBIDDEN_PLACEHOLDERS) {
        expect(text).not.toMatch(pattern);
      }
    });
  });

  it("mode=coach muestra la procedencia del insight (source_insight_id)", () => {
    render(<StageLogView stageLog={buildStageLogFullMonth()} mode="coach" />);
    expect(screen.getByTestId("analyst-reading-provenance")).toHaveTextContent("2001");
  });

  it("mode=parent NUNCA expone source_insight_id", () => {
    const fullMonth = buildStageLogFullMonth();
    // Simula el DTO de padre real: sin `source_insight_id` (to_parent_dto).
    const parentStageLog = {
      ...fullMonth,
      analyst_reading: {
        headline_family: fullMonth.analyst_reading!.headline_family,
        action_family: fullMonth.analyst_reading!.action_family,
        valida_label: fullMonth.analyst_reading!.valida_label,
      },
    };
    render(<StageLogView stageLog={parentStageLog} mode="parent" />);
    expect(screen.queryByTestId("analyst-reading-provenance")).not.toBeInTheDocument();
    expect(screen.queryByText(/2001/)).not.toBeInTheDocument();
  });

  describe("mes sin carrera (training-only)", () => {
    const stageLog = buildStageLogTrainingOnlyMonth();

    it("oculta el bloque de analista (no hubo InsightV3 ese mes)", () => {
      render(<StageLogView stageLog={stageLog} mode="parent" />);
      expect(screen.queryByTestId("analyst-reading")).not.toBeInTheDocument();
    });

    it("muestra un summit de tipo entrenamiento", () => {
      render(<StageLogView stageLog={stageLog} mode="parent" />);
      expect(screen.getByTestId("summit-card")).toHaveTextContent(
        "Mejor sesión de fondo del mes",
      );
    });

    it("no muestra el bloque de fotos (lista vacía)", () => {
      render(<StageLogView stageLog={stageLog} mode="parent" />);
      expect(screen.queryByTestId("photos-grid")).not.toBeInTheDocument();
    });

    it("no muestra nota del entrenador (coach_note es null)", () => {
      render(<StageLogView stageLog={stageLog} mode="parent" />);
      expect(screen.queryByTestId("coach-note")).not.toBeInTheDocument();
    });
  });

  describe("mes con cero asistencia", () => {
    const stageLog = buildStageLogZeroAttendanceMonth();

    it("oculta cima, analista, próximo tramo, brújula, insignias y fotos", () => {
      render(<StageLogView stageLog={stageLog} mode="parent" />);
      expect(screen.queryByTestId("summit-card")).not.toBeInTheDocument();
      expect(screen.queryByTestId("analyst-reading")).not.toBeInTheDocument();
      expect(screen.queryByTestId("next-segment")).not.toBeInTheDocument();
      expect(screen.queryByTestId("family-compass")).not.toBeInTheDocument();
      expect(screen.queryByTestId("badges-row")).not.toBeInTheDocument();
      expect(screen.queryByTestId("photos-grid")).not.toBeInTheDocument();
    });

    it("igual muestra header, trail (1 hito), observaciones y nota del entrenador", () => {
      render(<StageLogView stageLog={stageLog} mode="parent" />);
      expect(screen.getByTestId("stage-header")).toBeInTheDocument();
      expect(screen.getByTestId("trail-route")).toBeInTheDocument();
      expect(screen.getByTestId("observations-list")).toBeInTheDocument();
      expect(screen.getByTestId("coach-note")).toHaveTextContent(
        "Sin novedades este mes",
      );
    });

    it("no imprime ningún placeholder de 'sin información' pese a los bloques faltantes", () => {
      render(<StageLogView stageLog={stageLog} mode="parent" />);
      const text = screen.getByTestId("stage-log-view").textContent ?? "";
      // El único uso legítimo de "sin novedades" es la nota del entrenador
      // (texto libre del coach, no un placeholder generado por la UI) —
      // por eso se excluye ese patrón de esta aserción específica y en su
      // lugar se verifica cada patrón restante.
      expect(text).not.toMatch(/sin informaci[oó]n/i);
      expect(text).not.toMatch(/sin datos/i);
      expect(text).not.toMatch(/sin contenido/i);
      expect(text).not.toMatch(/sin recomendaciones/i);
    });
  });

  it("tiene data-surface='bitacora' en el contenedor raíz", () => {
    render(<StageLogView stageLog={buildStageLogFullMonth()} mode="parent" />);
    expect(screen.getByTestId("stage-log-view")).toHaveAttribute(
      "data-surface",
      "bitacora",
    );
  });
});
