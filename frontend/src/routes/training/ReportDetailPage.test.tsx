/**
 * ReportDetailPage.test.tsx
 *
 * Tests para el editor del Informe Técnico Mensual.
 * Coach view (rol coach): acceso completo con bloques editables, aprobar, descargar.
 * Parent view (rol parent): solo lectura, sin bloques narrativos.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

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
  useUpdateReportBlocks,
  useRegenerateBlock,
} from "@/api/trainingSessions";
import { useAuthStore } from "@/store/auth.store";
import { ReportDetailPage } from "./ReportDetailPage";
import type { MonthlyReportFull, NarrativeBlockKey } from "@/types/trainingSession.types";

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
  "objetivo", "desarrollo", "resultados", "conclusiones",
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

  it("renderiza los 7 bloques narrativos editables", () => {
    vi.mocked(useMonthlyReport).mockReturnValue({
      isLoading: false,
      isError: false,
      data: makeReport(),
    } as unknown as ReturnType<typeof useMonthlyReport>);
    renderPage();
    const blockKeys: NarrativeBlockKey[] = [
      "objetivo", "desarrollo", "resultados", "conclusiones",
      "apoyos_materiales", "analisis_grupo", "competencia",
    ];
    for (const key of blockKeys) {
      expect(screen.getByTestId(`block-editor-${key}`)).toBeInTheDocument();
    }
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

  it("el botón 'Descargar PDF' dispara la mutación con el período correcto", () => {
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
    fireEvent.click(screen.getByTestId("download-pdf-button"));
    expect(mutateMock).toHaveBeenCalledWith(
      { year: 2026, month: 4 },
      expect.anything(),
    );
  });

  it("muestra un banner de error si la descarga falla", () => {
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
    fireEvent.click(screen.getByTestId("download-pdf-button"));
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
});

// ---------------------------------------------------------------------------
// Tests — parent view (rol parent, narrative_blocks=null)
// ---------------------------------------------------------------------------

describe("ReportDetailPage — parent (solo lectura)", () => {
  beforeEach(() => {
    const parentState = {
      accessToken: "tok",
      user: { role: "parent", first_name: "Mamá", last_name: "García", club_ids: [1] },
    };
    vi.mocked(useAuthStore).mockImplementation(
      ((sel: (s: typeof parentState) => unknown) => sel(parentState)) as unknown as typeof useAuthStore,
    );
  });

  it("NO renderiza bloques narrativos para parent", () => {
    vi.mocked(useMonthlyReport).mockReturnValue({
      isLoading: false,
      isError: false,
      data: makeReport({ narrative_blocks: null }),
    } as unknown as ReturnType<typeof useMonthlyReport>);
    renderPage();
    // No debe haber ningún editor de bloque
    expect(screen.queryByTestId("block-editor-objetivo")).not.toBeInTheDocument();
    expect(screen.queryByTestId("approve-btn")).not.toBeInTheDocument();
  });

  it("muestra métricas para parent", () => {
    vi.mocked(useMonthlyReport).mockReturnValue({
      isLoading: false,
      isError: false,
      data: makeReport({ narrative_blocks: null }),
    } as unknown as ReturnType<typeof useMonthlyReport>);
    renderPage();
    expect(screen.getByTestId("metrics-table")).toBeInTheDocument();
  });

  it("NO muestra botón Descargar PDF para parent (documento interno del club)", () => {
    vi.mocked(useMonthlyReport).mockReturnValue({
      isLoading: false,
      isError: false,
      data: makeReport({ narrative_blocks: null }),
    } as unknown as ReturnType<typeof useMonthlyReport>);
    renderPage();
    expect(screen.queryByTestId("download-pdf-button")).not.toBeInTheDocument();
    expect(
      screen.getByText(/solo para el equipo técnico del club/i),
    ).toBeInTheDocument();
  });
});
