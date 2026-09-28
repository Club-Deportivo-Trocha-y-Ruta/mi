import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AxiosError } from "axios";

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

const navigateMock = vi.fn();
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>("react-router-dom");
  return { ...actual, useNavigate: () => navigateMock };
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

/** Rechazo del backend con respuesta HTTP y `detail` en español (forma FastAPI). */
function backendError(status: number, detail: string) {
  return new AxiosError(
    `Request failed with status code ${status}`,
    AxiosError.ERR_BAD_REQUEST,
    undefined,
    {},
    {
      status,
      statusText: "",
      headers: {},
      config: {} as never,
      data: { detail },
    },
  );
}

/** Petición enviada que nunca recibió respuesta (Render Free despertando). */
function unansweredRequestError() {
  return new AxiosError("Network Error", AxiosError.ERR_NETWORK, undefined, {});
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
    await waitFor(() => {
      expect(navigateMock).toHaveBeenCalledWith("/training/sessions/55");
    });
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

    // Reintento exitoso → redirige directo al detalle de la sesión.
    uploadRouteFileMock.mockResolvedValueOnce({ id: 56 });
    fireEvent.click(screen.getByRole("button", { name: /Reintentar subida/i }));
    await waitFor(() => {
      expect(navigateMock).toHaveBeenCalledWith("/training/sessions/56");
    });
  });

  it("notificar: crea la sesión y redirige directo a su detalle", async () => {
    createMutateAsync.mockResolvedValueOnce({ id: 57 });
    renderCreate();
    await gotoRouteStep();
    next();
    await screen.findByTestId("session-step-review");
    fireEvent.click(screen.getByTestId("notify-parents-checkbox"));
    fireEvent.click(screen.getByTestId("session-wizard-submit"));

    await waitFor(() => {
      expect(navigateMock).toHaveBeenCalledWith("/training/sessions/57");
    });
    expect(screen.queryByTestId("session-wizard-success")).not.toBeInTheDocument();
  });

  it("sin notificar: crea la sesión y redirige directo a su detalle", async () => {
    createMutateAsync.mockResolvedValueOnce({ id: 58 });
    renderCreate();
    await gotoRouteStep();
    next();
    await screen.findByTestId("session-step-review");
    fireEvent.click(screen.getByTestId("session-wizard-submit"));

    await waitFor(() => {
      expect(navigateMock).toHaveBeenCalledWith("/training/sessions/58");
    });
    expect(screen.queryByTestId("session-wizard-success")).not.toBeInTheDocument();
  });

  // El wizard pasa el error por `extractErrorDetail` (`@/lib/apiError`): el
  // `detail` en español del backend gana sobre `err.message`, un fallo sin
  // respuesta (servidor dormido) muestra la copy calmada de cold start, y solo
  // un error sin detalle ni mensaje cae a la copy genérica de creación. Por eso
  // estos tests rechazan con errores de forma axios y no con un `Error` plano
  // (cuyo `message` se mostraría tal cual).
  async function submitFromReview() {
    renderCreate();
    await gotoRouteStep();
    next();
    await screen.findByTestId("session-step-review");
    fireEvent.click(screen.getByTestId("session-wizard-submit"));
  }

  it("si el backend rechaza la creación, muestra su detalle y conserva el formulario para reintentar", async () => {
    createMutateAsync
      .mockRejectedValueOnce(
        backendError(409, "Ya existe una sesión del club en ese horario."),
      )
      .mockResolvedValueOnce({ id: 59 });
    await submitFromReview();

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Ya existe una sesión del club en ese horario.");
    // Sin pantalla de éxito ni redirección: la sesión no se creó.
    expect(screen.queryByTestId("session-wizard-success")).not.toBeInTheDocument();
    expect(navigateMock).not.toHaveBeenCalled();
    // El formulario se conserva: sigue en la revisión y se puede volver a enviar.
    expect(screen.getByTestId("session-step-review")).toBeInTheDocument();
    expect(screen.getByTestId("session-wizard-submit")).toBeEnabled();

    // Reintento con los mismos datos → crea y redirige; el error desaparece.
    fireEvent.click(screen.getByTestId("session-wizard-submit"));
    await waitFor(() => {
      expect(navigateMock).toHaveBeenCalledWith("/training/sessions/59");
    });
    expect(createMutateAsync).toHaveBeenCalledTimes(2);
    expect(createMutateAsync.mock.calls[1][0]).toEqual(createMutateAsync.mock.calls[0][0]);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("si el servidor no responde (arranque en frío), muestra la copy calmada y conserva el formulario", async () => {
    createMutateAsync.mockRejectedValueOnce(unansweredRequestError());
    await submitFromReview();

    expect(await screen.findByRole("alert")).toHaveTextContent(
      /La aplicación está iniciando/i,
    );
    expect(screen.queryByTestId("session-wizard-success")).not.toBeInTheDocument();
    expect(navigateMock).not.toHaveBeenCalled();
    expect(screen.getByTestId("session-step-review")).toBeInTheDocument();
    expect(screen.getByTestId("session-wizard-submit")).toBeEnabled();
  });

  it("si el error no trae detalle ni mensaje, cae a la copy genérica de creación", async () => {
    createMutateAsync.mockRejectedValueOnce(new Error(""));
    await submitFromReview();

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "No se pudo crear la sesión. Revisa tu conexión e intenta de nuevo.",
    );
    expect(screen.queryByTestId("session-wizard-success")).not.toBeInTheDocument();
    expect(navigateMock).not.toHaveBeenCalled();
    expect(screen.getByTestId("session-step-review")).toBeInTheDocument();
    expect(screen.getByTestId("session-wizard-submit")).toBeEnabled();
  });
});
