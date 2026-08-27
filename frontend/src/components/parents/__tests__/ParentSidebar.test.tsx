import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { axe } from "jest-axe";

import { ParentSidebar } from "@/components/parents/ParentSidebar";
import { useParentContextStore } from "@/store/parentContext.store";
import { FamilyRelationship, MaturationStatus, Sex } from "@/types/enums";
import type { AthleteConsentStatus, CurrentConsent } from "@/types/consent";
import type { MyAthleteOut } from "@/types/parent.types";

// Feature 035 — ParentSidebar (mockup PadresMenu.dc.html). Mocks solo la
// fuente de datos subyacente (useMyAthletes) y deja correr el hook real
// useActiveAthlete + el store real useParentContextStore, mismo patrón que
// components/parents/__tests__/AthleteSwitcher.test.tsx — así setActiveAthlete
// se puede verificar contra el estado real del store en vez de un mock.

vi.mock("@/hooks/parents/useMyAthletes", () => ({
  useMyAthletes: vi.fn(),
}));
vi.mock("@/hooks/consent", () => ({
  useMyConsentStatus: vi.fn(),
}));
vi.mock("@/store/auth.store", () => ({
  useAuthStore: vi.fn(),
}));

import { useMyAthletes } from "@/hooks/parents/useMyAthletes";
import { useMyConsentStatus } from "@/hooks/consent";
import { useAuthStore } from "@/store/auth.store";

const logout = vi.fn();

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function mkAthlete(
  id: number,
  first: string,
  overrides: Partial<MyAthleteOut> = {},
): MyAthleteOut {
  return {
    athlete_id: id,
    athlete_first_name: first,
    athlete_last_name: "García",
    birth_date: "2013-06-15",
    sex: Sex.F,
    age_decimal: 12.8,
    category: "Infantil",
    relationship: FamilyRelationship.madre,
    latest_anthropometry_date: null,
    maturation_status: MaturationStatus.CircaPHV,
    standing_height_cm: null,
    weight_kg: null,
    measurement_status: "never",
    ...overrides,
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

function consentOk(): CurrentConsent {
  return {
    id: 1,
    policy_version: "1.1",
    consented_at: "2026-05-01T00:00:00Z",
    is_current_policy: true,
    withdrawn_at: null,
    grants: {
      data_collection: true,
      anthropometry: true,
      training_tracking: true,
      third_party_sharing: false,
    },
  };
}

function mkAthleteConsent(
  athleteId: number,
  athleteName: string,
  current: CurrentConsent | null,
): AthleteConsentStatus {
  return { athlete_id: athleteId, athlete_name: athleteName, current_consent: current };
}

function mockConsent(
  consentsPerAthlete: AthleteConsentStatus[] | undefined,
  isLoading = false,
) {
  vi.mocked(useMyConsentStatus).mockReturnValue({
    data: consentsPerAthlete
      ? {
          active_policy: {
            id: 1,
            version: "1.1",
            effective_date: "2026-05-01",
            title: "Política de privacidad",
            changelog: null,
          },
          consents_per_athlete: consentsPerAthlete,
        }
      : undefined,
    isLoading,
    isError: false,
  } as unknown as ReturnType<typeof useMyConsentStatus>);
}

function renderSidebar({
  initialPath = "/my-athletes",
  withClose = true,
}: { initialPath?: string; withClose?: boolean } = {}) {
  const onNavigate = vi.fn();
  const onClose = vi.fn();
  const utils = render(
    <MemoryRouter initialEntries={[initialPath]}>
      <ParentSidebar onNavigate={onNavigate} onClose={withClose ? onClose : undefined} />
    </MemoryRouter>,
  );
  return { onNavigate, onClose, ...utils };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("ParentSidebar", () => {
  beforeEach(() => {
    useParentContextStore.setState({ activeAthleteId: null });
    vi.clearAllMocks();
    vi.mocked(useAuthStore).mockImplementation((selector: any) =>
      selector({ logout } as any),
    );
    mockAthletes([
      mkAthlete(7, "Valeria", { category: "Infantil", age_decimal: 12.8 }),
      mkAthlete(9, "Samuel", { category: "Prejuvenil", age_decimal: 14.2 }),
    ]);
    mockConsent([
      mkAthleteConsent(7, "Valeria", consentOk()),
      mkAthleteConsent(9, "Samuel", consentOk()),
    ]);
  });

  afterEach(() => {
    useParentContextStore.setState({ activeAthleteId: null });
  });

  describe("marca y cabecera", () => {
    it("renderiza la marca y 'Portal de familias'", () => {
      renderSidebar();
      expect(screen.getByText("Trocha y Ruta")).toBeInTheDocument();
      expect(screen.getByText("Portal de familias")).toBeInTheDocument();
    });

    it("renderiza el botón cerrar con aria-label 'Cerrar menú' cuando se pasa onClose, e invoca onClose al hacer click", async () => {
      const user = userEvent.setup();
      const { onClose } = renderSidebar({ withClose: true });

      const closeButton = screen.getByRole("button", { name: "Cerrar menú" });
      expect(closeButton).toBeInTheDocument();

      await user.click(closeButton);
      expect(onClose).toHaveBeenCalledTimes(1);
    });

    it("el botón cerrar se oculta en ≥md: allí la barra es fija y no hay overlay que cerrar", () => {
      renderSidebar({ withClose: true });

      // El contenedor es UNO SOLO (drawer bajo md, barra fija arriba) y la
      // presentación la decide el CSS, así que el X desaparece por la misma
      // vía en vez de quedar como control inerte en escritorio.
      expect(
        screen.getByRole("button", { name: "Cerrar menú" }).className,
      ).toMatch(/md:hidden/);
    });

    it("no renderiza el botón cerrar cuando no se pasa onClose", () => {
      renderSidebar({ withClose: false });
      expect(
        screen.queryByRole("button", { name: "Cerrar menú" }),
      ).not.toBeInTheDocument();
    });
  });

  describe("navegación principal", () => {
    it("renderiza los 4 enlaces del mockup con sus rutas, en orden", () => {
      renderSidebar();
      const nav = screen.getByRole("navigation", { name: "Secciones" });
      const links = within(nav).getAllByRole("link");

      expect(links.map((a) => a.textContent?.trim())).toEqual([
        "Inicio",
        "Calendario",
        "Entrenamientos",
        "Resumen mensual",
      ]);
      expect(links.map((a) => a.getAttribute("href"))).toEqual([
        "/my-athletes",
        "/parents/calendar",
        "/parents/training/sessions",
        "/parents/training/overview",
      ]);
    });

    it("/my-athletes marca 'Inicio' activo (aria-current=page)", () => {
      renderSidebar({ initialPath: "/my-athletes" });
      expect(screen.getByRole("link", { name: "Inicio" })).toHaveAttribute(
        "aria-current",
        "page",
      );
    });

    it("una subruta de detalle (/my-athletes/42) mantiene 'Inicio' activo", () => {
      renderSidebar({ initialPath: "/my-athletes/42" });
      expect(screen.getByRole("link", { name: "Inicio" })).toHaveAttribute(
        "aria-current",
        "page",
      );
    });

    it("/parents/calendar marca 'Calendario' activo", () => {
      renderSidebar({ initialPath: "/parents/calendar" });
      expect(screen.getByRole("link", { name: "Calendario" })).toHaveAttribute(
        "aria-current",
        "page",
      );
    });

    it("/parents/training/overview marca 'Resumen mensual' activo y NUNCA 'Entrenamientos' (caso de anidación)", () => {
      renderSidebar({ initialPath: "/parents/training/overview" });

      expect(screen.getByRole("link", { name: "Resumen mensual" })).toHaveAttribute(
        "aria-current",
        "page",
      );
      expect(screen.getByRole("link", { name: "Entrenamientos" })).not.toHaveAttribute(
        "aria-current",
      );
    });

    it("los enlaces inactivos no tienen aria-current", () => {
      renderSidebar({ initialPath: "/parents/calendar" });

      for (const label of ["Inicio", "Entrenamientos", "Resumen mensual"]) {
        expect(screen.getByRole("link", { name: label })).not.toHaveAttribute(
          "aria-current",
        );
      }
    });
  });

  describe("selector de atleta", () => {
    it("renderiza una fila por atleta con nombre y edad/categoría", () => {
      renderSidebar();
      expect(screen.getByText("Valeria")).toBeInTheDocument();
      expect(screen.getByText("12 años · Infantil")).toBeInTheDocument();
      expect(screen.getByText("Samuel")).toBeInTheDocument();
      expect(screen.getByText("14 años · Prejuvenil")).toBeInTheDocument();
      expect(screen.getByText("Todos mis atletas")).toBeInTheDocument();
    });

    it("no renderiza la sección cuando no hay atletas vinculados", () => {
      mockAthletes([]);
      renderSidebar();
      expect(screen.queryByText("Tus deportistas")).not.toBeInTheDocument();
      expect(screen.queryByText("Todos mis atletas")).not.toBeInTheDocument();
    });

    it("no renderiza la sección mientras useMyAthletes está cargando", () => {
      mockAthletes([], true);
      renderSidebar();
      expect(screen.queryByText("Tus deportistas")).not.toBeInTheDocument();
    });

    it("al hacer click en un atleta dispara setActiveAthlete(id) y onNavigate", async () => {
      const user = userEvent.setup();
      const { onNavigate } = renderSidebar();

      await user.click(screen.getByTestId("parent-sidebar-athlete-9"));

      expect(useParentContextStore.getState().activeAthleteId).toBe(9);
      expect(onNavigate).toHaveBeenCalledTimes(1);
    });

    it("marca el atleta activo con aria-current='true' (el resto sin aria-current)", () => {
      useParentContextStore.setState({ activeAthleteId: 7 });
      renderSidebar();

      expect(screen.getByTestId("parent-sidebar-athlete-7")).toHaveAttribute(
        "aria-current",
        "true",
      );
      expect(screen.getByTestId("parent-sidebar-athlete-9")).not.toHaveAttribute(
        "aria-current",
      );
    });

    it("'Todos mis atletas' dispara setActiveAthlete(null) y onNavigate", async () => {
      const user = userEvent.setup();
      useParentContextStore.setState({ activeAthleteId: 7 });
      const { onNavigate } = renderSidebar();

      await user.click(screen.getByTestId("parent-sidebar-athlete-all"));

      expect(useParentContextStore.getState().activeAthleteId).toBeNull();
      expect(onNavigate).toHaveBeenCalledTimes(1);
    });
  });

  describe("cuenta", () => {
    it("renderiza 'Mi perfil' enlazando a /perfil", () => {
      renderSidebar();
      expect(screen.getByRole("link", { name: /Mi perfil/ })).toHaveAttribute(
        "href",
        "/perfil",
      );
    });

    it("'Cerrar sesión' invoca logout() del auth store", async () => {
      const user = userEvent.setup();
      renderSidebar();

      await user.click(screen.getByRole("button", { name: "Cerrar sesión" }));
      expect(logout).toHaveBeenCalledTimes(1);
    });
  });

  describe("chip de consentimiento", () => {
    it("muestra 'Consentimientos al día' cuando todos los atletas están al día", () => {
      mockConsent([
        mkAthleteConsent(7, "Valeria", consentOk()),
        mkAthleteConsent(9, "Samuel", consentOk()),
      ]);
      renderSidebar();
      expect(screen.getByTestId("parent-sidebar-consent-chip")).toHaveTextContent(
        "Consentimientos al día",
      );
    });

    it("muestra 'Consentimiento por renovar' cuando falta consentimiento (null)", () => {
      mockConsent([
        mkAthleteConsent(7, "Valeria", null),
        mkAthleteConsent(9, "Samuel", consentOk()),
      ]);
      renderSidebar();
      expect(screen.getByTestId("parent-sidebar-consent-chip")).toHaveTextContent(
        "Consentimiento por renovar",
      );
    });

    it("muestra 'Consentimiento por renovar' cuando la política está desactualizada", () => {
      mockConsent([
        mkAthleteConsent(7, "Valeria", { ...consentOk(), is_current_policy: false }),
      ]);
      renderSidebar();
      expect(screen.getByTestId("parent-sidebar-consent-chip")).toHaveTextContent(
        "Consentimiento por renovar",
      );
    });

    it("muestra 'Consentimiento por renovar' cuando fue revocado", () => {
      mockConsent([
        mkAthleteConsent(7, "Valeria", {
          ...consentOk(),
          withdrawn_at: "2026-05-01T00:00:00Z",
        }),
      ]);
      renderSidebar();
      expect(screen.getByTestId("parent-sidebar-consent-chip")).toHaveTextContent(
        "Consentimiento por renovar",
      );
    });

    it("no renderiza chip mientras está cargando", () => {
      mockConsent(undefined, true);
      renderSidebar();
      expect(
        screen.queryByTestId("parent-sidebar-consent-chip"),
      ).not.toBeInTheDocument();
    });

    it("no renderiza chip cuando la query falla (sin data)", () => {
      mockConsent(undefined, false);
      renderSidebar();
      expect(
        screen.queryByTestId("parent-sidebar-consent-chip"),
      ).not.toBeInTheDocument();
    });
  });

  describe("accesibilidad", () => {
    it("sin violaciones axe", async () => {
      const { container } = renderSidebar();
      const results = await axe(container);
      expect(results).toHaveNoViolations();
    });
  });
});
