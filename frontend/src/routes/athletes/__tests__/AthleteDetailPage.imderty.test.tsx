/**
 * AthleteDetailPage.imderty.test.tsx — feature 047.
 *
 * La sección IMDERTY (perfil + contacto principal + datos sensibles) dejó
 * de vivir bajo el hero (`AthleteInfoCard`) y pasó a su propia pestaña
 * «Perfil IMDERTY», solo admin/coach. Cubre: visibilidad por rol, deep link
 * `?tab=imderty`, forma legada `#imderty-profile` sin `tab`, fallback de
 * padre/atleta y axe sobre la pestaña.
 *
 * Privacidad Ley 1581: fixtures 100 % sintéticas.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { axe, toHaveNoViolations } from "jest-axe";

expect.extend(toHaveNoViolations);

vi.mock("@/hooks/athletes/useAthlete", () => ({
  useAthlete: vi.fn(),
}));
vi.mock("@/components/athletes/AthleteInfoCard", () => ({
  AthleteInfoCard: () => <div data-testid="athlete-info-card">InfoCard</div>,
}));
vi.mock("@/components/athletes/LinkedParentsCard", () => ({
  LinkedParentsCard: () => <div data-testid="linked-parents-card">LinkedParentsCard</div>,
}));
vi.mock("@/components/imderty/ImdertyProfileCard", () => ({
  ImdertyProfileCard: ({ athleteId }: { athleteId: number }) => (
    <section id="imderty-profile" data-testid="imderty-profile-card">
      Tarjeta IMDERTY {athleteId}
    </section>
  ),
}));

import { useAthlete } from "@/hooks/athletes/useAthlete";
import { AthleteDetailPage } from "../AthleteDetailPage";
import { mswServer } from "@/test/setup";
import { makeGrowthSummary } from "@/test/msw/growthSummaryHandlers";
import { useAuthStore } from "@/store/auth.store";
import { Sex, UserRole } from "@/types/enums";
import type { AthleteDetailOut } from "@/types/athlete.types";
import type { MeResponse } from "@/types/auth.types";

const ATHLETE_ID = 9;

const mockAthlete: AthleteDetailOut = {
  id: ATHLETE_ID,
  user_id: 900,
  first_name: "Atleta",
  last_name: "Ficticio",
  birth_date: "2013-03-10",
  sex: Sex.F,
  club_join_date: "2023-01-01",
  years_in_club: 2.0,
  age_decimal: 13.0,
  category: "Sub-15",
  club_id: 1,
  created_at: "2023-01-01T00:00:00Z",
  latest_anthropometry: null,
};

function setRole(role: UserRole) {
  useAuthStore.setState({
    user: { id: 1, email: "u@example.test", role } as MeResponse,
    isAuthenticated: true,
    isLoading: false,
  });
}

function LocationProbe() {
  const location = useLocation();
  return (
    <>
      <span data-testid="location-search">{location.search}</span>
      <span data-testid="location-hash">{location.hash}</span>
    </>
  );
}

function renderPage(suffix = "") {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
  });
  return render(
    <MemoryRouter initialEntries={[`/athletes/${ATHLETE_ID}${suffix}`]}>
      <QueryClientProvider client={queryClient}>
        <LocationProbe />
        <Routes>
          <Route path="/athletes/:id" element={<AthleteDetailPage />} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

describe("AthleteDetailPage — pestaña «Perfil IMDERTY» (047)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useAthlete).mockReturnValue({
      data: mockAthlete,
      isLoading: false,
      isError: false,
      error: null,
    } as unknown as ReturnType<typeof useAthlete>);
    mswServer.use(
      http.get("*/api/athletes/:athleteId/anthropometry", () => HttpResponse.json([])),
      http.get("*/api/athletes/:athleteId/growth-summary", () =>
        HttpResponse.json(makeGrowthSummary()),
      ),
    );
  });

  afterEach(() => {
    useAuthStore.setState({ user: null, isAuthenticated: false });
  });

  it.each([UserRole.coach, UserRole.admin])(
    "%s ve la pestaña entre «Historial» y «Actividades», sin la tarjeta en la vista inicial",
    async (role) => {
      setRole(role);
      renderPage();
      const tab = await screen.findByTestId("athlete-tab-imderty");
      expect(tab).toHaveTextContent("Perfil IMDERTY");
      // Orden en la barra: Historial → Perfil IMDERTY → Actividades.
      const history = screen.getByTestId("athlete-tab-history");
      const activities = screen.getByTestId("athlete-tab-activities");
      expect(history.compareDocumentPosition(tab) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
      expect(tab.compareDocumentPosition(activities) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
      // La tarjeta ya no empuja las demás pestañas: no se monta en «Info general».
      expect(screen.queryByTestId("imderty-profile-card")).not.toBeInTheDocument();
      expect(screen.getByText(/Datos del atleta/i)).toBeInTheDocument();
    },
  );

  it("clic en la pestaña monta la tarjeta y deja ?tab=imderty en la URL", async () => {
    setRole(UserRole.coach);
    renderPage();
    await act(async () => {
      await userEvent.click(await screen.findByTestId("athlete-tab-imderty"));
    });
    expect(screen.getByTestId("imderty-profile-card")).toHaveTextContent(`${ATHLETE_ID}`);
    expect(screen.getByTestId("location-search")).toHaveTextContent("tab=imderty");
    expect(screen.queryByText(/Datos del atleta/i)).not.toBeInTheDocument();
  });

  it("?tab=imderty abre directo la pestaña (coach)", async () => {
    setRole(UserRole.coach);
    renderPage("?tab=imderty#imderty-profile");
    expect(await screen.findByTestId("imderty-profile-card")).toBeInTheDocument();
    expect(screen.getByTestId("athlete-tab-imderty")).toHaveClass("bg-charcoal");
    expect(screen.getByTestId("location-hash")).toHaveTextContent("#imderty-profile");
  });

  it("forma legada #imderty-profile sin ?tab se normaliza a ?tab=imderty conservando el ancla", async () => {
    setRole(UserRole.admin);
    renderPage("#imderty-profile");
    expect(await screen.findByTestId("imderty-profile-card")).toBeInTheDocument();
    expect(screen.getByTestId("location-search")).toHaveTextContent("?tab=imderty");
    expect(screen.getByTestId("location-hash")).toHaveTextContent("#imderty-profile");
  });

  it("tras la forma legada, cambiar a «Info general» no vuelve a saltar a IMDERTY", async () => {
    setRole(UserRole.coach);
    renderPage("#imderty-profile");
    await screen.findByTestId("imderty-profile-card");
    await act(async () => {
      await userEvent.click(screen.getByRole("button", { name: /Info general/i }));
    });
    expect(screen.queryByTestId("imderty-profile-card")).not.toBeInTheDocument();
    expect(screen.getByText(/Datos del atleta/i)).toBeInTheDocument();
  });

  it.each([UserRole.parent, UserRole.athlete])(
    "%s no ve la pestaña y ?tab=imderty cae a «Info general»",
    async (role) => {
      setRole(role);
      renderPage("?tab=imderty#imderty-profile");
      expect(await screen.findByText(/Datos del atleta/i)).toBeInTheDocument();
      expect(screen.queryByTestId("athlete-tab-imderty")).not.toBeInTheDocument();
      expect(screen.queryByTestId("imderty-profile-card")).not.toBeInTheDocument();
    },
  );

  it("padre con la forma legada #imderty-profile se queda en «Info general»", async () => {
    setRole(UserRole.parent);
    renderPage("#imderty-profile");
    expect(await screen.findByText(/Datos del atleta/i)).toBeInTheDocument();
    expect(screen.queryByTestId("imderty-profile-card")).not.toBeInTheDocument();
    expect(screen.getByTestId("location-search")).toBeEmptyDOMElement();
  });

  it("la página con la pestaña IMDERTY activa no tiene violaciones axe", async () => {
    setRole(UserRole.coach);
    const { container } = renderPage("?tab=imderty");
    await screen.findByTestId("imderty-profile-card");
    expect(await axe(container)).toHaveNoViolations();
  });
});
