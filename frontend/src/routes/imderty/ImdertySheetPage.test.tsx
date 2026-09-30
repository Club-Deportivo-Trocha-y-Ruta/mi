/**
 * Tests de ImdertySheetPage (feature 047, US1/T021 + US3/T045).
 *
 * Cubre: la descarga llama a la API con el mes y el encabezado elegidos, un
 * error muestra un mensaje en español, un rol parent no puede llegar a la
 * ruta (gate de `ProtectedRoute`, registrado en App.tsx por T012) y cero
 * violaciones axe. Desde T044 la página también monta `ReadinessPanel` y
 * `HeaderOverridesForm`, así que sus llamadas (`getImdertySheetReadiness`,
 * `getClubImdertySettings`) se mockean también.
 *
 * `downloadImdertySheet` se mockea a nivel de `@/api/imderty` en vez de vía
 * MSW: con `responseType: "blob"`, axios usa XHR y el interceptor de MSW
 * para Node falla al construir el `Response` interno a partir de un cuerpo
 * binario en este entorno (jsdom + undici) — mismo motivo por el que
 * `athleteNewsletters.test.ts` mockea `apiClient` directo para su descarga
 * de PDF en vez de usar MSW. Las otras dos llamadas de este archivo no usan
 * blob, pero se mockean igual para no depender de MSW ni de la red real.
 *
 * `TableScrollContainer` (vista desktop de `ReadinessPanel`) usa
 * `ResizeObserver`, ausente en jsdom — se polyfilla acá, igual que en
 * `components/imderty/__smoke__.test.tsx`.
 */
if (!globalThis.ResizeObserver) {
  globalThis.ResizeObserver = class ResizeObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver;
}

import type { ReactNode } from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { axe, toHaveNoViolations } from "jest-axe";

expect.extend(toHaveNoViolations);

import { UserRole } from "@/types/enums";

// `role` es mutable (vi.hoisted) para poder alternarlo entre pruebas sin
// remockear el módulo completo — mismo patrón que DashboardPage.test.tsx.
// String literal en vez de `UserRole.coach`: vi.hoisted corre antes de que
// los imports estáticos se resuelvan.
const authState = vi.hoisted(() => ({
  role: "coach" as string,
}));

type AuthStoreState = {
  accessToken: string;
  refreshToken: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  refreshSession: () => Promise<void>;
  user: { id: number; role: string; club_ids: number[] };
};

// `useAuthStore()` se usa con y sin selector en el árbol de rutas
// (`ProtectedRoute` la llama sin argumentos; `ImdertySheetPage` con uno) —
// el mock soporta ambas formas, igual que la store real de Zustand.
vi.mock("@/store/auth.store", () => ({
  useAuthStore: (selector?: (state: AuthStoreState) => unknown) => {
    const state: AuthStoreState = {
      accessToken: "fake-token",
      refreshToken: null,
      isAuthenticated: true,
      isLoading: false,
      refreshSession: vi.fn(),
      user: { id: 1, role: authState.role, club_ids: [7] },
    };
    return selector ? selector(state) : state;
  },
}));

// AppShell trae de todo (sidebar, quick-create, atajos de teclado…) — no es
// lo que se prueba aquí, así que se sustituye por un passthrough, igual que
// en las pruebas que ejercitan `ProtectedRoute` de verdad.
vi.mock("@/components/layout/AppShell", () => ({
  AppShell: ({ children }: { children: ReactNode }) => <>{children}</>,
}));

vi.mock("@/api/imderty", () => ({
  downloadImdertySheet: vi.fn(),
  getImdertySheetReadiness: vi.fn(),
  getClubImdertySettings: vi.fn(),
}));

import { ProtectedRoute } from "@/routes/ProtectedRoute";
import {
  downloadImdertySheet,
  getClubImdertySettings,
  getImdertySheetReadiness,
} from "@/api/imderty";
import { ImdertySheetPage } from "./ImdertySheetPage";
import type { ClubImdertySettings, ImdertyReadiness, ImdertySheetHeaderValues } from "@/schemas/imderty";

const mockDownloadImdertySheet = vi.mocked(downloadImdertySheet);
const mockGetReadiness = vi.mocked(getImdertySheetReadiness);
const mockGetSettings = vi.mocked(getClubImdertySettings);

/** El club nunca guardó configuración IMDERTY: nulls/lista vacía (contrato §Club IMDERTY settings). */
const BLANK_HEADER: ImdertySheetHeaderValues = {
  contractor_name: null,
  venue: null,
  training_days: null,
  schedule: null,
  programs: [],
};
const NEVER_SAVED_SETTINGS: ClubImdertySettings = {
  contractor_name: null,
  venue: null,
  training_days: null,
  schedule: null,
  programs: [],
};
const NO_GAPS_READINESS: ImdertyReadiness = {
  months: ["2026-06"],
  month_in_progress: false,
  months_without_activity: [],
  athlete_count: 20,
  gaps: [],
};

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0, staleTime: 0 } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/imderty/planilla"]}>
        <Routes>
          <Route
            path="/imderty/planilla"
            element={
              <ProtectedRoute allowedRoles={[UserRole.coach, UserRole.admin]}>
                <ImdertySheetPage />
              </ProtectedRoute>
            }
          />
          <Route path="/dashboard" element={<div>landed-dashboard</div>} />
          <Route path="/my-athletes" element={<div>landed-my-athletes</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("ImdertySheetPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    authState.role = "coach";
    mockDownloadImdertySheet.mockResolvedValue({
      blob: new Blob([new Uint8Array([0x50, 0x4b, 0x03, 0x04])]),
      filename: "FO-GDD-057_asistencia_2026-08_2026-08.xlsx",
    });
    mockGetReadiness.mockResolvedValue(NO_GAPS_READINESS);
    mockGetSettings.mockResolvedValue(NEVER_SAVED_SETTINGS);
    URL.createObjectURL = vi.fn(() => "blob:mock-url");
    URL.revokeObjectURL = vi.fn();
  });

  it("descarga la planilla llamando a la API con el mes y el encabezado elegidos", async () => {
    const user = userEvent.setup();
    renderPage();

    // Espera a que el encabezado precargado (nulls, nunca guardado) llegue
    // antes de descargar, para que el payload sea determinístico: mientras
    // `HeaderOverridesForm` sigue cargando, la página manda `header: null`
    // a propósito (ver su comentario) en vez de un objeto en blanco.
    await screen.findByText("Todo listo");
    await waitFor(() =>
      expect(screen.queryByLabelText("Cargando configuración del encabezado…")).not.toBeInTheDocument(),
    );

    const monthInput = screen.getByLabelText("Mes");
    await user.clear(monthInput);
    await user.type(monthInput, "2026-06");

    await user.click(screen.getByRole("button", { name: /descargar planilla/i }));

    await waitFor(() =>
      expect(mockDownloadImdertySheet).toHaveBeenCalledWith(7, {
        from: "2026-06",
        to: "2026-06",
        header: BLANK_HEADER,
        save_header_as_default: false,
      }),
    );
  });

  it("descargar antes de que cargue la configuración del club manda header null (no en blanco)", async () => {
    // `getClubImdertySettings` nunca resuelve durante esta prueba: simula un
    // coach que hace clic en "Descargar" mientras el encabezado sigue
    // cargando. El payload debe llevar `header: null` (el contrato lo hace
    // caer de vuelta a la configuración guardada), nunca un objeto con
    // todos los campos en blanco que la pisaría.
    mockGetSettings.mockReturnValue(new Promise(() => {}));
    const user = userEvent.setup();
    renderPage();

    await screen.findByText("Todo listo");
    await user.click(screen.getByRole("button", { name: /descargar planilla/i }));

    await waitFor(() =>
      expect(mockDownloadImdertySheet).toHaveBeenCalledWith(7, {
        from: expect.any(String),
        to: expect.any(String),
        header: null,
        save_header_as_default: false,
      }),
    );
  });

  it("muestra un mensaje en español cuando la descarga falla", async () => {
    // Simula lo que axios entrega realmente con `responseType: "blob"`: el
    // cuerpo del error 422 llega como Blob, no como JSON ya parseado.
    const errorBlob = new Blob(
      [JSON.stringify({ detail: "No hay atletas activos en ese mes." })],
      { type: "application/json" },
    );
    mockDownloadImdertySheet.mockReset();
    mockDownloadImdertySheet.mockRejectedValueOnce({
      isAxiosError: true,
      response: { status: 422, data: errorBlob },
    });
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole("button", { name: /descargar planilla/i }));

    expect(
      await screen.findByText("No hay atletas activos en ese mes."),
    ).toBeInTheDocument();
  });

  it("un rol parent no puede llegar a la ruta de la planilla", async () => {
    authState.role = "parent";
    renderPage();

    await waitFor(() => expect(screen.getByText("landed-my-athletes")).toBeInTheDocument());
    expect(screen.queryByText("Planilla IMDERTY")).not.toBeInTheDocument();
  });

  it("sin violaciones axe", async () => {
    const { container } = renderPage();

    await waitFor(() => expect(screen.getByText("Planilla IMDERTY")).toBeInTheDocument());
    // Espera a que el panel de disponibilidad y el encabezado terminen de
    // cargar (no solo skeletons) para que el escaneo axe sea determinístico.
    await screen.findByText("Todo listo");
    await waitFor(() => expect(mockGetSettings).toHaveBeenCalled());

    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  // US4/T050 — toggle «Un mes / Varios meses».
  describe("rango de varios meses (US4)", () => {
    it("descarga un rango de meses llamando a la API con from/to distintos", async () => {
      const user = userEvent.setup();
      renderPage();

      await screen.findByText("Todo listo");
      await waitFor(() =>
        expect(screen.queryByLabelText("Cargando configuración del encabezado…")).not.toBeInTheDocument(),
      );

      await user.click(screen.getByRole("radio", { name: "Varios meses" }));

      const fromInput = screen.getByLabelText("Desde");
      const toInput = screen.getByLabelText("Hasta");
      await user.clear(fromInput);
      await user.type(fromInput, "2026-11");
      await user.clear(toInput);
      await user.type(toInput, "2027-02");

      await user.click(screen.getByRole("button", { name: /descargar planilla/i }));

      await waitFor(() =>
        expect(mockDownloadImdertySheet).toHaveBeenCalledWith(7, {
          from: "2026-11",
          to: "2027-02",
          header: BLANK_HEADER,
          save_header_as_default: false,
        }),
      );
    });

    it("deshabilita la descarga y muestra un mensaje en línea cuando el rango supera 12 meses", async () => {
      const user = userEvent.setup();
      renderPage();

      await screen.findByText("Todo listo");
      await user.click(screen.getByRole("radio", { name: "Varios meses" }));

      const fromInput = screen.getByLabelText("Desde");
      const toInput = screen.getByLabelText("Hasta");
      await user.clear(fromInput);
      await user.type(fromInput, "2025-01");
      await user.clear(toInput);
      await user.type(toInput, "2026-06");

      expect(
        await screen.findByText(/el rango no puede superar los 12 meses/i),
      ).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /descargar planilla/i })).toBeDisabled();
      expect(mockDownloadImdertySheet).not.toHaveBeenCalled();
    });

    it("deshabilita la descarga cuando «Hasta» es anterior a «Desde»", async () => {
      const user = userEvent.setup();
      renderPage();

      await screen.findByText("Todo listo");
      await user.click(screen.getByRole("radio", { name: "Varios meses" }));

      const fromInput = screen.getByLabelText("Desde");
      const toInput = screen.getByLabelText("Hasta");
      await user.clear(fromInput);
      await user.type(fromInput, "2026-06");
      await user.clear(toInput);
      await user.type(toInput, "2026-01");

      expect(
        await screen.findByText(/no puede ser anterior al mes «Desde»/i),
      ).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /descargar planilla/i })).toBeDisabled();
      expect(mockDownloadImdertySheet).not.toHaveBeenCalled();
    });

    it("volver a «Un mes» descarga de nuevo con from === to", async () => {
      const user = userEvent.setup();
      renderPage();

      await screen.findByText("Todo listo");
      await user.click(screen.getByRole("radio", { name: "Varios meses" }));
      await user.click(screen.getByRole("radio", { name: "Un mes" }));

      const monthInput = screen.getByLabelText("Mes");
      await user.clear(monthInput);
      await user.type(monthInput, "2026-06");

      await user.click(screen.getByRole("button", { name: /descargar planilla/i }));

      await waitFor(() =>
        expect(mockDownloadImdertySheet).toHaveBeenCalledWith(7, {
          from: "2026-06",
          to: "2026-06",
          header: BLANK_HEADER,
          save_header_as_default: false,
        }),
      );
    });
  });
});
