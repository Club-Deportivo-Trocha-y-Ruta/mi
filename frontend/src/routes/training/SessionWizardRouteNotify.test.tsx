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

const uploadRouteFileMock = vi.fn();
const createMutateAsync = vi.fn();

vi.mock("@/api/trainingSessions", () => ({
  useTrainingSession: vi.fn(() => ({ data: undefined, isLoading: false, isError: false })),
  useSessionAttendance: vi.fn(() => ({ data: [], isLoading: false, isError: false })),
  useCreateTrainingSession: vi.fn(() => ({
    mutateAsync: createMutateAsync,
    isPending: false,
    isError: false,
  })),
  useUpdateTrainingSession: vi.fn(() => ({ mutateAsync: vi.fn(), isPending: false, isError: false })),
  bulkSetConvocatoria: vi.fn(),
  uploadRouteFile: (...args: unknown[]) => uploadRouteFileMock(...args),
  fetchTrainingSession: vi.fn(),
}));

vi.mock("@/components/training/AthletesMultiSelect", () => ({
  AthletesMultiSelect: ({ onChange }: { onChange: (ids: number[]) => void }) => (
    <button type="button" data-testid="select-athlete" onClick={() => onChange([1])}>
      Seleccionar atleta
    </button>
  ),
}));

vi.mock("@/store/auth.store", () => ({
  useAuthStore: vi.fn((sel) =>
    sel({ accessToken: "tok", user: { id: 7, role: "coach", club_ids: [1] }, isAuthenticated: true }),
  ),
}));

vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>("react-router-dom");
  return { ...actual, useNavigate: () => vi.fn() };
});

import { SessionFormPage } from "./SessionFormPage";

function renderCreate() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/training/sessions/new"]}>
        <Routes>
          <Route path="/training/sessions/new" element={<SessionFormPage mode="create" />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function fillStep1() {
  fireEvent.change(screen.getByLabelText(/Fecha/i), { target: { value: "2026-12-01" } });
  fireEvent.change(screen.getByLabelText(/Hora de inicio/i), { target: { value: "08:00" } });
  fireEvent.change(screen.getByLabelText(/Lugar/i), { target: { value: "Pista XCO" } });
  fireEvent.change(screen.getByLabelText(/Foco técnico/i), { target: { value: "Técnica" } });
  fireEvent.change(screen.getByLabelText("Descripción"), {
    target: { value: "Descripción válida de la sesión" },
  });
}

const next = () => fireEvent.click(screen.getByRole("button", { name: /Siguiente/i }));

/** Avanza del paso 1 al 3 (ruta y notas), dejando la sesión lista para revisar. */
async function gotoRouteStep() {
  fillStep1();
  next();
  fireEvent.click(await screen.findByTestId("select-athlete"));
  next();
  await screen.findByTestId("session-step-route-notes");
}

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
});

describe("Wizard — ruta, notas y notificación (US4)", () => {
  it("bloquea avance con URL de Strava inválida (regla compartida)", async () => {
    renderCreate();
    await gotoRouteStep();
    fireEvent.change(screen.getByLabelText(/Link Strava/i), {
      target: { value: "https://example.com/no-strava" },
    });
    next();
    // El mensaje aparece inline y en el resumen (varias coincidencias).
    expect(await screen.findByTestId("session-error-summary")).toBeInTheDocument();
    expect(screen.getAllByText(/URL de Strava no válida/i).length).toBeGreaterThan(0);
    // Sigue en el paso de ruta.
    expect(screen.getByTestId("session-step-route-notes")).toBeInTheDocument();
  });

  it("adjunta archivo de ruta y lo sube tras crear la sesión", async () => {
    createMutateAsync.mockResolvedValueOnce({ id: 55 });
    uploadRouteFileMock.mockResolvedValueOnce({ id: 55 });
    const { container } = renderCreate();
    await gotoRouteStep();

    const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File(["<gpx></gpx>"], "ruta.gpx", { type: "application/gpx+xml" });
    fireEvent.change(fileInput, { target: { files: [file] } });
    expect(await screen.findByTestId("route-file-name")).toHaveTextContent("ruta.gpx");

    next();
    await screen.findByTestId("session-step-review");
    fireEvent.click(screen.getByTestId("session-wizard-submit"));

    await waitFor(() => {
      expect(createMutateAsync).toHaveBeenCalled();
      expect(uploadRouteFileMock).toHaveBeenCalledWith(55, file);
    });
    expect(await screen.findByTestId("session-wizard-success")).toBeInTheDocument();
  });

  it("si la subida del archivo falla, la sesión queda guardada y ofrece reintentar", async () => {
    createMutateAsync.mockResolvedValueOnce({ id: 56 });
    uploadRouteFileMock.mockRejectedValueOnce(new Error("network"));
    const { container } = renderCreate();
    await gotoRouteStep();

    const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File(["<gpx></gpx>"], "track.fit", { type: "application/octet-stream" });
    fireEvent.change(fileInput, { target: { files: [file] } });

    next();
    await screen.findByTestId("session-step-review");
    fireEvent.click(screen.getByTestId("session-wizard-submit"));

    // Pantalla "guardada, archivo pendiente" con reintento.
    expect(await screen.findByTestId("session-wizard-route-failed")).toBeInTheDocument();

    // Reintento exitoso → pantalla de éxito.
    uploadRouteFileMock.mockResolvedValueOnce({ id: 56 });
    fireEvent.click(screen.getByRole("button", { name: /Reintentar subida/i }));
    expect(await screen.findByTestId("session-wizard-success")).toBeInTheDocument();
  });

  it("notificar: el resultado indica que se avisó a las familias", async () => {
    createMutateAsync.mockResolvedValueOnce({ id: 57 });
    renderCreate();
    await gotoRouteStep();
    next();
    await screen.findByTestId("session-step-review");
    fireEvent.click(screen.getByTestId("notify-parents-checkbox"));
    fireEvent.click(screen.getByTestId("session-wizard-submit"));

    const success = await screen.findByTestId("session-wizard-success");
    expect(success).toHaveTextContent(/Se envió la notificación a las familias/i);
  });

  it("sin notificar: el resultado indica que no se enviaron notificaciones", async () => {
    createMutateAsync.mockResolvedValueOnce({ id: 58 });
    renderCreate();
    await gotoRouteStep();
    next();
    await screen.findByTestId("session-step-review");
    fireEvent.click(screen.getByTestId("session-wizard-submit"));

    const success = await screen.findByTestId("session-wizard-success");
    expect(success).toHaveTextContent(/No se enviaron notificaciones/i);
  });

  it("si falla la creación, muestra error y conserva el formulario (sin pantalla de éxito)", async () => {
    createMutateAsync.mockRejectedValueOnce(new Error("boom"));
    renderCreate();
    await gotoRouteStep();
    next();
    await screen.findByTestId("session-step-review");
    fireEvent.click(screen.getByTestId("session-wizard-submit"));

    expect(await screen.findByText(/No se pudo crear la sesión/i)).toBeInTheDocument();
    expect(screen.queryByTestId("session-wizard-success")).not.toBeInTheDocument();
  });
});
