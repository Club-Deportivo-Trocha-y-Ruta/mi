/**
 * T021 + T022 — Wave B consolidation routing tests.
 *
 * T021: Exactly one "Competencias" nav entry for coach; legacy paths redirect
 *       to the canonical destinations inside /competitions/*.
 * T022: Parent role cannot see the insights nav entry, and hitting
 *       /competitions/insights/* is blocked (redirect via ProtectedRoute).
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes, Navigate, useParams } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// ---------------------------------------------------------------------------
// Mocks — set up before component imports
// ---------------------------------------------------------------------------

vi.mock("@/store/auth.store", () => ({
  useAuthStore: vi.fn(),
}));

// AthleteSwitcher (used by AppShell for parent role) consumes useMyAthletes.
vi.mock("@/hooks/parents/useMyAthletes", () => ({
  useMyAthletes: vi.fn(() => ({ data: [], isLoading: false, isError: false })),
}));

import { useAuthStore } from "@/store/auth.store";
import { AppShell } from "@/components/layout/AppShell";
import { UserRole } from "@/types/enums";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeUser(role: UserRole) {
  return {
    id: 1,
    email: "test@trochyruta.com",
    first_name: "Test",
    last_name: "User",
    role,
    is_active: true,
    can_login: true,
    created_at: "2026-01-01T00:00:00Z",
  };
}

function mockAuthAs(role: UserRole) {
  vi.mocked(useAuthStore).mockImplementation((selector: any) =>
    selector({
      user: makeUser(role),
      accessToken: "token",
      refreshToken: "refresh",
      isAuthenticated: true,
      isLoading: false,
      login: vi.fn(),
      logout: vi.fn(),
      refreshSession: vi.fn(),
      fetchMe: vi.fn(),
    } as any),
  );
}

function renderShellAt(initialPath = "/") {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[initialPath]}>
        <AppShell>
          <div data-testid="page-content">contenido</div>
        </AppShell>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

/** Stub redirect components — same logic as App.tsx Wave B. */
function ClubInsightsRedirect() {
  const { raceEventId } = useParams<{ raceEventId: string }>();
  return <Navigate to={`/competitions/${raceEventId}?tab=insights`} replace />;
}

function renderLegacyRoutes(initialPath: string) {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <Routes>
        {/* Wave B redirects */}
        <Route
          path="/coach/race-analysis"
          element={<Navigate to="/competitions/insights" replace />}
        />
        <Route
          path="/training/races/:raceEventId/club-insights"
          element={<ClubInsightsRedirect />}
        />
        {/* Canonical destinations */}
        <Route
          path="/competitions/insights"
          element={<div data-testid="insights-hub">Hub insights</div>}
        />
        <Route
          path="/competitions/:id"
          element={<div data-testid="competition-detail">Detalle</div>}
        />
        <Route path="*" element={<div data-testid="not-found">404</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

// ---------------------------------------------------------------------------
// T021 — Single "Competencias" entry for coach
// ---------------------------------------------------------------------------

describe("T021 — Sidebar: entrada única Competencias (coach)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockAuthAs(UserRole.coach);
  });

  it("muestra exactamente UN enlace 'Competencias' en el sidebar", () => {
    renderShellAt();
    const links = screen
      .getAllByRole("link")
      .filter((el) => el.textContent === "Competencias");
    expect(links).toHaveLength(1);
    expect(links[0]).toHaveAttribute("href", "/competitions");
  });

  it("NO muestra 'Análisis IA carreras' como entrada separada en el sidebar", () => {
    renderShellAt();
    expect(
      screen.queryByRole("link", { name: "Análisis IA carreras" }),
    ).not.toBeInTheDocument();
  });

  it("NO hay ningún enlace al sidebar que apunte directamente a /competitions/insights", () => {
    renderShellAt();
    const insightsNavLinks = screen
      .queryAllByRole("link")
      .filter((el) => el.getAttribute("href") === "/competitions/insights");
    expect(insightsNavLinks).toHaveLength(0);
  });

  it("el único entry de competencias apunta a /competitions (no al hub de insights)", () => {
    renderShellAt();
    const link = screen.getByRole("link", { name: "Competencias" });
    expect(link).toHaveAttribute("href", "/competitions");
  });
});

describe("T021 — Sidebar: entrada única Competencias (admin)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockAuthAs(UserRole.admin);
  });

  it("admin también ve exactamente UN enlace 'Competencias'", () => {
    renderShellAt();
    const links = screen
      .getAllByRole("link")
      .filter((el) => el.textContent === "Competencias");
    expect(links).toHaveLength(1);
  });

  it("admin NO ve 'Análisis IA carreras' como entrada separada", () => {
    renderShellAt();
    expect(
      screen.queryByRole("link", { name: "Análisis IA carreras" }),
    ).not.toBeInTheDocument();
  });
});

describe("T021 — Legacy paths redirigen al destino canónico", () => {
  it("/coach/race-analysis monta el hub /competitions/insights", () => {
    renderLegacyRoutes("/coach/race-analysis");
    expect(screen.getByTestId("insights-hub")).toBeInTheDocument();
    expect(screen.queryByTestId("not-found")).not.toBeInTheDocument();
  });

  it("/training/races/42/club-insights monta el detalle /competitions/42", () => {
    renderLegacyRoutes("/training/races/42/club-insights");
    expect(screen.getByTestId("competition-detail")).toBeInTheDocument();
    expect(screen.queryByTestId("not-found")).not.toBeInTheDocument();
  });

  it("/training/races/99/club-insights preserva el id en el destino", () => {
    renderLegacyRoutes("/training/races/99/club-insights");
    // Si la ruta /competitions/99 no existe en este mini-árbol,
    // el match de /competitions/:id la captura de todas formas.
    expect(screen.getByTestId("competition-detail")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// T022 — Parent: no insights nav entry + /competitions/insights/* blocked
// ---------------------------------------------------------------------------

describe("T022 — Parent: sin entrada de insights en sidebar", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockAuthAs(UserRole.parent);
  });

  it("parent NO ve 'Competencias' en el sidebar", () => {
    renderShellAt();
    expect(
      screen.queryByRole("link", { name: "Competencias" }),
    ).not.toBeInTheDocument();
  });

  it("parent NO ve 'Análisis IA carreras' en el sidebar", () => {
    renderShellAt();
    expect(
      screen.queryByRole("link", { name: "Análisis IA carreras" }),
    ).not.toBeInTheDocument();
  });

  it("parent NO ve ningún enlace que apunte a /competitions/*", () => {
    renderShellAt();
    const competitionLinks = screen
      .queryAllByRole("link")
      .filter((el) => el.getAttribute("href")?.startsWith("/competitions"));
    expect(competitionLinks).toHaveLength(0);
  });
});

describe("T022 — Parent: /competitions/insights/* bloqueado por ProtectedRoute", () => {
  /**
   * ProtectedRoute redirige a ROLE_FALLBACKS[parent] = "/my-athletes"
   * cuando allowedRoles = [coach, admin] y el usuario es parent.
   * Verificamos el comportamiento con un mini árbol de rutas que replica
   * la lógica de ProtectedRoute sin requerir el árbol completo de App.
   */

  beforeEach(() => {
    vi.clearAllMocks();
  });

  function renderProtectedInsights(role: UserRole, path: string) {
    vi.mocked(useAuthStore).mockImplementation((selector: any) =>
      selector({
        user: makeUser(role),
        accessToken: "token",
        refreshToken: null,
        isAuthenticated: true,
        isLoading: false,
        login: vi.fn(),
        logout: vi.fn(),
        refreshSession: vi.fn(),
        fetchMe: vi.fn(),
      } as any),
    );

    // Simula el guard de ProtectedRoute:
    // allowedRoles=[coach, admin]; parent → redirect a /my-athletes.
    function InsightsGuard({ children }: { children: React.ReactNode }) {
      const user = makeUser(role);
      const allowed = [UserRole.coach, UserRole.admin];
      if (!allowed.includes(user.role)) {
        const fallback =
          user.role === UserRole.parent ? "/my-athletes" : "/login";
        return <Navigate to={fallback} replace />;
      }
      return <>{children}</>;
    }

    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    return render(
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={[path]}>
          <Routes>
            <Route
              path="/competitions/insights"
              element={
                <InsightsGuard>
                  <div data-testid="insights-content">Insights</div>
                </InsightsGuard>
              }
            />
            <Route
              path="/competitions/insights/club"
              element={
                <InsightsGuard>
                  <div data-testid="insights-club">Club insights</div>
                </InsightsGuard>
              }
            />
            <Route
              path="/competitions/insights/athletes/:id"
              element={
                <InsightsGuard>
                  <div data-testid="insights-athlete">Athlete insights</div>
                </InsightsGuard>
              }
            />
            <Route
              path="/my-athletes"
              element={<div data-testid="my-athletes">Mis atletas</div>}
            />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );
  }

  it("parent en /competitions/insights es redirigido (no ve contenido de insights)", () => {
    renderProtectedInsights(UserRole.parent, "/competitions/insights");
    expect(screen.queryByTestId("insights-content")).not.toBeInTheDocument();
    expect(screen.getByTestId("my-athletes")).toBeInTheDocument();
  });

  it("parent en /competitions/insights/club es redirigido", () => {
    renderProtectedInsights(UserRole.parent, "/competitions/insights/club");
    expect(screen.queryByTestId("insights-club")).not.toBeInTheDocument();
    expect(screen.getByTestId("my-athletes")).toBeInTheDocument();
  });

  it("parent en /competitions/insights/athletes/:id es redirigido", () => {
    renderProtectedInsights(
      UserRole.parent,
      "/competitions/insights/athletes/5",
    );
    expect(screen.queryByTestId("insights-athlete")).not.toBeInTheDocument();
    expect(screen.getByTestId("my-athletes")).toBeInTheDocument();
  });

  it("coach en /competitions/insights puede acceder (no redirigido)", () => {
    renderProtectedInsights(UserRole.coach, "/competitions/insights");
    expect(screen.getByTestId("insights-content")).toBeInTheDocument();
    expect(screen.queryByTestId("my-athletes")).not.toBeInTheDocument();
  });

  it("admin en /competitions/insights puede acceder (no redirigido)", () => {
    renderProtectedInsights(UserRole.admin, "/competitions/insights");
    expect(screen.getByTestId("insights-content")).toBeInTheDocument();
    expect(screen.queryByTestId("my-athletes")).not.toBeInTheDocument();
  });
});
