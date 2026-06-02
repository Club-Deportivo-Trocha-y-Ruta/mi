import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
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
  useMonthlyReports: vi.fn(),
  useGenerateMonthlyReport: vi.fn(),
  useDownloadMonthlyReportPdf: vi.fn(),
}));

vi.mock("@/store/auth.store", () => ({
  useAuthStore: vi.fn((sel: (s: unknown) => unknown) =>
    sel({
      accessToken: "tok",
      user: { role: "coach", first_name: "Juan", last_name: "T", club_ids: [1] },
    }),
  ),
}));

import {
  useMonthlyReports,
  useGenerateMonthlyReport,
  useDownloadMonthlyReportPdf,
} from "@/api/trainingSessions";
import { ReportsListPage } from "./ReportsListPage";
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
    ai_summary: "Buen mes de entrenamiento.",
    metrics_snapshot: null,
    coach_observations: null,
    generated_by_user_id: 10,
    generated_at: "2026-05-01T10:00:00Z",
    ...overrides,
  };
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <ReportsListPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.mocked(useGenerateMonthlyReport).mockReturnValue(
    mutationStub as unknown as ReturnType<typeof useGenerateMonthlyReport>,
  );
  vi.mocked(useDownloadMonthlyReportPdf).mockReturnValue(
    mutationStub as unknown as ReturnType<typeof useDownloadMonthlyReportPdf>,
  );
});

describe("ReportsListPage", () => {
  it("muestra estado vacío cuando no hay reportes", () => {
    vi.mocked(useMonthlyReports).mockReturnValue({
      isLoading: false,
      isError: false,
      data: [],
    } as unknown as ReturnType<typeof useMonthlyReports>);
    renderPage();
    expect(screen.getByTestId("empty-state")).toBeInTheDocument();
    expect(
      screen.getByText(/Aún no hay reportes mensuales generados/i),
    ).toBeInTheDocument();
  });

  it("abre el modal al presionar 'Generar reporte'", async () => {
    vi.mocked(useMonthlyReports).mockReturnValue({
      isLoading: false,
      isError: false,
      data: [],
    } as unknown as ReturnType<typeof useMonthlyReports>);
    renderPage();
    fireEvent.click(screen.getByTestId("open-generate-modal"));
    await waitFor(() => {
      expect(screen.getByTestId("generate-report-form")).toBeInTheDocument();
    });
  });

  it("muestra la tabla de reportes cuando hay datos", () => {
    vi.mocked(useMonthlyReports).mockReturnValue({
      isLoading: false,
      isError: false,
      data: [makeReport()],
    } as unknown as ReturnType<typeof useMonthlyReports>);
    renderPage();
    const items = screen.getAllByText(/Abril 2026/i);
    expect(items.length).toBeGreaterThan(0);
  });

  it("el botón 'Descargar PDF' dispara la mutación de descarga", () => {
    const mutateMock = vi.fn();
    vi.mocked(useDownloadMonthlyReportPdf).mockReturnValue({
      ...mutationStub,
      mutate: mutateMock,
    } as unknown as ReturnType<typeof useDownloadMonthlyReportPdf>);
    vi.mocked(useMonthlyReports).mockReturnValue({
      isLoading: false,
      isError: false,
      data: [makeReport()],
    } as unknown as ReturnType<typeof useMonthlyReports>);
    renderPage();
    fireEvent.click(screen.getAllByText("Descargar PDF")[0]);
    expect(mutateMock).toHaveBeenCalledWith(
      { year: 2026, month: 4 },
      expect.anything(),
    );
  });

  it("muestra skeleton durante la carga", () => {
    vi.mocked(useMonthlyReports).mockReturnValue({
      isLoading: true,
      isError: false,
      data: undefined,
    } as unknown as ReturnType<typeof useMonthlyReports>);
    const { container } = renderPage();
    expect(container.querySelector(".animate-pulse")).toBeInTheDocument();
  });

  it("muestra error cuando falla la carga", () => {
    vi.mocked(useMonthlyReports).mockReturnValue({
      isLoading: false,
      isError: true,
      data: undefined,
    } as unknown as ReturnType<typeof useMonthlyReports>);
    renderPage();
    expect(screen.getByText(/No se pudo cargar la lista de reportes/i)).toBeInTheDocument();
  });

  it("conflict 409 muestra mensaje de regeneración en el modal", async () => {
    const axiosError = {
      isAxiosError: true,
      response: { status: 409, data: { detail: "Ya existe un reporte" } },
    };
    const mutateMock = vi.fn((_payload, opts) => opts?.onError?.(axiosError));
    vi.mocked(useGenerateMonthlyReport).mockReturnValue({
      ...mutationStub,
      mutate: mutateMock,
    } as unknown as ReturnType<typeof useGenerateMonthlyReport>);
    vi.mocked(useMonthlyReports).mockReturnValue({
      isLoading: false,
      isError: false,
      data: [],
    } as unknown as ReturnType<typeof useMonthlyReports>);
    renderPage();
    fireEvent.click(screen.getByTestId("open-generate-modal"));
    await waitFor(() => screen.getByTestId("generate-report-form"));
    fireEvent.submit(screen.getByTestId("generate-report-form"));
    await waitFor(() => {
      expect(screen.getByText(/Ya existe un reporte para este período/i)).toBeInTheDocument();
    });
  });
});
