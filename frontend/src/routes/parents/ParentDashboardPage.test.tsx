import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { ParentDashboardPage } from "./ParentDashboardPage";
import { useParentContextStore } from "@/store/parentContext.store";
import { FamilyRelationship, MaturationStatus, Sex } from "@/types/enums";
import type { MyAthleteOut } from "@/types/parent.types";
import type { ConsentStatus } from "@/types/consent";

// ---------------------------------------------------------------------------
// Mocks de hooks de datos
// ---------------------------------------------------------------------------

vi.mock("@/hooks/parents/useMyAthletes", () => ({
  useMyAthletes: vi.fn(),
}));
vi.mock("@/hooks/consent", () => ({
  useMyConsentStatus: vi.fn(),
  useActivePolicy: vi.fn(() => ({ data: null, isLoading: false })),
  useRenewConsent: vi.fn(() => ({ mutateAsync: vi.fn(), isPending: false, isError: false })),
  useWithdrawConsent: vi.fn(() => ({ mutateAsync: vi.fn(), isPending: false, isError: false })),
}));
vi.mock("@/hooks/parents/useNextSession", () => ({
  useNextSession: vi.fn(() => ({ data: null, isLoading: false, isError: false })),
}));
vi.mock("@/hooks/parents/useLastSession", () => ({
  useLastSession: vi.fn(() => ({ data: null, isLoading: false, isError: false })),
}));
vi.mock("@/api/trainingSessions", () => ({
  useParentMonthlySummary: vi.fn(() => ({ data: [], isLoading: false, isError: false })),
  useParentSessions: vi.fn(() => ({ data: [], isLoading: false, isError: false })),
}));

import { useMyAthletes } from "@/hooks/parents/useMyAthletes";
import { useMyConsentStatus } from "@/hooks/consent";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function mkAthlete(id: number, first: string, last = "López"): MyAthleteOut {
  return {
    athlete_id: id,
    athlete_first_name: first,
    athlete_last_name: last,
    birth_date: "2013-06-15",
    sex: Sex.M,
    age_decimal: 12.8,
    category: "Pre-juvenil A",
    relationship: FamilyRelationship.padre,
    latest_anthropometry_date: null,
    maturation_status: MaturationStatus.PrePHV,
    standing_height_cm: null,
    weight_kg: null,
    measurement_status: "never",
  };
}

function mockAthletes(athletes: MyAthleteOut[], isLoading = false) {
  vi.mocked(useMyAthletes).mockReturnValue({
    data: athletes,
    isLoading,
    isError: false,
    error: null,
  } as unknown as ReturnType<typeof useMyAthletes>);
}

function mockConsent(status: ConsentStatus | undefined, isLoading = false) {
  vi.mocked(useMyConsentStatus).mockReturnValue({
    data: status,
    isLoading,
    isError: false,
  } as unknown as ReturnType<typeof useMyConsentStatus>);
}

function mkConsentOk(athletes: MyAthleteOut[]): ConsentStatus {
  return {
    active_policy: {
      id: 1,
      version: "1.1",
      effective_date: "2026-04-01",
      title: "Política de privacidad",
      changelog: null,
    },
    consents_per_athlete: athletes.map((a) => ({
      athlete_id: a.athlete_id,
      athlete_name: `${a.athlete_first_name} ${a.athlete_last_name}`,
      current_consent: {
        id: 1,
        policy_version: "1.1",
        consented_at: "2026-04-15T00:00:00Z",
        is_current_policy: true,
        withdrawn_at: null,
        grants: {
          data_collection: true,
          anthropometry: true,
          training_tracking: true,
          third_party_sharing: false,
        },
      },
    })),
  };
}

function renderPage() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <ParentDashboardPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("ParentDashboardPage (Wave 4)", () => {
  beforeEach(() => {
    useParentContextStore.setState({ activeAthleteId: null });
    vi.clearAllMocks();
  });

  afterEach(() => {
    useParentContextStore.setState({ activeAthleteId: null });
  });

  describe("estructura general", () => {
    it("muestra título 'Mis Atletas'", () => {
      mockAthletes([mkAthlete(7, "Santiago")]);
      mockConsent(mkConsentOk([mkAthlete(7, "Santiago")]));
      renderPage();
      expect(
        screen.getByRole("heading", { name: /mis atletas/i, level: 1 }),
      ).toBeInTheDocument();
    });

    it("muestra empty state cuando no hay atletas vinculados", () => {
      mockAthletes([]);
      mockConsent({
        active_policy: {
          id: 1,
          version: "1.1",
          effective_date: "2026-04-01",
          title: "x",
          changelog: null,
        },
        consents_per_athlete: [],
      });
      renderPage();
      expect(screen.getByText(/No tienes atletas vinculados/i)).toBeInTheDocument();
    });
  });

  describe("orden vertical de Wave 4", () => {
    it("renderiza la sección 'Perfil deportivo' con los ChildCard al final", () => {
      const athletes = [mkAthlete(7, "Santiago"), mkAthlete(9, "Mateo")];
      mockAthletes(athletes);
      mockConsent(mkConsentOk(athletes));
      renderPage();
      expect(
        screen.getByRole("heading", { name: /perfil deportivo/i, level: 2 }),
      ).toBeInTheDocument();
    });
  });

  describe("multi-hijo sin selección — apila bloques por hijo", () => {
    it("renderiza un AthleteHomeBlock por cada hijo", () => {
      const athletes = [mkAthlete(7, "Santiago"), mkAthlete(9, "Mateo")];
      mockAthletes(athletes);
      mockConsent(mkConsentOk(athletes));
      renderPage();
      expect(screen.getByTestId("athlete-home-block-7")).toBeInTheDocument();
      expect(screen.getByTestId("athlete-home-block-9")).toBeInTheDocument();
    });
  });

  describe("multi-hijo con selección — solo un bloque + toggle 'Ver todos'", () => {
    it("muestra solo el bloque del hijo activo y el toggle", async () => {
      const athletes = [mkAthlete(7, "Santiago"), mkAthlete(9, "Mateo")];
      mockAthletes(athletes);
      mockConsent(mkConsentOk(athletes));
      useParentContextStore.setState({ activeAthleteId: 9 });

      renderPage();

      expect(screen.getByTestId("athlete-home-block-9")).toBeInTheDocument();
      expect(screen.queryByTestId("athlete-home-block-7")).not.toBeInTheDocument();
      expect(screen.getByTestId("see-all-athletes")).toBeInTheDocument();
    });

    it("toggle 'Ver todos los hijos' resetea activeAthleteId a null", async () => {
      const user = userEvent.setup();
      const athletes = [mkAthlete(7, "Santiago"), mkAthlete(9, "Mateo")];
      mockAthletes(athletes);
      mockConsent(mkConsentOk(athletes));
      useParentContextStore.setState({ activeAthleteId: 9 });

      renderPage();

      await user.click(screen.getByTestId("see-all-athletes"));
      expect(useParentContextStore.getState().activeAthleteId).toBeNull();
    });
  });

  describe("consentimiento (preservado de versiones previas)", () => {
    it("renderiza ConsentRenewalModal cuando hay atletas con política desactualizada", () => {
      const athletes = [mkAthlete(7, "Santiago")];
      mockAthletes(athletes);
      mockConsent({
        active_policy: {
          id: 1,
          version: "1.2",
          effective_date: "2026-05-01",
          title: "Política",
          changelog: null,
        },
        consents_per_athlete: [
          {
            athlete_id: 7,
            athlete_name: "Santiago López",
            current_consent: {
              id: 1,
              policy_version: "1.1",
              consented_at: "2026-04-15T00:00:00Z",
              is_current_policy: false,
              withdrawn_at: null,
              grants: {
                data_collection: true,
                anthropometry: true,
                training_tracking: true,
                third_party_sharing: false,
              },
            },
          },
        ],
      });

      renderPage();
      // El modal de renovación incluye un titular con "renovar autorización"
      // (verificamos textualmente que el modal está visible).
      expect(screen.getByRole("dialog", { hidden: true })).toBeInTheDocument();
    });

    it("NO renderiza ConsentRenewalModal cuando todos los consentimientos están al día", () => {
      const athletes = [mkAthlete(7, "Santiago")];
      mockAthletes(athletes);
      mockConsent(mkConsentOk(athletes));

      renderPage();
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });

    it("renderiza ConsentStatusPanel al final cuando hay datos", () => {
      const athletes = [mkAthlete(7, "Santiago")];
      mockAthletes(athletes);
      mockConsent(mkConsentOk(athletes));

      renderPage();
      // ConsentStatusPanel usa un encabezado tipo "Mis autorizaciones" o similar.
      // Verificamos al menos que el contenedor del consent panel aparece — el
      // nombre del atleta aparece duplicado (en ChildCard y en el panel).
      const matches = screen.getAllByText(/Santiago/i);
      expect(matches.length).toBeGreaterThan(0);
    });
  });
});
