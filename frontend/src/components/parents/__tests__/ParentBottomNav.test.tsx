import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { axe } from "jest-axe";

// Feature 038 (T303): "Bitácora" depende del atleta activo resuelto por
// useActiveAthlete → useMyAthletes. Se mockea la fuente de datos (mismo
// patrón que ParentSidebar.test.tsx) y se deja correr el hook real, así el
// store real de contexto de padres decide el atleta activo.
vi.mock("@/hooks/parents/useMyAthletes", () => ({
  useMyAthletes: vi.fn(),
}));

import { useMyAthletes } from "@/hooks/parents/useMyAthletes";
import { useParentContextStore } from "@/store/parentContext.store";
import { FamilyRelationship, MaturationStatus, Sex } from "@/types/enums";
import type { MyAthleteOut } from "@/types/parent.types";
import { ParentBottomNav } from "@/components/parents/ParentBottomNav";

// Feature 035 — ParentBottomNav (mockup PadresInicio.dc.html). Cinco slots
// fijos (sin "Más"), resolución de activo exact-match/longest-prefix
// (mismo algoritmo que resolveActiveItemId, reimplementado localmente) y
// tamaño táctil >=48px.

function mkAthlete(id: number, overrides: Partial<MyAthleteOut> = {}): MyAthleteOut {
  return {
    athlete_id: id,
    athlete_first_name: "Valeria",
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

function mockAthletes(athletes: MyAthleteOut[]) {
  vi.mocked(useMyAthletes).mockReturnValue({
    data: athletes,
    isLoading: false,
    isError: false,
    error: null,
  } as unknown as ReturnType<typeof useMyAthletes>);
}

beforeEach(() => {
  useParentContextStore.setState({ activeAthleteId: null });
  vi.clearAllMocks();
  // Sin atleta activo por defecto (0 o 2+ atletas sin selección) — mismo
  // set de 5 slots que antes de la feature 038, para no romper los tests
  // preexistentes de estructura/resolución de activo.
  mockAthletes([]);
});

function renderBottomNav(initialPath = "/my-athletes") {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <ParentBottomNav />
    </MemoryRouter>,
  );
}

describe("ParentBottomNav — estructura", () => {
  it("renderiza los cinco slots en el orden del mockup con sus rutas", () => {
    renderBottomNav();

    const nav = screen.getByRole("navigation", { name: "Navegación principal" });
    const links = Array.from(nav.querySelectorAll("a"));

    expect(links.map((a) => a.textContent?.trim())).toEqual([
      "Inicio",
      "Calendario",
      "Entrenos",
      "Resumen",
      "Perfil",
    ]);
    expect(links.map((a) => a.getAttribute("href"))).toEqual([
      "/my-athletes",
      "/parents/calendar",
      "/parents/training/sessions",
      "/parents/training/overview",
      "/perfil",
    ]);
  });

  it("no renderiza un disparador 'Más' (los 5 slots caben)", () => {
    renderBottomNav();
    expect(screen.queryByRole("button", { name: /Más/ })).not.toBeInTheDocument();
  });
});

describe("ParentBottomNav — resolución de activo", () => {
  it("/my-athletes marca 'Inicio' activo", () => {
    renderBottomNav("/my-athletes");
    expect(screen.getByRole("link", { name: "Inicio" })).toHaveAttribute(
      "aria-current",
      "page",
    );
  });

  it("una subruta de detalle (/my-athletes/42) mantiene 'Inicio' activo", () => {
    renderBottomNav("/my-athletes/42");
    expect(screen.getByRole("link", { name: "Inicio" })).toHaveAttribute(
      "aria-current",
      "page",
    );
  });

  it("/parents/calendar marca 'Calendario' activo", () => {
    renderBottomNav("/parents/calendar");
    expect(screen.getByRole("link", { name: "Calendario" })).toHaveAttribute(
      "aria-current",
      "page",
    );
  });

  it("/parents/training/sessions marca 'Entrenos' activo", () => {
    renderBottomNav("/parents/training/sessions");
    expect(screen.getByRole("link", { name: "Entrenos" })).toHaveAttribute(
      "aria-current",
      "page",
    );
  });

  it("/parents/training/overview marca 'Resumen' activo y NUNCA 'Entrenos' (caso de anidación)", () => {
    renderBottomNav("/parents/training/overview");

    expect(screen.getByRole("link", { name: "Resumen" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(screen.getByRole("link", { name: "Entrenos" })).not.toHaveAttribute(
      "aria-current",
    );
  });

  it("/perfil marca 'Perfil' activo", () => {
    renderBottomNav("/perfil");
    expect(screen.getByRole("link", { name: "Perfil" })).toHaveAttribute(
      "aria-current",
      "page",
    );
  });

  it("los slots inactivos no tienen aria-current", () => {
    renderBottomNav("/parents/calendar");

    for (const label of ["Inicio", "Entrenos", "Resumen", "Perfil"]) {
      expect(screen.getByRole("link", { name: label })).not.toHaveAttribute(
        "aria-current",
      );
    }
  });
});

describe("ParentBottomNav — reparto de color del estado activo", () => {
  it("el acento va en el ícono; el label activo se queda en charcoal semibold", () => {
    renderBottomNav("/parents/calendar");

    const active = screen.getByRole("link", { name: "Calendario" });
    // El acento (#008492) sobre blanco da 4.45:1 y no llega al piso AA de
    // 4.5:1 para texto normal — el label no puede llevarlo (mismo reparto
    // que SidebarNav). El peso semibold sigue diferenciándolo.
    expect(active.className).toMatch(/font-semibold/);
    expect(active.className).toMatch(/text-charcoal/);
    expect(active.className).not.toMatch(/text-nav-accent/);
    expect(active.querySelector("svg")?.getAttribute("class")).toMatch(/text-nav-accent/);
  });

  it("el ícono de un slot inactivo no lleva el acento", () => {
    renderBottomNav("/parents/calendar");

    const inactive = screen.getByRole("link", { name: "Inicio" });
    expect(inactive.querySelector("svg")?.getAttribute("class")).not.toMatch(
      /text-nav-accent/,
    );
  });
});

describe("ParentBottomNav — tamaño de objetivo táctil (>=48px)", () => {
  it("cada slot tiene min-h-[48px]", () => {
    renderBottomNav();

    for (const label of ["Inicio", "Calendario", "Entrenos", "Resumen", "Perfil"]) {
      const link = screen.getByRole("link", { name: label });
      expect(link.className).toMatch(/min-h-\[48px\]/);
    }
  });
});

describe("ParentBottomNav — accesibilidad", () => {
  it("sin violaciones axe", async () => {
    const { container } = renderBottomNav();
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});

// Feature 038, T303 — slot "Bitácora"
describe("ParentBottomNav — slot 'Bitácora' (feature 038)", () => {
  it("no aparece cuando no hay atleta activo resuelto (multi-hijo sin selección)", () => {
    mockAthletes([mkAthlete(7), mkAthlete(9)]);
    renderBottomNav();
    expect(screen.queryByRole("link", { name: "Bitácora" })).not.toBeInTheDocument();
  });

  it("aparece entre 'Resumen' y 'Perfil' cuando el padre tiene un solo hijo", () => {
    mockAthletes([mkAthlete(7)]);
    renderBottomNav();

    const nav = screen.getByRole("navigation", { name: "Navegación principal" });
    const links = Array.from(nav.querySelectorAll("a"));

    expect(links.map((a) => a.textContent?.trim())).toEqual([
      "Inicio",
      "Calendario",
      "Entrenos",
      "Resumen",
      "Bitácora",
      "Perfil",
    ]);
    expect(screen.getByRole("link", { name: "Bitácora" })).toHaveAttribute(
      "href",
      "/my-athletes/7/bitacora",
    );
  });

  it("apunta a la bitácora del atleta seleccionado explícitamente (multi-hijo)", () => {
    mockAthletes([mkAthlete(7), mkAthlete(9)]);
    useParentContextStore.setState({ activeAthleteId: 9 });
    renderBottomNav();

    expect(screen.getByRole("link", { name: "Bitácora" })).toHaveAttribute(
      "href",
      "/my-athletes/9/bitacora",
    );
  });

  it("marca 'Bitácora' activo en su ruta y en subrutas de detalle", () => {
    mockAthletes([mkAthlete(7)]);
    renderBottomNav("/my-athletes/7/bitacora/3");

    expect(screen.getByRole("link", { name: "Bitácora" })).toHaveAttribute(
      "aria-current",
      "page",
    );
  });
});
