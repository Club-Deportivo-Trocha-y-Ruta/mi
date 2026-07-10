/**
 * AthleteDetailPage — tarjeta de conexión Strava (feature 025, T027).
 *
 * Cubre los 4 estados de conexión (none/active/broken/disconnected),
 * los flujos de conectar/desconectar, y 0 violaciones axe en la superficie
 * de la tarjeta para cada estado.
 *
 * A diferencia de `AthleteDetailPage.test.tsx`, este archivo NO mockea
 * `@/api/client`: la tarjeta de Strava ejercita la capa HTTP real (axios)
 * contra handlers MSW (`@/test/msw/stravaHandlers`), consistente con el
 * criterio "vitest + Testing Library + MSW" del task T027. El resto de
 * datos del atleta (getAthlete/getAnthropometry) se mockea igual que en
 * el archivo base para no depender de esos endpoints.
 *
 * `@/store/auth.store` se mockea (rol `coach`) porque esta pestaña es una
 * de las dos superficies coach que habilitan `canLink` en `ActivityCard`
 * (T032b, cierre del gap de integración de `LinkSessionDialog`).
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, act, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { axe, toHaveNoViolations } from "jest-axe";
import { http } from "msw";

import { UserRole } from "@/types/enums";

expect.extend(toHaveNoViolations);

// ---------------------------------------------------------------------------
// Mocks — deben declararse antes de los imports de producción
// ---------------------------------------------------------------------------

vi.mock("@/store/auth.store", () => ({
  useAuthStore: (
    selector: (s: { accessToken: string; user: { id: number; role: UserRole } }) => unknown,
  ) => selector({ accessToken: "test-token", user: { id: 1, role: UserRole.coach } }),
}));

vi.mock("@/api/athletes", () => ({
  getAthlete: vi.fn(),
  getAnthropometry: vi.fn(),
  createAnthropometry: vi.fn(),
}));

vi.mock("@/api/parents", () => ({
  getParentAthletes: vi.fn().mockResolvedValue([]),
  getParentInvites: vi.fn().mockResolvedValue([]),
}));

vi.mock("@/api/ai", () => ({
  getPHVExplanation: vi.fn(),
  getPHVExplanationCached: vi.fn().mockResolvedValue(null),
}));

// Sub-componentes pesados que no son objeto de este archivo — mismo patrón
// que AthleteDetailPage.test.tsx.
vi.mock("@/components/athletes/AnthropometryForm", () => ({
  AnthropometryForm: () => <div data-testid="anthropometry-form">AnthropometryForm</div>,
}));
vi.mock("@/components/athletes/AnthropometryHistory", () => ({
  AnthropometryHistory: () => <div data-testid="anthropometry-history">AnthropometryHistory</div>,
}));
vi.mock("@/components/athletes/GrowthCharts", () => ({
  GrowthCharts: () => <div data-testid="growth-charts">GrowthCharts</div>,
}));
vi.mock("@/components/athletes/NutritionalClassification", () => ({
  NutritionalClassification: () => (
    <div data-testid="nutritional-classification">NutritionalClassification</div>
  ),
}));
vi.mock("@/components/athletes/TrainingReadiness", () => ({
  TrainingReadiness: () => <div data-testid="training-readiness">TrainingReadiness</div>,
}));
vi.mock("@/components/athletes/ResearchReferences", () => ({
  ResearchReferences: () => <div data-testid="research-references">ResearchReferences</div>,
}));
vi.mock("@/components/athletes/AthleteInfoCard", () => ({
  AthleteInfoCard: ({ athlete }: { athlete: { first_name: string; last_name: string } }) => (
    <div data-testid="athlete-info-card">
      {athlete.first_name} {athlete.last_name}
    </div>
  ),
}));
vi.mock("@/components/athletes/LinkedParentsCard", () => ({
  LinkedParentsCard: () => <div data-testid="linked-parents-card">LinkedParentsCard</div>,
}));
vi.mock("@/components/ai/PHVExplanationCard", () => ({
  PHVExplanationCard: () => <div data-testid="phv-explanation-card">PHVExplanationCard</div>,
}));
vi.mock("@/components/training/AthleteNewslettersTabPanel", () => ({
  AthleteNewslettersTabPanel: () => (
    <div data-testid="newsletters-tab-panel">AthleteNewslettersTabPanel</div>
  ),
}));

// ---------------------------------------------------------------------------
// Imports de producción (después de mocks)
// ---------------------------------------------------------------------------

import * as athletesApi from "@/api/athletes";
import { AthleteDetailPage } from "./AthleteDetailPage";
import { mswServer } from "@/test/setup";
import {
  stravaHandlers,
  noneConnectionHandler,
  brokenConnectionHandler,
  disconnectedConnectionHandler,
  connectionErrorHandler,
  connectServiceUnavailableHandler,
  emptyActivitiesHandler,
  activitiesErrorHandler,
} from "@/test/msw/stravaHandlers";
import type { AthleteDetailOut } from "@/types/athlete.types";
import { Sex } from "@/types/enums";

// ---------------------------------------------------------------------------
// Fixtures — DATOS FICTICIOS. Nunca usar datos reales de atletas menores.
// ---------------------------------------------------------------------------

const mockAthlete: AthleteDetailOut = {
  id: 42,
  user_id: 10,
  first_name: "Sebastián",
  last_name: "García Ficticio",
  birth_date: "2012-06-15",
  sex: Sex.M,
  club_join_date: "2023-01-01",
  years_in_club: 2.3,
  age_decimal: 13.5,
  category: "Sub-15",
  club_id: 1,
  created_at: "2023-01-01T00:00:00Z",
  latest_anthropometry: null,
};

// ---------------------------------------------------------------------------
// Helpers de render
// ---------------------------------------------------------------------------

function renderActivitiesTab(athleteId = "42") {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  return render(
    <MemoryRouter initialEntries={[`/athletes/${athleteId}?tab=activities`]}>
      <QueryClientProvider client={queryClient}>
        <Routes>
          <Route path="/athletes/:id" element={<AthleteDetailPage />} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

/** Devuelve el contenedor de la tarjeta "Conexión con Strava" (no el listado). */
function getConnectionCard(): HTMLElement {
  const heading = screen.getByText("Conexión con Strava");
  const card = heading.closest("div.rounded-xl");
  if (!card) throw new Error("No se encontró la tarjeta de conexión Strava");
  return card as HTMLElement;
}

// ---------------------------------------------------------------------------
// Suites
// ---------------------------------------------------------------------------

describe("AthleteDetailPage — tarjeta de conexión Strava", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(athletesApi.getAthlete).mockResolvedValue(mockAthlete);
    vi.mocked(athletesApi.getAnthropometry).mockResolvedValue([]);
    mswServer.use(...stravaHandlers);
  });

  // -------------------------------------------------------------------------
  // Estado: active
  // -------------------------------------------------------------------------

  describe("estado active", () => {
    it("muestra el badge 'Conectado' y quién autorizó la conexión", async () => {
      renderActivitiesTab();
      await screen.findByText("Conectado");
      const card = getConnectionCard();
      expect(within(card).getByText("Conectado")).toBeInTheDocument();
      expect(within(card).getByText(/María Ficticia Pérez/)).toBeInTheDocument();
    });

    it("muestra el botón Desconectar y NO el de Conectar", async () => {
      renderActivitiesTab();
      await screen.findByText("Conexión con Strava");
      expect(
        await screen.findByRole("button", { name: /Desconectar/i }),
      ).toBeInTheDocument();
      expect(
        screen.queryByRole("button", { name: /^Conectar con Strava$/i }),
      ).not.toBeInTheDocument();
    });

    it("renderiza las actividades sincronizadas del atleta", async () => {
      renderActivitiesTab();
      expect(await screen.findByText("Rodada matutina")).toBeInTheDocument();
      expect(screen.getByText("Salida familiar")).toBeInTheDocument();
    });

    it("no tiene violaciones de accesibilidad en la tarjeta de conexión", async () => {
      renderActivitiesTab();
      await screen.findByText("Conectado");
      const card = getConnectionCard();
      const results = await axe(card);
      expect(results).toHaveNoViolations();
    });
  });

  // -------------------------------------------------------------------------
  // Acción de enlace (T032b — coach ve el botón y puede abrir el diálogo)
  // -------------------------------------------------------------------------

  describe("acción de enlace", () => {
    it("cada actividad expone su acción de enlace/cambio de sesión para el coach", async () => {
      renderActivitiesTab();
      await screen.findByText("Rodada matutina");

      // Ambas actividades del fixture están sin enlazar → dos botones.
      const linkButtons = screen.getAllByRole("button", {
        name: /enlazar a sesión/i,
      });
      expect(linkButtons).toHaveLength(2);
    });

    it("hacer clic abre LinkSessionDialog para esa actividad", async () => {
      renderActivitiesTab();
      const [linkButton] = await screen.findAllByRole("button", {
        name: /enlazar a sesión/i,
      });
      await act(async () => {
        await userEvent.click(linkButton);
      });

      expect(await screen.findByRole("dialog")).toBeInTheDocument();
      expect(screen.getByText(/Vincular a sesión/i)).toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // Estado: none
  // -------------------------------------------------------------------------

  describe("estado none", () => {
    beforeEach(() => {
      mswServer.use(noneConnectionHandler);
    });

    it("muestra el badge 'Sin conectar' y el CTA 'Conectar con Strava' habilitado", async () => {
      renderActivitiesTab();
      await screen.findByText("Sin conectar");
      const card = getConnectionCard();
      expect(within(card).getByText("Sin conectar")).toBeInTheDocument();
      const cta = within(card).getByRole("button", { name: /Conectar con Strava/i });
      expect(cta).toBeEnabled();
    });

    it("muestra el mensaje explicativo de conexión inicial", async () => {
      renderActivitiesTab();
      expect(
        await screen.findByText(/Conecta la cuenta de Strava del atleta/i),
      ).toBeInTheDocument();
    });

    it("muestra el estado vacío de actividades cuando nunca se conectó", async () => {
      mswServer.use(emptyActivitiesHandler);
      renderActivitiesTab();
      expect(
        await screen.findByText("Sin actividades sincronizadas."),
      ).toBeInTheDocument();
    });

    it("no tiene violaciones de accesibilidad en la tarjeta de conexión", async () => {
      renderActivitiesTab();
      await screen.findByText("Sin conectar");
      const card = getConnectionCard();
      const results = await axe(card);
      expect(results).toHaveNoViolations();
    });
  });

  // -------------------------------------------------------------------------
  // Estado: broken
  // -------------------------------------------------------------------------

  describe("estado broken", () => {
    beforeEach(() => {
      mswServer.use(brokenConnectionHandler);
    });

    it("muestra el badge 'Conexión rota' y el CTA 'Reconectar'", async () => {
      renderActivitiesTab();
      await screen.findByText("Conexión rota");
      const card = getConnectionCard();
      expect(within(card).getByText("Conexión rota")).toBeInTheDocument();
      expect(
        within(card).getByRole("button", { name: /Reconectar/i }),
      ).toBeInTheDocument();
    });

    it("muestra el mensaje de autorización revocada o expirada", async () => {
      renderActivitiesTab();
      expect(
        await screen.findByText(/autorización revocada o.*expirada/i),
      ).toBeInTheDocument();
    });

    it("no tiene violaciones de accesibilidad en la tarjeta de conexión", async () => {
      renderActivitiesTab();
      await screen.findByText("Conexión rota");
      const card = getConnectionCard();
      const results = await axe(card);
      expect(results).toHaveNoViolations();
    });
  });

  // -------------------------------------------------------------------------
  // Estado: disconnected
  // -------------------------------------------------------------------------

  describe("estado disconnected", () => {
    beforeEach(() => {
      mswServer.use(disconnectedConnectionHandler);
    });

    it("muestra el badge 'Desconectado' y el CTA 'Reconectar'", async () => {
      renderActivitiesTab();
      await screen.findByText("Desconectado");
      const card = getConnectionCard();
      expect(within(card).getByText("Desconectado")).toBeInTheDocument();
      expect(
        within(card).getByRole("button", { name: /Reconectar/i }),
      ).toBeInTheDocument();
    });

    it("indica que las actividades ya sincronizadas se conservan", async () => {
      renderActivitiesTab();
      expect(
        await screen.findByText(/La sincronización está detenida/i),
      ).toBeInTheDocument();
      expect(
        screen.getByText(/Las actividades ya sincronizadas se conservan/i),
      ).toBeInTheDocument();
    });

    it("no tiene violaciones de accesibilidad en la tarjeta de conexión", async () => {
      renderActivitiesTab();
      await screen.findByText("Desconectado");
      const card = getConnectionCard();
      const results = await axe(card);
      expect(results).toHaveNoViolations();
    });
  });

  // -------------------------------------------------------------------------
  // Carga y error de la query de conexión
  // -------------------------------------------------------------------------

  describe("estados de carga y error", () => {
    it("muestra un skeleton mientras se resuelve el estado de conexión", async () => {
      mswServer.use(
        http.get(
          "*/api/athletes/:athleteId/strava/connection",
          () => new Promise(() => {}), // nunca resuelve — loading indefinido
        ),
      );
      renderActivitiesTab();
      await screen.findByText("Conexión con Strava");
      // En loading no se renderiza ningún badge de estado todavía.
      expect(screen.queryByText("Conectado")).not.toBeInTheDocument();
      expect(screen.queryByText("Sin conectar")).not.toBeInTheDocument();
    });

    it("muestra mensaje de error y permite reintentar si la conexión falla en cargar", async () => {
      mswServer.use(connectionErrorHandler);
      renderActivitiesTab();
      expect(
        await screen.findByText(/No se pudo cargar el estado de la conexión/i),
      ).toBeInTheDocument();
      expect(
        screen.getByRole("button", { name: /Reintentar/i }),
      ).toBeInTheDocument();
    });

    it("muestra mensaje de error en el listado de actividades", async () => {
      mswServer.use(activitiesErrorHandler);
      renderActivitiesTab();
      expect(
        await screen.findByText(/No se pudieron cargar las actividades/i),
      ).toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // Flujo de conexión (redirección OAuth)
  // -------------------------------------------------------------------------

  describe("flujo de conexión", () => {
    beforeEach(() => {
      mswServer.use(noneConnectionHandler);
    });

    it("redirige el navegador a authorize_url al hacer clic en Conectar", async () => {
      renderActivitiesTab();
      const cta = await screen.findByRole("button", {
        name: /Conectar con Strava/i,
      });

      // Interceptamos SOLO la asignación a `href` con un Proxy que delega
      // todo lo demás (origin/protocol/etc.) al Location real — jsdom usa
      // esos campos internamente al resolver la petición POST /connect vía
      // XHR, así que reemplazar window.location por completo (o borrar
      // `href` del prototipo) rompe la petición HTTP en curso.
      const realLocation = window.location;
      let capturedHref = "";
      const locationProxy = new Proxy(realLocation, {
        set(target, prop, value) {
          if (prop === "href") {
            capturedHref = String(value);
            return true;
          }
          return Reflect.set(target, prop, value);
        },
        get(target, prop) {
          const value = Reflect.get(target, prop);
          return typeof value === "function" ? value.bind(target) : value;
        },
      });
      Object.defineProperty(window, "location", {
        configurable: true,
        value: locationProxy,
      });

      await act(async () => {
        await userEvent.click(cta);
      });

      await vi.waitFor(() => {
        expect(capturedHref).toContain(
          "https://www.strava.com/oauth/authorize",
        );
      });

      Object.defineProperty(window, "location", {
        configurable: true,
        value: realLocation,
      });
    });

    it("muestra un error si el backend rechaza iniciar la conexión (503)", async () => {
      mswServer.use(connectServiceUnavailableHandler);
      renderActivitiesTab();
      const cta = await screen.findByRole("button", {
        name: /Conectar con Strava/i,
      });
      await act(async () => {
        await userEvent.click(cta);
      });
      expect(
        await screen.findByText(/No se pudo iniciar la conexión con Strava/i),
      ).toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // Flujo de desconexión (con confirmación)
  // -------------------------------------------------------------------------

  describe("flujo de desconexión", () => {
    it("pide confirmación antes de desconectar y actualiza el badge tras confirmar", async () => {
      renderActivitiesTab();
      const disconnectBtn = await screen.findByRole("button", {
        name: /Desconectar/i,
      });
      await act(async () => {
        await userEvent.click(disconnectBtn);
      });

      // Diálogo de confirmación visible
      const dialog = await screen.findByRole("alertdialog");
      expect(
        within(dialog).getByText(/Desconectar Strava/i),
      ).toBeInTheDocument();

      mswServer.use(disconnectedConnectionHandler);
      const confirmBtn = within(dialog).getByRole("button", {
        name: /^Desconectar$/i,
      });
      await act(async () => {
        await userEvent.click(confirmBtn);
      });

      await screen.findByText("Desconectado");
      expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    });

    it("cerrar el diálogo con Cancelar no desconecta la cuenta", async () => {
      renderActivitiesTab();
      const disconnectBtn = await screen.findByRole("button", {
        name: /Desconectar/i,
      });
      await act(async () => {
        await userEvent.click(disconnectBtn);
      });

      const dialog = await screen.findByRole("alertdialog");
      // El diálogo tiene DOS botones accesibles como "Cancelar": el ícono
      // "X" (aria-label) y el botón de texto del footer. Se distingue por
      // texto visible, único al botón del footer.
      const cancelBtn = within(dialog).getByText("Cancelar");
      await act(async () => {
        await userEvent.click(cancelBtn);
      });

      expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
      // Sigue conectado — el badge original permanece.
      expect(screen.getByText("Conectado")).toBeInTheDocument();
    });
  });
});
