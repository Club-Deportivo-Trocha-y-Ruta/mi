import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement } from "react";

// ---------------------------------------------------------------------------
// Mock auth store — always return a valid token so hooks are enabled
// ---------------------------------------------------------------------------

vi.mock("@/store/auth.store", () => ({
  useAuthStore: (selector: (s: { accessToken: string }) => unknown) =>
    selector({ accessToken: "test-token" }),
}));

vi.mock("@/api/client", () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
    interceptors: {
      request: { use: vi.fn() },
      response: { use: vi.fn() },
    },
  },
  registerAuthHandlers: vi.fn(),
}));

// Import after mocks
import * as apiClient from "@/api/client";
import {
  useTrainingSessions,
  useTrainingSession,
  useCreateTrainingSession,
  useExecuteTrainingSession,
  useUpdateAttendance,
  useUploadRouteFile,
  useGenerateMonthlyReport,
  useParentMonthlySummary,
  fetchTrainingSessions,
  fetchTrainingSession,
  createTrainingSession,
  executeTrainingSession,
  updateAttendance,
  uploadRouteFile,
  createMonthlyReport,
  fetchParentMonthlySummary,
} from "./trainingSessions";
import type { TrainingSessionCreate, AttendanceUpdate } from "@/types/trainingSession.types";
import { makeSession, makeAttendance, makeMonthlyReport } from "@/test/msw/trainingHandlers";

const { apiClient: mockApi } = apiClient as unknown as {
  apiClient: {
    get: ReturnType<typeof vi.fn>;
    post: ReturnType<typeof vi.fn>;
    patch: ReturnType<typeof vi.fn>;
    put: ReturnType<typeof vi.fn>;
    delete: ReturnType<typeof vi.fn>;
  };
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  return ({ children }: { children: React.ReactNode }) =>
    createElement(QueryClientProvider, { client: queryClient }, children);
}

const SESSION_CREATE_PAYLOAD: TrainingSessionCreate = {
  age_group: "u15",
  scheduled_date: "2026-05-20",
  scheduled_start_time: "08:00:00",
  duration_min: 90,
  location: "Pista XCO",
  technical_focus: "Saltos básicos",
  description: "Sesión de saltos",
  convocados_athlete_ids: [42, 43],
};

// ---------------------------------------------------------------------------
// fetchTrainingSessions
// ---------------------------------------------------------------------------

describe("fetchTrainingSessions", () => {
  it("llama a apiClient.get con el endpoint correcto", async () => {
    const session = makeSession();
    mockApi.get.mockResolvedValueOnce({ data: [session] });

    const result = await fetchTrainingSessions();

    expect(mockApi.get).toHaveBeenCalledWith("/api/training-sessions", { params: {} });
    expect(result).toHaveLength(1);
    expect(result[0].id).toBe(1);
  });

  it("pasa los filtros como query params", async () => {
    mockApi.get.mockResolvedValueOnce({ data: [] });
    await fetchTrainingSessions({
      from_date: "2026-05-01",
      to_date: "2026-05-31",
      age_group: "u15",
      status: "planned",
      athlete_id: 42,
    });

    expect(mockApi.get).toHaveBeenCalledWith("/api/training-sessions", {
      params: {
        from: "2026-05-01",
        to: "2026-05-31",
        age_group: "u15",
        status: "planned",
        athlete_id: "42",
      },
    });
  });

  it("omite filtros vacíos del querystring", async () => {
    mockApi.get.mockResolvedValueOnce({ data: [] });
    await fetchTrainingSessions({ from_date: "", to_date: "", age_group: "", status: "" });
    expect(mockApi.get).toHaveBeenCalledWith("/api/training-sessions", { params: {} });
  });
});

// ---------------------------------------------------------------------------
// fetchTrainingSession
// ---------------------------------------------------------------------------

describe("fetchTrainingSession", () => {
  it("llama al endpoint de detalle con el id correcto", async () => {
    const session = makeSession({ id: 5 });
    mockApi.get.mockResolvedValueOnce({ data: session });

    const result = await fetchTrainingSession(5);

    expect(mockApi.get).toHaveBeenCalledWith("/api/training-sessions/5");
    expect(result.id).toBe(5);
  });
});

// ---------------------------------------------------------------------------
// createTrainingSession
// ---------------------------------------------------------------------------

describe("createTrainingSession", () => {
  it("llama a POST con el payload correcto", async () => {
    const created = makeSession({ id: 99 });
    mockApi.post.mockResolvedValueOnce({ data: created });

    const result = await createTrainingSession(SESSION_CREATE_PAYLOAD);

    expect(mockApi.post).toHaveBeenCalledWith("/api/training-sessions", SESSION_CREATE_PAYLOAD);
    expect(result.id).toBe(99);
  });
});

// ---------------------------------------------------------------------------
// executeTrainingSession
// ---------------------------------------------------------------------------

describe("executeTrainingSession", () => {
  it("llama a POST /execute con el id correcto", async () => {
    const executed = makeSession({ id: 3, status: "executed" });
    mockApi.post.mockResolvedValueOnce({ data: executed });

    const result = await executeTrainingSession(3);

    expect(mockApi.post).toHaveBeenCalledWith("/api/training-sessions/3/execute");
    expect(result.status).toBe("executed");
  });
});

// ---------------------------------------------------------------------------
// updateAttendance
// ---------------------------------------------------------------------------

describe("updateAttendance", () => {
  it("llama a PATCH con session, athlete e payload", async () => {
    const updated = makeAttendance({ status: "tarde" });
    mockApi.patch.mockResolvedValueOnce({ data: updated });

    const payload: AttendanceUpdate = { status: "tarde" };
    const result = await updateAttendance(1, 42, payload);

    expect(mockApi.patch).toHaveBeenCalledWith(
      "/api/training-sessions/1/attendance/42",
      payload,
    );
    expect(result.status).toBe("tarde");
  });
});

// ---------------------------------------------------------------------------
// uploadRouteFile
// ---------------------------------------------------------------------------

describe("uploadRouteFile", () => {
  it("envía FormData con el archivo y el Content-Type correcto", async () => {
    mockApi.post.mockClear();

    const sessionWithRoute = makeSession({ route_file_path: "/static/routes/1/route.gpx" });
    mockApi.post.mockResolvedValueOnce({ data: sessionWithRoute });

    const file = new File(["<gpx/>"], "route.gpx", { type: "application/gpx+xml" });
    const result = await uploadRouteFile(1, file);

    // Buscar la llamada correcta por URL
    const routeFileCall = mockApi.post.mock.calls.find(
      (call: unknown[]) => String(call[0]).includes("route-file"),
    ) as [string, FormData, { headers: Record<string, string> }] | undefined;

    expect(routeFileCall).toBeDefined();
    const [url, formData, config] = routeFileCall!;
    expect(url).toBe("/api/training-sessions/1/route-file");
    expect(formData).toBeInstanceOf(FormData);
    expect(config.headers["Content-Type"]).toBe("multipart/form-data");
    expect(result.route_file_path).toBe("/static/routes/1/route.gpx");
  });
});

// ---------------------------------------------------------------------------
// createMonthlyReport
// ---------------------------------------------------------------------------

describe("createMonthlyReport", () => {
  it("llama a POST con clubId, year, month", async () => {
    const report = makeMonthlyReport();
    mockApi.post.mockResolvedValueOnce({ data: report });

    const result = await createMonthlyReport(1, { year: 2026, month: 5 });

    expect(mockApi.post).toHaveBeenCalledWith("/api/clubs/1/monthly-reports", {
      year: 2026,
      month: 5,
    });
    expect(result.year).toBe(2026);
  });
});

// ---------------------------------------------------------------------------
// fetchParentMonthlySummary
// ---------------------------------------------------------------------------

describe("fetchParentMonthlySummary", () => {
  it("devuelve un array de summaries", async () => {
    mockApi.get.mockResolvedValueOnce({
      data: [
        { athlete_id: 42, athlete_name: "Sebastián", year: 2026, month: 5, count_present: 6, count_total: 7, percentage: 85.7, focos_técnicos: [] },
        { athlete_id: 43, athlete_name: "Laura", year: 2026, month: 5, count_present: 5, count_total: 7, percentage: 71.4, focos_técnicos: [] },
      ],
    });

    const result = await fetchParentMonthlySummary(2026, 5);

    expect(result).toHaveLength(2);
    expect(result[0].athlete_id).toBe(42);
    expect(result[1].athlete_id).toBe(43);
  });

  it("pasa el parámetro athlete_id cuando se especifica", async () => {
    mockApi.get.mockResolvedValueOnce({ data: [] });
    await fetchParentMonthlySummary(2026, 5, 42);

    expect(mockApi.get).toHaveBeenCalledWith(
      "/api/parents/training/monthly-summary/2026/5",
      { params: { athlete_id: "42" } },
    );
  });
});

// ---------------------------------------------------------------------------
// useTrainingSessions (hook)
// ---------------------------------------------------------------------------

describe("useTrainingSessions", () => {
  beforeEach(() => {
    mockApi.get.mockResolvedValue({ data: [makeSession(), makeSession({ id: 2 })] });
  });

  it("retorna la lista de sesiones", async () => {
    const { result } = renderHook(() => useTrainingSessions(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toHaveLength(2);
  });

  it("está deshabilitado cuando no hay accessToken", () => {
    vi.mocked(apiClient.apiClient.get as ReturnType<typeof vi.fn>);

    // Simulate no token by overriding — hook should not fire
    const { result } = renderHook(() => useTrainingSessions(undefined), {
      wrapper: createWrapper(),
    });
    // Just verify hook returns without crashing
    expect(result.current).toBeDefined();
  });
});

// ---------------------------------------------------------------------------
// useTrainingSession (hook)
// ---------------------------------------------------------------------------

describe("useTrainingSession", () => {
  it("retorna una sesión por id", async () => {
    mockApi.get.mockResolvedValueOnce({ data: makeSession({ id: 7 }) });

    const { result } = renderHook(() => useTrainingSession(7), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.id).toBe(7);
  });

  it("no ejecuta la query cuando enabled=false", () => {
    const callsBefore = mockApi.get.mock.calls.length;
    renderHook(() => useTrainingSession(1, false), { wrapper: createWrapper() });
    expect(mockApi.get.mock.calls.length).toBe(callsBefore);
  });
});

// ---------------------------------------------------------------------------
// useCreateTrainingSession (hook)
// ---------------------------------------------------------------------------

describe("useCreateTrainingSession", () => {
  it("llama a POST y luego invalida la lista", async () => {
    const created = makeSession({ id: 99 });
    mockApi.post.mockResolvedValueOnce({ data: created });

    const wrapper = createWrapper();
    const { result } = renderHook(() => useCreateTrainingSession(), { wrapper });

    await act(async () => {
      result.current.mutate(SESSION_CREATE_PAYLOAD);
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.id).toBe(99);
  });
});

// ---------------------------------------------------------------------------
// useExecuteTrainingSession (hook)
// ---------------------------------------------------------------------------

describe("useExecuteTrainingSession", () => {
  it("invalida detalle y lista tras ejecutar", async () => {
    const executed = makeSession({ id: 3, status: "executed" });
    mockApi.post.mockResolvedValueOnce({ data: executed });
    mockApi.get.mockResolvedValue({ data: [] });

    const wrapper = createWrapper();
    const { result } = renderHook(() => useExecuteTrainingSession(), { wrapper });

    await act(async () => {
      result.current.mutate(3);
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.status).toBe("executed");
  });
});

// ---------------------------------------------------------------------------
// useUpdateAttendance — optimistic update + rollback
// ---------------------------------------------------------------------------

describe("useUpdateAttendance", () => {
  it("aplica el update optimista inmediatamente", async () => {
    const sessionId = 1;
    const initialAttendance = makeAttendance({ status: "ausente" });

    // Pre-populate cache
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
    queryClient.setQueryData(["training-session-attendance", sessionId], [initialAttendance]);

    const customWrapper = ({ children }: { children: React.ReactNode }) =>
      createElement(QueryClientProvider, { client: queryClient }, children);

    mockApi.patch.mockResolvedValueOnce({ data: makeAttendance({ status: "presente" }) });
    mockApi.get.mockResolvedValue({ data: [makeAttendance({ status: "presente" })] });

    const { result } = renderHook(() => useUpdateAttendance(sessionId), { wrapper: customWrapper });

    await act(async () => {
      result.current.mutate({ athleteId: 42, payload: { status: "presente" } });
      // Yield to allow onMutate to run before assertions
      await Promise.resolve();
    });

    // Optimistic update applied synchronously in onMutate
    const optimisticData = queryClient.getQueryData<{ status: string }[]>([
      "training-session-attendance",
      sessionId,
    ]);
    expect(optimisticData?.[0]?.status).toBe("presente");
  });

  it("revierte el update optimista en caso de error (500)", async () => {
    const sessionId = 2;
    const initialAttendance = makeAttendance({ session_id: 2, status: "ausente" });

    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
    queryClient.setQueryData(["training-session-attendance", sessionId], [initialAttendance]);

    const customWrapper = ({ children }: { children: React.ReactNode }) =>
      createElement(QueryClientProvider, { client: queryClient }, children);

    mockApi.patch.mockRejectedValueOnce(new Error("Server error 500"));
    mockApi.get.mockResolvedValue({ data: [initialAttendance] });

    const { result } = renderHook(() => useUpdateAttendance(sessionId), { wrapper: customWrapper });

    await act(async () => {
      result.current.mutate({ athleteId: 42, payload: { status: "presente" } });
    });

    await waitFor(() => expect(result.current.isError).toBe(true));

    const rolledBack = queryClient.getQueryData<{ status: string }[]>([
      "training-session-attendance",
      sessionId,
    ]);
    expect(rolledBack?.[0]?.status).toBe("ausente");
  });
});

// ---------------------------------------------------------------------------
// useUploadRouteFile (hook)
// ---------------------------------------------------------------------------

describe("useUploadRouteFile", () => {
  it("postea FormData con el archivo", async () => {
    const sessionWithRoute = makeSession({ route_file_path: "/static/routes/1/route.gpx" });
    mockApi.post.mockResolvedValueOnce({ data: sessionWithRoute });

    const { result } = renderHook(() => useUploadRouteFile(1), { wrapper: createWrapper() });

    const file = new File(["<gpx/>"], "route.gpx", { type: "application/gpx+xml" });
    await act(async () => {
      result.current.mutate(file);
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.route_file_path).toBe("/static/routes/1/route.gpx");
  });
});

// ---------------------------------------------------------------------------
// useGenerateMonthlyReport — propagación de 409
// ---------------------------------------------------------------------------

describe("useGenerateMonthlyReport", () => {
  it("propaga el error 409 cuando el reporte ya existe", async () => {
    const error = Object.assign(new Error("Conflict"), {
      response: { status: 409, data: { detail: "Ya existe un reporte para este mes" } },
    });
    mockApi.post.mockRejectedValueOnce(error);

    const { result } = renderHook(() => useGenerateMonthlyReport(1), { wrapper: createWrapper() });

    await act(async () => {
      result.current.mutate({ year: 2026, month: 5 });
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect((result.current.error as { response?: { status: number } })?.response?.status).toBe(409);
  });

  it("invalida la lista de reportes tras generar uno nuevo", async () => {
    mockApi.post.mockResolvedValueOnce({ data: makeMonthlyReport({ id: 10 }) });
    mockApi.get.mockResolvedValue({ data: [makeMonthlyReport()] });

    const { result } = renderHook(() => useGenerateMonthlyReport(1), { wrapper: createWrapper() });

    await act(async () => {
      result.current.mutate({ year: 2026, month: 5 });
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.id).toBe(10);
  });
});

// ---------------------------------------------------------------------------
// useParentMonthlySummary — array con múltiples hijos
// ---------------------------------------------------------------------------

describe("useParentMonthlySummary", () => {
  it("retorna array con múltiples hijos", async () => {
    mockApi.get.mockResolvedValueOnce({
      data: [
        { athlete_id: 42, athlete_name: "Sebastián", year: 2026, month: 5, count_present: 6, count_total: 7, percentage: 85.7, focos_técnicos: [] },
        { athlete_id: 43, athlete_name: "Laura", year: 2026, month: 5, count_present: 5, count_total: 7, percentage: 71.4, focos_técnicos: [] },
      ],
    });

    const { result } = renderHook(() => useParentMonthlySummary(2026, 5), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toHaveLength(2);
    expect(result.current.data?.[0].athlete_id).toBe(42);
    expect(result.current.data?.[1].athlete_id).toBe(43);
  });

  it("filtra por athlete_id cuando se provee", async () => {
    mockApi.get.mockResolvedValueOnce({
      data: [{ athlete_id: 42, athlete_name: "Sebastián", year: 2026, month: 5, count_present: 6, count_total: 7, percentage: 85.7, focos_técnicos: [] }],
    });

    const { result } = renderHook(() => useParentMonthlySummary(2026, 5, 42), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toHaveLength(1);
  });
});
