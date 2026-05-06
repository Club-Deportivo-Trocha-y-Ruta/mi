import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("@/api/client", () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
  },
  registerAuthHandlers: vi.fn(),
}));

vi.mock("@/api/trainingSessions", () => ({
  useMonthlyReport: vi.fn(),
  useSendMonthlyReport: vi.fn(),
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
  useSendMonthlyReport,
} from "@/api/trainingSessions";
import { ReportDetailPage } from "./ReportDetailPage";
import type { MonthlyReportFull } from "@/types/trainingSession.types";

const mutationStub = {
  mutate: vi.fn(),
  isPending: false,
  isError: false,
  isSuccess: false,
  data: undefined,
  error: null,
  reset: vi.fn(),
  mutateAsync: vi.fn(),
};

function makeReport(overrides?: Partial<MonthlyReportFull>): MonthlyReportFull {
  return {
    id: 1,
    club_id: 1,
    year: 2026,
    month: 4,
    ai_summary: "Excelente mes con buena asistencia.",
    metrics_snapshot: {
      total_sessions_planned: 8,
      total_sessions_executed: 7,
      total_sessions_cancelled: 1,
      attendance_stats: [],
      focos_técnicos: ["Frenada", "Curvas"],
      avg_rpe: 6.5,
      avg_rubric_effort: 4.2,
      avg_rubric_attitude: 4.8,
      avg_rubric_technique: 3.9,
    },
    coach_observations: "Buena actitud del grupo.",
    generated_by_user_id: 10,
    generated_at: "2026-05-01T10:00:00Z",
    sent_at: null,
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

beforeEach(() => {
  vi.mocked(useSendMonthlyReport).mockReturnValue(
    mutationStub as unknown as ReturnType<typeof useSendMonthlyReport>,
  );
});

describe("ReportDetailPage", () => {
  it("muestra el banner de IA visible", () => {
    vi.mocked(useMonthlyReport).mockReturnValue({
      isLoading: false,
      isError: false,
      data: makeReport(),
    } as unknown as ReturnType<typeof useMonthlyReport>);
    renderPage();
    expect(screen.getByTestId("ai-banner")).toBeInTheDocument();
    expect(
      screen.getByText(/Resumen generado por IA — revisalo antes de enviar/i),
    ).toBeInTheDocument();
  });

  it("el botón 'Re-enviar al club' abre el ConfirmModal", async () => {
    vi.mocked(useMonthlyReport).mockReturnValue({
      isLoading: false,
      isError: false,
      data: makeReport(),
    } as unknown as ReturnType<typeof useMonthlyReport>);
    renderPage();
    fireEvent.click(screen.getByTestId("resend-button"));
    await waitFor(() => {
      expect(screen.getByText(/Re-enviar reporte al club/i)).toBeInTheDocument();
    });
  });

  it("muestra 'Enviado el' en el footer después de éxito", async () => {
    const mutateMock = vi.fn((_vars, opts) =>
      opts?.onSuccess?.({ enviados: 1, total_admins: 1, sent_at: null }),
    );
    vi.mocked(useSendMonthlyReport).mockReturnValue({
      ...mutationStub,
      mutate: mutateMock,
    } as unknown as ReturnType<typeof useSendMonthlyReport>);
    vi.mocked(useMonthlyReport).mockReturnValue({
      isLoading: false,
      isError: false,
      data: makeReport({ sent_at: "2026-05-02T09:00:00Z" }),
    } as unknown as ReturnType<typeof useMonthlyReport>);
    renderPage();
    expect(screen.getByTestId("sent-at-text")).toBeInTheDocument();
  });

  it("el resumen de IA se renderiza como texto plano, no como input o textarea", () => {
    vi.mocked(useMonthlyReport).mockReturnValue({
      isLoading: false,
      isError: false,
      data: makeReport(),
    } as unknown as ReturnType<typeof useMonthlyReport>);
    renderPage();
    const summaryEl = screen.getByTestId("ai-summary-text");
    expect(summaryEl.tagName).not.toBe("INPUT");
    expect(summaryEl.tagName).not.toBe("TEXTAREA");
    expect(summaryEl).toHaveTextContent("Excelente mes con buena asistencia.");
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

  it("muestra not found cuando falla la query", () => {
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
});
