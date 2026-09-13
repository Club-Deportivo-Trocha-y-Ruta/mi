import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import type { UseQueryResult } from "@tanstack/react-query";

import { AnthropometryHistory } from "./AnthropometryHistory";
import { MaturationStatus } from "@/types/enums";
import type { AnthropometricRecord } from "@/types/anthropometry.types";
import type { AnthropometricRecordExplanationResponse } from "@/types/ai.types";

// ---------------------------------------------------------------------------
// Mocks — feature 042 (T076)
// ---------------------------------------------------------------------------

// La marca "Con señal para revisar" (`HistoryRowWarningMarker`) lee
// directamente `useMeasurementExplanationCached`; se mockea a nivel de hook
// (no de API/red) para poder controlar el dato cacheado por `recordId` sin
// necesitar un `QueryClientProvider` — la mayoría de los tests de este
// archivo no pasa `athleteId`, así que el hook nunca se invoca ahí.
vi.mock("@/hooks/ai/useMeasurementExplanation", () => ({
  useMeasurementExplanationCached: vi.fn(),
}));

// El modal migrado monta `AnthropometricRecordExplanationCard` cuando se le
// pasa `athleteId` — se mockea igual que en `LatestAnalysisLine.test.tsx`
// para las suites que sí pasan `athleteId` (marca de aviso), evitando
// llamadas HTTP reales. Las suites de foco/teclado NO pasan `athleteId`
// (mismo criterio que el resto de este archivo), así que ese bloque nunca
// se monta ahí y el mock es irrelevante para esas.
vi.mock("@/components/ai/AnthropometricRecordExplanationCard", () => ({
  AnthropometricRecordExplanationCard: ({
    athleteId,
    recordId,
  }: {
    athleteId: number;
    recordId: number;
  }) => (
    <div
      data-testid="mock-record-explanation-card"
      data-athlete-id={athleteId}
      data-record-id={recordId}
    >
      mock explanation
    </div>
  ),
}));

import { useMeasurementExplanationCached } from "@/hooks/ai/useMeasurementExplanation";

function mockCachedQuery(
  data: AnthropometricRecordExplanationResponse | null,
): UseQueryResult<AnthropometricRecordExplanationResponse | null, Error> {
  return {
    data,
    isLoading: false,
    isError: false,
    error: null,
  } as UseQueryResult<AnthropometricRecordExplanationResponse | null, Error>;
}

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function makeRecord(overrides: Partial<AnthropometricRecord> & { id: number }): AnthropometricRecord {
  return {
    athlete_id: 1,
    evaluation_date: "2026-01-15",
    weight_kg: 46.0,
    standing_height_cm: 157.0,
    arm_span_cm: null,
    sitting_height_cm: 74.0,
    leg_length_cm: 83.0,
    leg_sitting_ratio: 1.1216,
    maturity_offset: -0.3,
    age_at_phv: 13.0,
    maturation_status: MaturationStatus.CircaPHV,
    training_implications: null,
    evaluated_by: 1,
    created_at: "2026-01-15T00:00:00Z",
    notes: null,
    ...overrides,
  };
}

const record1 = makeRecord({
  id: 1,
  evaluation_date: "2025-06-01",
  weight_kg: 43.0,
  standing_height_cm: 152.0,
  maturity_offset: -1.5,
  maturation_status: MaturationStatus.PrePHV,
  training_implications: "Habilidades, juego, coordinacion.",
  notes: "Primera medición",
});

const record2 = makeRecord({
  id: 2,
  evaluation_date: "2026-01-15",
  weight_kg: 46.0,
  standing_height_cm: 157.0,
  maturity_offset: -0.3,
  maturation_status: MaturationStatus.CircaPHV,
  arm_span_cm: 158.0,
});

const record3 = makeRecord({
  id: 3,
  evaluation_date: "2026-04-01",
  weight_kg: 48.5,
  standing_height_cm: 160.0,
  maturity_offset: 1.2,
  maturation_status: MaturationStatus.PostPHV,
  arm_span_cm: 162.0,
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("AnthropometryHistory", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useMeasurementExplanationCached).mockReturnValue(mockCachedQuery(null));
  });

  // -------------------------------------------------------------------------
  // Estado de carga
  // -------------------------------------------------------------------------
  describe("cuando isLoading = true", () => {
    it("debería mostrar skeletons animados en lugar de la tabla", () => {
      const { container } = render(
        <AnthropometryHistory records={[]} isLoading={true} />
      );
      const skeletons = container.querySelectorAll(".animate-pulse");
      expect(skeletons.length).toBeGreaterThan(0);
    });

    it("no debería renderizar la tabla cuando está cargando", () => {
      render(<AnthropometryHistory records={[]} isLoading={true} />);
      expect(screen.queryByRole("table")).not.toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // Sin registros
  // -------------------------------------------------------------------------
  describe("cuando no hay registros", () => {
    it("debería mostrar mensaje de 'No hay mediciones registradas'", () => {
      render(<AnthropometryHistory records={[]} isLoading={false} />);
      expect(
        screen.getByText(/No hay mediciones registradas aún/i)
      ).toBeInTheDocument();
    });

    it("no debería renderizar tabla cuando no hay registros", () => {
      render(<AnthropometryHistory records={[]} isLoading={false} />);
      expect(screen.queryByRole("table")).not.toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // Tabla con registros
  // -------------------------------------------------------------------------
  describe("cuando hay registros", () => {
    it("debería renderizar la tabla con encabezados", () => {
      render(<AnthropometryHistory records={[record1, record2]} isLoading={false} />);
      expect(screen.getByRole("table")).toBeInTheDocument();
      expect(screen.getByText("Fecha")).toBeInTheDocument();
      expect(screen.getByText("Peso")).toBeInTheDocument();
      expect(screen.getByText("Talla")).toBeInTheDocument();
      expect(screen.getByText("Estado PHV")).toBeInTheDocument();
    });

    it("debería mostrar una fila por cada registro", () => {
      render(
        <AnthropometryHistory records={[record1, record2, record3]} isLoading={false} />
      );
      const rows = screen.getAllByRole("row");
      // 1 encabezado + 3 filas de datos
      expect(rows.length).toBe(4);
    });

    it("debería formatear la fecha como DD/MM/YYYY", () => {
      render(<AnthropometryHistory records={[record1]} isLoading={false} />);
      // record1.evaluation_date = "2025-06-01" → "01/06/2025" (aparece en mobile y desktop)
      const matches = screen.getAllByText("01/06/2025");
      expect(matches.length).toBeGreaterThanOrEqual(1);
    });

    it("debería mostrar el peso con unidad 'kg'", () => {
      render(<AnthropometryHistory records={[record1]} isLoading={false} />);
      // Aparece en card mobile y tabla desktop
      const matches = screen.getAllByText("43 kg");
      expect(matches.length).toBeGreaterThanOrEqual(1);
    });

    it("debería mostrar la talla con unidad 'cm'", () => {
      render(<AnthropometryHistory records={[record1]} isLoading={false} />);
      // Aparece en card mobile y tabla desktop
      const matches = screen.getAllByText("152 cm");
      expect(matches.length).toBeGreaterThanOrEqual(1);
    });

    it("debería mostrar la envergadura en la columna cuando existe", () => {
      render(<AnthropometryHistory records={[record2]} isLoading={false} />);
      // Aparece en card mobile y tabla desktop
      const matches = screen.getAllByText("158 cm");
      expect(matches.length).toBeGreaterThanOrEqual(1);
    });

    it("debería mostrar '-' cuando arm_span_cm es null", () => {
      render(<AnthropometryHistory records={[record1]} isLoading={false} />);
      // Al menos un '-' en la tabla desktop
      const dashes = screen.getAllByText("-");
      expect(dashes.length).toBeGreaterThanOrEqual(1);
    });

    it("debería formatear maturity_offset negativo sin signo extra", () => {
      render(<AnthropometryHistory records={[record1]} isLoading={false} />);
      // record1.maturity_offset = -1.5 → "-1.50" (aparece en card mobile y desktop)
      const matches = screen.getAllByText("-1.50");
      expect(matches.length).toBeGreaterThanOrEqual(1);
    });

    it("debería formatear maturity_offset positivo con signo '+'", () => {
      render(<AnthropometryHistory records={[record3]} isLoading={false} />);
      // record3.maturity_offset = 1.2 → "+1.20" (aparece en card mobile y desktop)
      const matches = screen.getAllByText("+1.20");
      expect(matches.length).toBeGreaterThanOrEqual(1);
    });
  });

  // -------------------------------------------------------------------------
  // Orden de registros (más reciente primero)
  // -------------------------------------------------------------------------
  describe("ordenamiento de registros", () => {
    it("debería mostrar el registro más reciente primero", () => {
      render(
        <AnthropometryHistory records={[record1, record2, record3]} isLoading={false} />
      );
      const rows = screen.getAllByRole("row");
      // Fila 1 (índice 1 = primera data row) debe tener la fecha más reciente
      // record3 = "2026-04-01" → "01/04/2026"
      expect(rows[1]).toHaveTextContent("01/04/2026");
    });

    it("debería mostrar el registro más antiguo al final", () => {
      render(
        <AnthropometryHistory records={[record1, record2, record3]} isLoading={false} />
      );
      const rows = screen.getAllByRole("row");
      // Última fila data = record1 = "2025-06-01" → "01/06/2025"
      expect(rows[rows.length - 1]).toHaveTextContent("01/06/2025");
    });
  });

  // -------------------------------------------------------------------------
  // Modal de detalle al hacer clic
  // -------------------------------------------------------------------------
  describe("modal de detalle", () => {
    it("no debería mostrar modal al inicio", () => {
      render(<AnthropometryHistory records={[record1]} isLoading={false} />);
      expect(screen.queryByText(/Medición del/i)).not.toBeInTheDocument();
    });

    it("debería mostrar el modal al hacer clic en una fila", async () => {
      const user = userEvent.setup();
      render(<AnthropometryHistory records={[record1]} isLoading={false} />);
      const rows = screen.getAllByRole("row");
      await user.click(rows[1]); // primera fila de datos
      expect(screen.getByText(/Medición del 01\/06\/2025/i)).toBeInTheDocument();
    });

    it("debería mostrar el peso del registro en el modal", async () => {
      const user = userEvent.setup();
      render(<AnthropometryHistory records={[record1]} isLoading={false} />);
      const rows = screen.getAllByRole("row");
      await user.click(rows[1]);
      expect(screen.getByText(/Peso: 43 kg/)).toBeInTheDocument();
    });

    it("debería mostrar implicaciones de entrenamiento si existen", async () => {
      const user = userEvent.setup();
      render(<AnthropometryHistory records={[record1]} isLoading={false} />);
      const rows = screen.getAllByRole("row");
      await user.click(rows[1]);
      expect(
        screen.getByText("Habilidades, juego, coordinacion.")
      ).toBeInTheDocument();
    });

    it("debería mostrar notas si existen", async () => {
      const user = userEvent.setup();
      render(<AnthropometryHistory records={[record1]} isLoading={false} />);
      const rows = screen.getAllByRole("row");
      await user.click(rows[1]);
      expect(screen.getByText("Primera medición")).toBeInTheDocument();
    });

    it("debería mostrar 'No registrada' para envergadura nula", async () => {
      const user = userEvent.setup();
      render(<AnthropometryHistory records={[record1]} isLoading={false} />);
      const rows = screen.getAllByRole("row");
      await user.click(rows[1]);
      expect(screen.getByText(/No registrada/)).toBeInTheDocument();
    });

    it("debería cerrar el modal al hacer clic en el botón 'x'", async () => {
      const user = userEvent.setup();
      render(<AnthropometryHistory records={[record1]} isLoading={false} />);
      const rows = screen.getAllByRole("row");
      await user.click(rows[1]);
      // Confirmar que el modal está abierto
      expect(screen.getByText(/Medición del/i)).toBeInTheDocument();
      // Cerrar con el botón x (aria-label="Cerrar")
      await user.click(screen.getByRole("button", { name: "Cerrar" }));
      expect(screen.queryByText(/Medición del/i)).not.toBeInTheDocument();
    });

    it("debería cerrar el modal al hacer clic en el backdrop", async () => {
      const user = userEvent.setup();
      render(<AnthropometryHistory records={[record1]} isLoading={false} />);
      const rows = screen.getAllByRole("row");
      await user.click(rows[1]);
      expect(screen.getByText(/Medición del/i)).toBeInTheDocument();
      // Feature 042 (T075): el modal migró a la primitiva `Dialog` (Radix),
      // que renderiza el overlay en un portal fuera del `container` de RTL
      // — por eso se busca en `document`, no en `container`.
      const backdrop = document.querySelector(".fixed.inset-0");
      expect(backdrop).not.toBeNull();
      await user.click(backdrop!);
      expect(screen.queryByText(/Medición del/i)).not.toBeInTheDocument();
    });

    it("debería mostrar la envergadura cuando existe", async () => {
      const user = userEvent.setup();
      render(<AnthropometryHistory records={[record3]} isLoading={false} />);
      const rows = screen.getAllByRole("row");
      await user.click(rows[1]);
      // record3.arm_span_cm = 162.0 — aparece en la columna de la tabla y dentro del modal
      expect(screen.getByText(/Envergadura: 162/)).toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // Modal de detalle — foco y teclado (feature 042, T075/T076): el modal
  // migró a la primitiva `Dialog` compartida (Radix). Se prueba como
  // COMPORTAMIENTO (eventos de teclado / foco real), nunca leyendo props.
  // -------------------------------------------------------------------------
  describe("modal de detalle — foco y teclado", () => {
    it("Escape cierra el modal", async () => {
      const user = userEvent.setup();
      render(<AnthropometryHistory records={[record1]} isLoading={false} />);
      await user.click(
        screen.getByRole("button", {
          name: /Ver detalle de medición del 01\/06\/2025/i,
        }),
      );
      expect(screen.getByRole("dialog")).toBeInTheDocument();

      await user.keyboard("{Escape}");

      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
      expect(screen.queryByText(/Medición del/i)).not.toBeInTheDocument();
    });

    it("el foco queda ATRAPADO dentro del diálogo: Tab repetido nunca sale de su contenido", async () => {
      const user = userEvent.setup();
      render(<AnthropometryHistory records={[record1]} isLoading={false} />);
      await user.click(
        screen.getByRole("button", {
          name: /Ver detalle de medición del 01\/06\/2025/i,
        }),
      );
      const dialog = screen.getByRole("dialog");

      // Más vueltas que elementos enfocables dentro del modal — si el foco
      // se escapara, alguna de estas aserciones fallaría.
      for (let i = 0; i < 12; i += 1) {
        await user.tab();
        expect(dialog.contains(document.activeElement)).toBe(true);
      }
    });

    it("Shift+Tab desde el primer elemento enfocable tampoco saca el foco del diálogo", async () => {
      const user = userEvent.setup();
      render(<AnthropometryHistory records={[record1]} isLoading={false} />);
      await user.click(
        screen.getByRole("button", {
          name: /Ver detalle de medición del 01\/06\/2025/i,
        }),
      );
      const dialog = screen.getByRole("dialog");

      await user.tab({ shift: true });
      expect(dialog.contains(document.activeElement)).toBe(true);
    });

    it("el foco vuelve al botón disparador al cerrar con Escape", async () => {
      const user = userEvent.setup();
      render(<AnthropometryHistory records={[record1]} isLoading={false} />);
      const trigger = screen.getByRole("button", {
        name: /Ver detalle de medición del 01\/06\/2025/i,
      });

      await user.click(trigger);
      expect(screen.getByRole("dialog")).toBeInTheDocument();

      await user.keyboard("{Escape}");

      await waitFor(() => {
        expect(trigger).toHaveFocus();
      });
    });

    it("el foco vuelve al botón disparador al cerrar con el control 'Cerrar' (≥48 px, FR-031)", async () => {
      const user = userEvent.setup();
      render(<AnthropometryHistory records={[record1]} isLoading={false} />);
      const trigger = screen.getByRole("button", {
        name: /Ver detalle de medición del 01\/06\/2025/i,
      });

      await user.click(trigger);
      await user.click(screen.getByRole("button", { name: "Cerrar" }));

      await waitFor(() => {
        expect(trigger).toHaveFocus();
      });
    });

    it("sin violaciones jest-axe con el diálogo abierto (Radix lo renderiza en un portal fuera de `container`)", async () => {
      const user = userEvent.setup();
      render(<AnthropometryHistory records={[record1]} isLoading={false} />);
      await user.click(
        screen.getByRole("button", {
          name: /Ver detalle de medición del 01\/06\/2025/i,
        }),
      );
      expect(screen.getByRole("dialog")).toBeInTheDocument();

      expect(await axe(document.body)).toHaveNoViolations();
    });
  });

  // -------------------------------------------------------------------------
  // Marca "Con señal para revisar" (feature 042, FR-028/T076)
  // -------------------------------------------------------------------------
  describe("marca 'Con señal para revisar'", () => {
    const withWarning: AnthropometricRecordExplanationResponse = {
      schema_version: "v2",
      text: "Resumen sintético con una señal de aviso.",
      model: "fake-model",
      provider: "fake",
      generated_at: "2026-01-15T10:00:00Z",
      age_group: "10-12",
      maturation_status: MaturationStatus.CircaPHV,
      record_id: record2.id,
      num_previous_measurements: 1,
      delta_height_cm: 1.0,
      delta_weight_kg: 0.5,
      structured: {
        summary_line: "Cambio de talla dentro de lo esperado.",
        changes: [],
        meaning: [],
        next_weeks: [],
        warning_signs: ["Señal sintética de ejemplo — sin dato real de un menor."],
        confidence: { level: "medium", reason: "Motivo sintético." },
        data_gaps: [],
      },
      critic_verdict: "approved",
      is_fallback: false,
      prompt_version: "anthropometry_analyst_v1",
      trace_id: "deadbeefcafef00d",
    };

    const withoutWarning: AnthropometricRecordExplanationResponse = {
      ...withWarning,
      record_id: record3.id,
      structured: { ...withWarning.structured, warning_signs: [] },
    };

    beforeEach(() => {
      vi.mocked(useMeasurementExplanationCached).mockImplementation(
        (_athleteId: number, recordId: number) => {
          if (recordId === record2.id) return mockCachedQuery(withWarning);
          if (recordId === record3.id) return mockCachedQuery(withoutWarning);
          return mockCachedQuery(null);
        },
      );
    });

    it("aparece SOLO en la fila cuyo análisis trae señales de aviso, en la tabla de escritorio", () => {
      render(
        <AnthropometryHistory
          records={[record2, record3]}
          isLoading={false}
          athleteId={7}
        />,
      );
      const desktop = screen.getByTestId("anthropometry-history-desktop");
      expect(within(desktop).getAllByTestId("history-warning-marker")).toHaveLength(1);

      const rows = within(desktop).getAllByRole("row");
      // Fila 1 = record3 (más reciente, "01/04/2026", sin señales);
      // fila 2 = record2 ("15/01/2026", con señales).
      expect(within(rows[1]).queryByTestId("history-warning-marker")).not.toBeInTheDocument();
      expect(within(rows[2]).getByTestId("history-warning-marker")).toBeInTheDocument();
    });

    it("aparece SOLO en la tarjeta correspondiente de la vista móvil", () => {
      render(
        <AnthropometryHistory
          records={[record2, record3]}
          isLoading={false}
          athleteId={7}
        />,
      );
      const mobile = screen.getByTestId("anthropometry-history");
      expect(within(mobile).getAllByTestId("history-warning-marker")).toHaveLength(1);
    });

    it("NO aparece cuando la fila no es entregable a la familia (verdict bloqueado → 204/null en caché)", () => {
      // El backend nunca deja pasar un veredicto flagged/fallback/skipped a
      // un padre — llega como `204`, indistinguible de "sin análisis
      // todavía" (`hasWarningSigns(null) === false`). Se simula aquí
      // devolviendo `null` para el registro que en el fondo SÍ tiene
      // señales (record2), como haría el gate familiar del backend.
      vi.mocked(useMeasurementExplanationCached).mockReturnValue(mockCachedQuery(null));
      render(
        <AnthropometryHistory
          records={[record2]}
          isLoading={false}
          athleteId={7}
          mode="parent"
        />,
      );
      expect(screen.queryByTestId("history-warning-marker")).not.toBeInTheDocument();
    });

    it("no se monta (ni invoca el hook) cuando no se pasa athleteId", () => {
      render(<AnthropometryHistory records={[record2]} isLoading={false} />);
      expect(screen.queryByTestId("history-warning-marker")).not.toBeInTheDocument();
      expect(useMeasurementExplanationCached).not.toHaveBeenCalled();
    });
  });

  // -------------------------------------------------------------------------
  // Modo familia (feature 040, FR-016): sin offset, etapa clínica ni edad PHV
  // -------------------------------------------------------------------------
  describe("en modo parent", () => {
    it("oculta las columnas clínicas de la tabla y de las tarjetas móviles", () => {
      render(
        <AnthropometryHistory records={[record1, record2]} isLoading={false} mode="parent" />
      );
      expect(screen.getByRole("table")).toBeInTheDocument();
      expect(screen.getByText("Peso")).toBeInTheDocument();
      expect(screen.queryByText("Offset")).not.toBeInTheDocument();
      expect(screen.queryByText("Estado PHV")).not.toBeInTheDocument();
      expect(screen.queryByText("Edad PHV")).not.toBeInTheDocument();
      expect(screen.queryByText(/Offset:/)).not.toBeInTheDocument();
      expect(screen.queryByText(/Pre-PHV|Circa-PHV|Post-PHV/)).not.toBeInTheDocument();
    });

    it("oculta el offset, la edad al PHV, el estado y las implicaciones en el detalle", async () => {
      const user = userEvent.setup();
      render(<AnthropometryHistory records={[record1]} isLoading={false} mode="parent" />);
      await user.click(screen.getAllByText("01/06/2025")[0]);
      expect(screen.getByText(/Peso: 43/)).toBeInTheDocument();
      expect(screen.queryByText(/Maturity Offset/)).not.toBeInTheDocument();
      expect(screen.queryByText(/Edad al PHV/)).not.toBeInTheDocument();
      expect(screen.queryByText("Estado:")).not.toBeInTheDocument();
      expect(screen.queryByText(/Implicaciones de entrenamiento/)).not.toBeInTheDocument();
      expect(screen.queryByText(/Pre-PHV/)).not.toBeInTheDocument();
    });

    it("en modo coach sigue mostrando las columnas clínicas", () => {
      render(<AnthropometryHistory records={[record1]} isLoading={false} mode="coach" />);
      expect(screen.getByText("Estado PHV")).toBeInTheDocument();
      expect(screen.getByText("Edad PHV")).toBeInTheDocument();
    });
  });
});
