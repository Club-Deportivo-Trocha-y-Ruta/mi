/**
 * GrowthTab.test.tsx — feature 040, US2 (T041).
 *
 * Cubre `contracts/growth-tab-ui.md`:
 *  - Composición modo coach (orden fijo): GrowthAlerts → GrowthStatusRow →
 *    NextMeasurementCard → TrainingReadiness → GrowthCurveSection (T052)
 *    → MorphologyCard → PHVExplanationCard → AnthropometryHistory (coach) →
 *    ResearchReferences.
 *  - Estados de carga/vacío/error del bloque resumen (fila "Status row /
 *    next measurement" de la tabla de estados del contrato).
 *
 * La composición del modo padre (rediseño familiar narrativo, feature 040
 * US4, T062) tiene su propio archivo dedicado y mucho más exhaustivo:
 * `GrowthTab.parent.test.tsx` (T056) — cubre `FamilyStageCard`/
 * `FamilyBandCards`/curva familiar/IA de solo lectura/historial, orden,
 * privacidad (sin Z-score/percentil/offset/bibliografía) y a11y. Este
 * archivo ya no incluye una suite "modo padre" propia (el diseño de
 * paridad-con-`MyAthleteDetailPage.tsx` que cubría quedó obsoleto al
 * aterrizar T062: `NutritionalClassification` dejó de montarse en modo
 * padre).
 *
 * Los hijos "pesados" existentes (`GrowthCurveSection`, `TrainingReadiness`,
 * `MorphologyCard`, `PHVExplanationCard`, `AnthropometryHistory`,
 * `NutritionalClassification`, `ResearchReferences`) se mockean para que
 * este archivo sólo ejercite la composición/orden/props de `GrowthTab`,
 * igual que `AthleteDetailPage.test.tsx`. `GrowthAlerts`/`GrowthStatusRow`/
 * `NextMeasurementCard` NO se mockean — ya tienen sus propios tests
 * unitarios (T038/T039) y aquí interesa verificar que reciben el
 * `GrowthSummary` real.
 *
 * Privacidad Ley 1581: fixtures 100% sintéticas (ningún atleta real), sin
 * fecha de nacimiento real ni nombre de un menor real.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// ---------------------------------------------------------------------------
// Mocks — deben declararse antes de los imports de producción
// ---------------------------------------------------------------------------

vi.mock("@/api/athletes", () => ({
  getAnthropometry: vi.fn(),
  createAnthropometry: vi.fn(),
}));

vi.mock("@/api/growth", () => ({
  getGrowthSummary: vi.fn(),
}));

vi.mock("@/components/athletes/AnthropometryHistory", () => ({
  AnthropometryHistory: ({ mode }: { mode?: string }) => (
    <div data-testid="anthropometry-history" data-mode={mode}>
      AnthropometryHistory
    </div>
  ),
}));

vi.mock("@/components/athletes/growth/GrowthCurveSection", () => ({
  GrowthCurveSection: ({ mode }: { mode?: string }) => (
    <div data-testid="growth-curve" data-mode={mode}>
      GrowthCurveSection
    </div>
  ),
}));

vi.mock("@/components/athletes/MorphologyCard", () => ({
  MorphologyCard: () => <div data-testid="morphology-card">MorphologyCard</div>,
}));

vi.mock("@/components/athletes/ResearchReferences", () => ({
  ResearchReferences: () => <div data-testid="research-references">ResearchReferences</div>,
}));

vi.mock("@/components/athletes/TrainingReadiness", () => ({
  TrainingReadiness: () => <div data-testid="training-readiness">TrainingReadiness</div>,
}));

vi.mock("@/components/ai/PHVExplanationCard", () => ({
  PHVExplanationCard: ({
    onMeasurementCTA,
    readOnly,
  }: {
    onMeasurementCTA?: () => void;
    readOnly?: boolean;
  }) => (
    <div data-testid="phv-explanation-card" data-readonly={readOnly ?? false}>
      {!readOnly && (
        <button type="button" onClick={onMeasurementCTA}>
          Agregar medicion
        </button>
      )}
    </div>
  ),
}));

// ---------------------------------------------------------------------------
// Imports de producción (después de mocks)
// ---------------------------------------------------------------------------

import { GrowthTab } from "@/components/athletes/growth/GrowthTab";
import * as athletesApi from "@/api/athletes";
import * as growthApi from "@/api/growth";
import { makeGrowthSummary, makeNeverGrowthSummary } from "@/test/msw/growthSummaryHandlers";
import { MaturationStatus, Sex } from "@/types/enums";
import type { AnthropometricRecord } from "@/types/anthropometry.types";
import type { AthleteDetailOut } from "@/types/athlete.types";

// ---------------------------------------------------------------------------
// Fixtures — sintéticas, sin datos reales de atletas.
// ---------------------------------------------------------------------------

const mockAthlete: AthleteDetailOut = {
  id: 2,
  user_id: 20,
  first_name: "Atleta",
  last_name: "Prueba",
  birth_date: "2013-03-10",
  sex: Sex.M,
  club_join_date: "2023-01-01",
  years_in_club: 2.0,
  age_decimal: 12.9,
  category: "Sub-13",
  club_id: 1,
  created_at: "2023-01-01T00:00:00Z",
  latest_anthropometry: null,
};

function makeRecord(overrides: Partial<AnthropometricRecord> = {}): AnthropometricRecord {
  return {
    id: 41,
    athlete_id: 2,
    evaluation_date: "2026-08-14",
    weight_kg: 45.0,
    standing_height_cm: 150.0,
    arm_span_cm: null,
    sitting_height_cm: 78.0,
    leg_length_cm: 72.0,
    leg_sitting_ratio: 0.923,
    maturity_offset: 1.2,
    age_at_phv: 12.9,
    maturation_status: MaturationStatus.PostPHV,
    training_implications: null,
    evaluated_by: 1,
    created_at: "2026-08-14T10:00:00",
    notes: null,
    height_percentile: 4.8,
    growth_source: "WHO",
    ...overrides,
  };
}

function renderGrowthTab(props: Partial<React.ComponentProps<typeof GrowthTab>> = {}) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <GrowthTab athlete={mockAthlete} mode="coach" {...props} />
    </QueryClientProvider>,
  );
}

describe("GrowthTab", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(athletesApi.getAnthropometry).mockResolvedValue([makeRecord()]);
    vi.mocked(growthApi.getGrowthSummary).mockResolvedValue(makeGrowthSummary());
  });

  it('expone data-testid="growth-tab" en la raíz', async () => {
    renderGrowthTab();
    expect(await screen.findByTestId("growth-status-row")).toBeInTheDocument();
    expect(screen.getByTestId("growth-tab")).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // Modo coach — composición y orden
  // -------------------------------------------------------------------------

  describe("modo coach", () => {
    it("renderiza los nueve bloques del contrato en el orden fijo", async () => {
      const { container } = renderGrowthTab();
      await screen.findByTestId("growth-status-row");

      const order = [
        "growth-status-row",
        "growth-next-measurement",
        "training-readiness",
        "growth-curve",
        "morphology-card",
        "phv-explanation-card",
        "anthropometry-history",
        "research-references",
      ];
      const positions = order.map((id) => {
        const el = container.querySelector(`[data-testid="${id}"]`);
        expect(el).not.toBeNull();
        return Array.from(container.querySelectorAll("[data-testid]")).indexOf(el as Element);
      });
      // Cada posición debe ser estrictamente creciente (mismo orden del contrato).
      for (let i = 1; i < positions.length; i += 1) {
        expect(positions[i]).toBeGreaterThan(positions[i - 1]);
      }
    });

    it("NO renderiza NutritionalClassification en modo coach (reemplazada por GrowthStatusRow)", async () => {
      renderGrowthTab();
      await screen.findByTestId("growth-status-row");
      expect(screen.queryByTestId("nutritional-classification")).not.toBeInTheDocument();
    });

    it("pasa mode=\"coach\" a AnthropometryHistory", async () => {
      renderGrowthTab();
      const history = await screen.findByTestId("anthropometry-history");
      expect(history).toHaveAttribute("data-mode", "coach");
    });

    it("PHVExplanationCard no es readOnly en modo coach", async () => {
      renderGrowthTab();
      const card = await screen.findByTestId("phv-explanation-card");
      expect(card).toHaveAttribute("data-readonly", "false");
    });

    it('el CTA de PHVExplanationCard invoca "onRecordMeasurement"', async () => {
      const onRecordMeasurement = vi.fn();
      renderGrowthTab({ onRecordMeasurement });
      await screen.findByTestId("phv-explanation-card");
      await userEvent.click(screen.getByRole("button", { name: /Agregar medicion/i }));
      expect(onRecordMeasurement).toHaveBeenCalledTimes(1);
    });

    it("renderiza GrowthAlerts cuando el resumen trae alertas compartidas con el dashboard", async () => {
      vi.mocked(growthApi.getGrowthSummary).mockResolvedValue(
        makeGrowthSummary({ alerts: ["rapid_growth"] }),
      );
      renderGrowthTab();
      expect(await screen.findByTestId("growth-alerts")).toBeInTheDocument();
    });

    it("no renderiza GrowthAlerts cuando el resumen no trae alertas", async () => {
      renderGrowthTab();
      await screen.findByTestId("growth-status-row");
      expect(screen.queryByTestId("growth-alerts")).not.toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // Bloque resumen — loading / error / empty (tabla de estados del contrato)
  // -------------------------------------------------------------------------

  describe("bloque resumen — estados", () => {
    it("muestra un estado de carga (role=status) mientras el resumen no resuelve", () => {
      vi.mocked(growthApi.getGrowthSummary).mockImplementation(
        () => new Promise(() => {}), // nunca resuelve dentro del test
      );
      renderGrowthTab();
      expect(screen.getByRole("status", { name: /Cargando resumen de crecimiento/i })).toBeInTheDocument();
      // El resto del tab (piezas independientes del resumen) sigue montado.
      expect(screen.getByTestId("training-readiness")).toBeInTheDocument();
    });

    it("muestra ErrorState con reintentar cuando el resumen falla", async () => {
      vi.mocked(growthApi.getGrowthSummary).mockRejectedValue(new Error("500"));
      renderGrowthTab();

      const retryButton = await screen.findByRole("button", { name: /Reintentar/i });
      expect(screen.getByText("No se pudo cargar el resumen de crecimiento.")).toBeInTheDocument();

      // Otras secciones (que no dependen del resumen) siguen visibles.
      expect(screen.getByTestId("training-readiness")).toBeInTheDocument();
      expect(screen.queryByTestId("growth-status-row")).not.toBeInTheDocument();

      vi.mocked(growthApi.getGrowthSummary).mockResolvedValue(makeGrowthSummary());
      await userEvent.click(retryButton);
      expect(await screen.findByTestId("growth-status-row")).toBeInTheDocument();
    });

    it('muestra EmptyState "Registra la primera medición" cuando records_count es 0', async () => {
      vi.mocked(growthApi.getGrowthSummary).mockResolvedValue(makeNeverGrowthSummary());
      const onRecordMeasurement = vi.fn();
      renderGrowthTab({ onRecordMeasurement });

      expect(await screen.findByText("Registra la primera medición")).toBeInTheDocument();
      await userEvent.click(screen.getByRole("button", { name: /Registrar medición/i }));
      expect(onRecordMeasurement).toHaveBeenCalledTimes(1);

      // El resto del tab sigue montado (TrainingReadiness/GrowthCurveSection/etc. no dependen del resumen).
      expect(screen.getByTestId("training-readiness")).toBeInTheDocument();
    });
  });

  // Modo padre: cubierto exhaustivamente por `GrowthTab.parent.test.tsx`
  // (T056) desde que T062 reemplazó la paridad-con-`MyAthleteDetailPage.tsx`
  // por el diseño familiar narrativo — ver docstring del módulo.
});
