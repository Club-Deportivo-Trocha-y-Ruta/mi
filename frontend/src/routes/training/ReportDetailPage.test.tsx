/**
 * ReportDetailPage.test.tsx
 *
 * Tests para el editor del Informe Técnico Mensual.
 * Coach view (rol coach): acceso completo con bloques editables, aprobar, descargar.
 * Parent view (rol parent): solo lectura, sin bloques narrativos.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe, toHaveNoViolations } from "jest-axe";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

expect.extend(toHaveNoViolations);

// axe "region" desactivada: el layout de la página vive dentro del shell de
// rutas (sin landmarks propios en el árbol renderizado por el test); no es
// una regresión de accesibilidad real del componente bajo prueba.
const AXE_OPTIONS = {
  rules: {
    region: { enabled: false },
  },
} as const;

vi.mock("@/api/client", () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
  },
  registerAuthHandlers: vi.fn(),
}));

vi.mock("@/api/trainingSessions", () => ({
  useMonthlyReport: vi.fn(),
  useDownloadMonthlyReportPdf: vi.fn(),
  useDownloadMonthlyReportDocx: vi.fn(),
  useUpdateReportBlocks: vi.fn(),
  useRegenerateBlock: vi.fn(),
}));

vi.mock("@/store/auth.store", () => ({
  useAuthStore: vi.fn((sel: (s: unknown) => unknown) =>
    sel({
      accessToken: "tok",
      user: { role: "coach", first_name: "Juan", last_name: "T", club_ids: [1] },
    }),
  ),
}));

vi.mock("@/components/training/MonthlyMetricsTable", () => ({
  MonthlyMetricsTable: () => <div data-testid="metrics-table">Métricas</div>,
}));

import {
  useMonthlyReport,
  useDownloadMonthlyReportPdf,
  useDownloadMonthlyReportDocx,
  useUpdateReportBlocks,
  useRegenerateBlock,
} from "@/api/trainingSessions";
import { useAuthStore } from "@/store/auth.store";
import { ReportDetailPage } from "./ReportDetailPage";
import {
  sessionDetailItemSchema,
  athleteAttendanceStatsAdditiveSchema,
  competitionResultAdditiveSchema,
} from "@/schemas/monthlyReport.schema";
import type { MonthlyReportFull, NarrativeBlockKey } from "@/types/trainingSession.types";

// Orden aprobado de bloques narrativos del Informe Técnico Mensual — debe
// incluir "plan_entrenamiento" (feature 022). Espejo de `BLOCK_ORDER` en
// `ReportDetailPage.tsx`; se re-declara aquí (no exportado) para verificar
// el contrato de render sin acoplar el test a un símbolo interno.
const BLOCK_ORDER: NarrativeBlockKey[] = [
  "objetivo",
  "plan_entrenamiento",
  "desarrollo",
  "competencia",
  "resultados",
  "conclusiones",
  "apoyos_materiales",
  "analisis_grupo",
];

// ---------------------------------------------------------------------------
// Stubs
// ---------------------------------------------------------------------------

const mutationStub = {
  mutate: vi.fn(),
  isPending: false,
  isError: false,
  isSuccess: false,
  isIdle: true,
  data: undefined,
  error: null,
  reset: vi.fn(),
  mutateAsync: vi.fn(),
  variables: undefined,
};

function makeBlock(overrides?: object) {
  return {
    ai_draft: "Borrador IA.",
    final_text: null,
    ai_model: "gemini",
    ai_generated_at: "2026-06-01T00:00:00Z",
    ...overrides,
  };
}

const ALL_BLOCK_KEYS: NarrativeBlockKey[] = [
  "objetivo", "plan_entrenamiento", "desarrollo", "resultados", "conclusiones",
  "apoyos_materiales", "analisis_grupo", "competencia",
];

function makeReport(overrides?: Partial<MonthlyReportFull>): MonthlyReportFull {
  const blocks = Object.fromEntries(ALL_BLOCK_KEYS.map((k) => [k, makeBlock()])) as Record<NarrativeBlockKey, ReturnType<typeof makeBlock>>;
  return {
    id: 1,
    club_id: 1,
    year: 2026,
    month: 4,
    ai_summary: null,
    metrics_snapshot: {
      total_sessions_planned: 8,
      total_sessions_executed: 7,
      total_sessions_cancelled: 1,
      technical_focus_list: ["Frenada"],
      avg_rpe: 6.5,
      avg_rubric_effort: 4.2,
      avg_rubric_attitude: 4.8,
      avg_rubric_technique: 3.9,
    },
    coach_observations: "Buena actitud.",
    generated_by_user_id: 10,
    generated_at: "2026-05-01T10:00:00Z",
    status: "draft",
    narrative_blocks: blocks,
    competition_results: [],
    ...overrides,
  };
}

function renderPage(year = "2026", month = "4") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[`/training/reports/${year}/${month}`]}>
        <Routes>
          <Route path="/training/reports/:year/:month" element={<ReportDetailPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

// ---------------------------------------------------------------------------
// Setup
// ---------------------------------------------------------------------------

beforeEach(() => {
  vi.mocked(useDownloadMonthlyReportPdf).mockReturnValue(
    mutationStub as unknown as ReturnType<typeof useDownloadMonthlyReportPdf>,
  );
  vi.mocked(useDownloadMonthlyReportDocx).mockReturnValue(
    mutationStub as unknown as ReturnType<typeof useDownloadMonthlyReportDocx>,
  );
  vi.mocked(useUpdateReportBlocks).mockReturnValue(
    mutationStub as unknown as ReturnType<typeof useUpdateReportBlocks>,
  );
  vi.mocked(useRegenerateBlock).mockReturnValue(
    mutationStub as unknown as ReturnType<typeof useRegenerateBlock>,
  );
  // Default: coach role
  const coachState = {
    accessToken: "tok",
    user: { role: "coach", first_name: "Juan", last_name: "T", club_ids: [1] },
  };
  vi.mocked(useAuthStore).mockImplementation(
    ((sel: (s: typeof coachState) => unknown) => sel(coachState)) as unknown as typeof useAuthStore,
  );
});

// ---------------------------------------------------------------------------
// Tests — coach view
// ---------------------------------------------------------------------------

describe("ReportDetailPage — coach", () => {
  it("renderiza título con mes y año y badge borrador", () => {
    vi.mocked(useMonthlyReport).mockReturnValue({
      isLoading: false,
      isError: false,
      data: makeReport(),
    } as unknown as ReturnType<typeof useMonthlyReport>);
    renderPage();
    expect(screen.getByText(/Informe Técnico — Abril 2026/i)).toBeInTheDocument();
    expect(screen.getByTestId("status-badge-draft")).toBeInTheDocument();
  });

  it("muestra badge 'Aprobado' cuando status es approved", () => {
    vi.mocked(useMonthlyReport).mockReturnValue({
      isLoading: false,
      isError: false,
      data: makeReport({ status: "approved" }),
    } as unknown as ReturnType<typeof useMonthlyReport>);
    renderPage();
    expect(screen.getByTestId("status-badge-approved")).toBeInTheDocument();
  });

  it("renderiza los 8 bloques narrativos editables, incl. plan_entrenamiento", () => {
    vi.mocked(useMonthlyReport).mockReturnValue({
      isLoading: false,
      isError: false,
      data: makeReport(),
    } as unknown as ReturnType<typeof useMonthlyReport>);
    renderPage();
    for (const key of ALL_BLOCK_KEYS) {
      expect(screen.getByTestId(`block-editor-${key}`)).toBeInTheDocument();
    }
    expect(screen.getByTestId("block-editor-plan_entrenamiento")).toBeInTheDocument();
  });

  it("BLOCK_ORDER incluye 'plan_entrenamiento' y se renderiza en el orden aprobado", () => {
    expect(BLOCK_ORDER).toContain("plan_entrenamiento");
    vi.mocked(useMonthlyReport).mockReturnValue({
      isLoading: false,
      isError: false,
      data: makeReport(),
    } as unknown as ReturnType<typeof useMonthlyReport>);
    renderPage();
    const editors = screen.getAllByTestId(/^block-editor-/);
    const renderedOrder = editors.map(
      (el) => el.getAttribute("data-testid")?.replace("block-editor-", ""),
    );
    expect(renderedOrder).toEqual(BLOCK_ORDER);
  });

  it("el botón 'Aprobar' llama a updateReportBlocks con status=approved", () => {
    const mutateMock = vi.fn();
    vi.mocked(useUpdateReportBlocks).mockReturnValue({
      ...mutationStub,
      mutate: mutateMock,
    } as unknown as ReturnType<typeof useUpdateReportBlocks>);
    vi.mocked(useMonthlyReport).mockReturnValue({
      isLoading: false,
      isError: false,
      data: makeReport(),
    } as unknown as ReturnType<typeof useMonthlyReport>);
    renderPage();
    fireEvent.click(screen.getByTestId("approve-btn"));
    expect(mutateMock).toHaveBeenCalledWith(
      { status: "approved" },
      expect.anything(),
    );
  });

  it("el botón 'Aprobar' está deshabilitado si status es approved", () => {
    vi.mocked(useMonthlyReport).mockReturnValue({
      isLoading: false,
      isError: false,
      data: makeReport({ status: "approved" }),
    } as unknown as ReturnType<typeof useMonthlyReport>);
    renderPage();
    expect(screen.getByTestId("approve-btn")).toBeDisabled();
  });

  it("editar un bloque y guardar llama a updateReportBlocks con el texto", async () => {
    const mutateMock = vi.fn();
    vi.mocked(useUpdateReportBlocks).mockReturnValue({
      ...mutationStub,
      mutate: mutateMock,
    } as unknown as ReturnType<typeof useUpdateReportBlocks>);
    vi.mocked(useMonthlyReport).mockReturnValue({
      isLoading: false,
      isError: false,
      data: makeReport(),
    } as unknown as ReturnType<typeof useMonthlyReport>);
    renderPage();

    const textarea = screen.getByTestId("block-textarea-objetivo");
    fireEvent.change(textarea, { target: { value: "Nuevo objetivo redactado" } });
    fireEvent.click(screen.getByTestId("save-btn-objetivo"));

    await waitFor(() => {
      expect(mutateMock).toHaveBeenCalledWith(
        { blocks: { objetivo: "Nuevo objetivo redactado" } },
        expect.anything(),
      );
    });
  });

  it("el botón 'Generar con IA' llama a regenerateBlock con la clave correcta", () => {
    const mutateMock = vi.fn();
    vi.mocked(useRegenerateBlock).mockReturnValue({
      ...mutationStub,
      mutate: mutateMock,
      variables: undefined,
    } as unknown as ReturnType<typeof useRegenerateBlock>);
    vi.mocked(useMonthlyReport).mockReturnValue({
      isLoading: false,
      isError: false,
      data: makeReport(),
    } as unknown as ReturnType<typeof useMonthlyReport>);
    renderPage();

    fireEvent.click(screen.getByTestId("regenerate-btn-desarrollo"));
    expect(mutateMock).toHaveBeenCalledWith("desarrollo", expect.anything());
  });

  it("muestra el banner IA en bloques con ai_draft", () => {
    vi.mocked(useMonthlyReport).mockReturnValue({
      isLoading: false,
      isError: false,
      data: makeReport(),
    } as unknown as ReturnType<typeof useMonthlyReport>);
    renderPage();
    expect(screen.getByTestId("ai-draft-banner-objetivo")).toBeInTheDocument();
  });

  it("el menú de descarga ofrece 'Descargar PDF' y 'Descargar DOCX'", async () => {
    const user = userEvent.setup();
    vi.mocked(useMonthlyReport).mockReturnValue({
      isLoading: false,
      isError: false,
      data: makeReport(),
    } as unknown as ReturnType<typeof useMonthlyReport>);
    renderPage();

    await user.click(screen.getByTestId("download-menu-trigger"));

    expect(await screen.findByTestId("download-pdf-option")).toHaveTextContent(
      "Descargar PDF",
    );
    expect(screen.getByTestId("download-docx-option")).toHaveTextContent(
      "Descargar DOCX",
    );
  });

  it("la opción 'Descargar PDF' dispara useDownloadMonthlyReportPdf con el período correcto", async () => {
    const user = userEvent.setup();
    const mutateMock = vi.fn();
    vi.mocked(useDownloadMonthlyReportPdf).mockReturnValue({
      ...mutationStub,
      mutate: mutateMock,
    } as unknown as ReturnType<typeof useDownloadMonthlyReportPdf>);
    vi.mocked(useMonthlyReport).mockReturnValue({
      isLoading: false,
      isError: false,
      data: makeReport(),
    } as unknown as ReturnType<typeof useMonthlyReport>);
    renderPage();

    await user.click(screen.getByTestId("download-menu-trigger"));
    await user.click(await screen.findByTestId("download-pdf-option"));

    expect(mutateMock).toHaveBeenCalledWith(
      { year: 2026, month: 4 },
      expect.anything(),
    );
  });

  it("la opción 'Descargar DOCX' dispara useDownloadMonthlyReportDocx con el período correcto", async () => {
    const user = userEvent.setup();
    const mutateMock = vi.fn();
    vi.mocked(useDownloadMonthlyReportDocx).mockReturnValue({
      ...mutationStub,
      mutate: mutateMock,
    } as unknown as ReturnType<typeof useDownloadMonthlyReportDocx>);
    vi.mocked(useMonthlyReport).mockReturnValue({
      isLoading: false,
      isError: false,
      data: makeReport(),
    } as unknown as ReturnType<typeof useMonthlyReport>);
    renderPage();

    await user.click(screen.getByTestId("download-menu-trigger"));
    await user.click(await screen.findByTestId("download-docx-option"));

    expect(mutateMock).toHaveBeenCalledWith(
      { year: 2026, month: 4 },
      expect.anything(),
    );
    // No debe disparar también la mutación de PDF.
    expect(mutationStub.mutate).not.toHaveBeenCalledWith(
      { year: 2026, month: 4 },
      expect.anything(),
    );
  });

  it("muestra un banner de error si la descarga de PDF falla", async () => {
    const user = userEvent.setup();
    const mutateMock = vi.fn((_vars, opts) => opts?.onError?.(new Error("boom")));
    vi.mocked(useDownloadMonthlyReportPdf).mockReturnValue({
      ...mutationStub,
      mutate: mutateMock,
    } as unknown as ReturnType<typeof useDownloadMonthlyReportPdf>);
    vi.mocked(useMonthlyReport).mockReturnValue({
      isLoading: false,
      isError: false,
      data: makeReport(),
    } as unknown as ReturnType<typeof useMonthlyReport>);
    renderPage();

    await user.click(screen.getByTestId("download-menu-trigger"));
    await user.click(await screen.findByTestId("download-pdf-option"));

    expect(screen.getByTestId("download-error-banner")).toBeInTheDocument();
  });

  it("muestra un banner de error si la descarga de DOCX falla", async () => {
    const user = userEvent.setup();
    const mutateMock = vi.fn((_vars, opts) => opts?.onError?.(new Error("boom")));
    vi.mocked(useDownloadMonthlyReportDocx).mockReturnValue({
      ...mutationStub,
      mutate: mutateMock,
    } as unknown as ReturnType<typeof useDownloadMonthlyReportDocx>);
    vi.mocked(useMonthlyReport).mockReturnValue({
      isLoading: false,
      isError: false,
      data: makeReport(),
    } as unknown as ReturnType<typeof useMonthlyReport>);
    renderPage();

    await user.click(screen.getByTestId("download-menu-trigger"));
    await user.click(await screen.findByTestId("download-docx-option"));

    expect(screen.getByTestId("download-error-banner")).toBeInTheDocument();
  });

  it("muestra el componente de métricas cuando existen métricas", () => {
    vi.mocked(useMonthlyReport).mockReturnValue({
      isLoading: false,
      isError: false,
      data: makeReport(),
    } as unknown as ReturnType<typeof useMonthlyReport>);
    renderPage();
    expect(screen.getByTestId("metrics-table")).toBeInTheDocument();
  });

  it("muestra 'Reporte no encontrado' cuando falla la query", () => {
    vi.mocked(useMonthlyReport).mockReturnValue({
      isLoading: false,
      isError: true,
      data: undefined,
    } as unknown as ReturnType<typeof useMonthlyReport>);
    renderPage();
    expect(screen.getByText(/Reporte no encontrado/i)).toBeInTheDocument();
  });

  it("muestra skeleton durante la carga", () => {
    vi.mocked(useMonthlyReport).mockReturnValue({
      isLoading: true,
      isError: false,
      data: undefined,
    } as unknown as ReturnType<typeof useMonthlyReport>);
    const { container } = renderPage();
    expect(container.querySelector(".animate-pulse")).toBeInTheDocument();
  });

  it("los bloques están deshabilitados cuando el informe está aprobado", () => {
    vi.mocked(useMonthlyReport).mockReturnValue({
      isLoading: false,
      isError: false,
      data: makeReport({ status: "approved" }),
    } as unknown as ReturnType<typeof useMonthlyReport>);
    renderPage();
    const textarea = screen.getByTestId("block-textarea-objetivo");
    expect(textarea).toBeDisabled();
  });

  it("muestra la tabla de resultados de competencia", () => {
    vi.mocked(useMonthlyReport).mockReturnValue({
      isLoading: false,
      isError: false,
      data: makeReport({
        competition_results: [
          {
            athlete_name: "Juan Pérez",
            category: "Sub-13",
            position: 2,
            points: 15,
            event_name: "Válida IV",
            event_date: "2026-05-17",
          },
        ],
      }),
    } as unknown as ReturnType<typeof useMonthlyReport>);
    renderPage();
    expect(screen.getByTestId("competition-results-table")).toBeInTheDocument();
    expect(screen.getByText("Juan Pérez")).toBeInTheDocument();
  });

  it("muestra 'Sin resultados' cuando competition_results está vacío", () => {
    vi.mocked(useMonthlyReport).mockReturnValue({
      isLoading: false,
      isError: false,
      data: makeReport({ competition_results: [] }),
    } as unknown as ReturnType<typeof useMonthlyReport>);
    renderPage();
    expect(screen.getByTestId("competition-results-empty")).toBeInTheDocument();
  });

  it("agrupa resultados por evento (jornada) y muestra 'Otorga puntos' para una copa", () => {
    vi.mocked(useMonthlyReport).mockReturnValue({
      isLoading: false,
      isError: false,
      data: makeReport({
        competition_results: [
          {
            athlete_name: "Juan Pérez",
            category: "Sub-13",
            position: 2,
            points: 15,
            event_name: "Válida IV — Cali",
            event_date: "2026-05-17",
            event_id: 4,
            series_kind: "cup",
            awards_points: true,
          },
          {
            athlete_name: "Ana Gómez",
            category: "Sub-15",
            position: 1,
            points: 20,
            event_name: "Válida IV — Cali",
            event_date: "2026-05-17",
            event_id: 4,
            series_kind: "cup",
            awards_points: true,
          },
        ],
      }),
    } as unknown as ReturnType<typeof useMonthlyReport>);
    renderPage();
    expect(screen.getByText("Válida IV — Cali")).toBeInTheDocument();
    expect(screen.getByTestId("event-points-note-4")).toHaveTextContent("Otorga puntos");
    expect(screen.getByText("Juan Pérez")).toBeInTheDocument();
    expect(screen.getByText("Ana Gómez")).toBeInTheDocument();
  });

  it("muestra 'No otorga puntos' para un evento de campeonato", () => {
    vi.mocked(useMonthlyReport).mockReturnValue({
      isLoading: false,
      isError: false,
      data: makeReport({
        competition_results: [
          {
            athlete_name: "Juan Pérez",
            category: "Sub-13",
            position: 1,
            points: null,
            event_name: "Campeonato Departamental",
            event_date: "2026-06-12",
            event_id: 9,
            series_kind: "championship",
            awards_points: false,
          },
        ],
      }),
    } as unknown as ReturnType<typeof useMonthlyReport>);
    renderPage();
    expect(screen.getByTestId("event-points-note-9")).toHaveTextContent("No otorga puntos");
  });

  it("agrupa en un solo bloque sin nota de puntos cuando el informe es antiguo (sin event_id)", () => {
    vi.mocked(useMonthlyReport).mockReturnValue({
      isLoading: false,
      isError: false,
      data: makeReport({
        competition_results: [
          {
            athlete_name: "Juan Pérez",
            category: "Sub-13",
            position: 2,
            points: 15,
            event_name: "Válida IV",
            event_date: "2026-05-17",
          },
        ],
      }),
    } as unknown as ReturnType<typeof useMonthlyReport>);
    renderPage();
    expect(screen.getByText("Válida IV")).toBeInTheDocument();
    expect(screen.queryByText("Otorga puntos")).not.toBeInTheDocument();
    expect(screen.queryByText("No otorga puntos")).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Tests — fallback sin club / sin acceso
//
// El Informe Técnico Mensual es interno del club: la ruta está protegida con
// allowedRoles [coach, admin] y los padres son redirigidos por el guard de ruta
// (ProtectedRoute) antes de montar esta página. El único caso defensivo que
// llega al fallback es coach/admin sin club asignado: no debe caer en una vista
// de reporte, sino mostrar un estado neutro "Informe no disponible".
// ---------------------------------------------------------------------------

describe("ReportDetailPage — fallback sin club asignado", () => {
  beforeEach(() => {
    const noClubState = {
      accessToken: "tok",
      user: { role: "coach", first_name: "Entrena", last_name: "Dor", club_ids: [] },
    };
    vi.mocked(useAuthStore).mockImplementation(
      ((sel: (s: typeof noClubState) => unknown) => sel(noClubState)) as unknown as typeof useAuthStore,
    );
  });

  it("muestra 'Informe no disponible' sin caer en una vista de reporte", () => {
    vi.mocked(useMonthlyReport).mockReturnValue({
      isLoading: false,
      isError: false,
      data: makeReport({ narrative_blocks: null }),
    } as unknown as ReturnType<typeof useMonthlyReport>);
    renderPage();

    expect(screen.getByText(/informe no disponible/i)).toBeInTheDocument();
    // No expone nada del informe: ni métricas, ni editores, ni aprobar, ni PDF.
    expect(screen.queryByTestId("metrics-table")).not.toBeInTheDocument();
    expect(screen.queryByTestId("block-editor-objetivo")).not.toBeInTheDocument();
    expect(screen.queryByTestId("approve-btn")).not.toBeInTheDocument();
    expect(screen.queryByTestId("download-menu-trigger")).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Tests — campos aditivos (feature 022): deben parsear/renderizar sin
// lanzar excepción aunque el snapshot persistido sea antiguo (backward
// compat) o incluya los nuevos campos opcionales.
// ---------------------------------------------------------------------------

describe("ReportDetailPage — campos aditivos (feature 022)", () => {
  it("los schemas aditivos parsean payloads que incluyen los nuevos campos sin lanzar", () => {
    expect(() =>
      sessionDetailItemSchema.parse({
        session_date: "2026-06-05",
        start_time: "08:00:00",
        technical_focus: "Frenada",
        location: "Pista XCO",
        status: "executed",
        present_count: 6,
        attendee_total: 7,
      }),
    ).not.toThrow();

    expect(() =>
      athleteAttendanceStatsAdditiveSchema.parse({
        avg_rubric_effort: 4.1,
        avg_rubric_attitude: null,
        avg_rubric_technique: undefined,
      }),
    ).not.toThrow();

    expect(() =>
      competitionResultAdditiveSchema.parse({
        event_id: 12,
        series_kind: "cup",
        awards_points: true,
      }),
    ).not.toThrow();

    // Snapshots antiguos: sin ninguno de los campos aditivos → sigue siendo válido.
    expect(() => athleteAttendanceStatsAdditiveSchema.parse({})).not.toThrow();
    expect(() => competitionResultAdditiveSchema.parse({})).not.toThrow();
  });

  it("renderiza sin lanzar cuando el reporte incluye los campos aditivos nuevos", () => {
    vi.mocked(useMonthlyReport).mockReturnValue({
      isLoading: false,
      isError: false,
      data: makeReport({
        metrics_snapshot: {
          total_sessions_planned: 8,
          total_sessions_executed: 7,
          total_sessions_cancelled: 1,
          technical_focus_list: ["Frenada"],
          avg_rpe: 6.5,
          avg_rubric_effort: 4.2,
          avg_rubric_attitude: 4.8,
          avg_rubric_technique: 3.9,
          total_minutes_planned: 720,
          total_minutes_executed: 630,
          avg_hours_per_week: 2.4,
          attendance_status_totals: { presente: 30, ausente: 5 },
          session_detail: [
            {
              session_date: "2026-04-05",
              start_time: "08:00:00",
              technical_focus: "Frenada",
              location: "Pista XCO",
              status: "executed",
              present_count: 6,
              attendee_total: 7,
            },
          ],
        },
        competition_results: [
          {
            athlete_name: "Juan Pérez",
            category: "Sub-13",
            position: 2,
            points: 15,
            event_name: "Válida IV",
            event_date: "2026-05-17",
            event_id: 12,
            series_kind: "cup",
            awards_points: true,
          },
        ],
      }),
    } as unknown as ReturnType<typeof useMonthlyReport>);

    expect(() => renderPage()).not.toThrow();
    expect(screen.getByTestId("block-editor-plan_entrenamiento")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Tests — accesibilidad WCAG 2.1 AA (jest-axe)
// ---------------------------------------------------------------------------

describe("ReportDetailPage — accesibilidad", () => {
  it("no tiene violaciones de axe en la vista de coach", async () => {
    vi.mocked(useMonthlyReport).mockReturnValue({
      isLoading: false,
      isError: false,
      data: makeReport(),
    } as unknown as ReturnType<typeof useMonthlyReport>);
    const { container } = renderPage();
    const results = await axe(container, AXE_OPTIONS);
    expect(results).toHaveNoViolations();
  });
});
