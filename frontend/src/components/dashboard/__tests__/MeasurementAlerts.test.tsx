import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { MeasurementAlerts } from "../MeasurementAlerts";
import type { AlertsSummary, AthleteAlert } from "@/types/alerts.types";

vi.mock("@/hooks/athletes/useAlerts", () => ({
  useAlerts: vi.fn(),
}));

// `vi.hoisted` corre antes de que los imports se resuelvan — mismo patrón
// que ActivityCard.test.tsx / AthleteLink.test.tsx para poder alternar el rol
// entre tests del mismo archivo. Default "coach" porque los tests
// preexistentes de esta suite asumen que el nombre del atleta es un <a>
// navegable (AthleteLink solo renderiza <Link> para coach — ver
// src/components/shared/AthleteLink.tsx).
const authState = vi.hoisted(() => ({
  role: "coach" as string | undefined,
}));

vi.mock("@/store/auth.store", () => ({
  useAuthStore: (
    selector: (s: { user: { id: number; role: string | undefined } | null }) => unknown,
  ) => selector({ user: { id: 1, role: authState.role } }),
}));

import { useAlerts } from "@/hooks/athletes/useAlerts";

const mockUseAlerts = vi.mocked(useAlerts);

beforeEach(() => {
  authState.role = "coach";
});

function makeAlert(overrides: Partial<AthleteAlert>): AthleteAlert {
  return {
    athlete_id: 1,
    athlete_name: "Atleta Ficticio",
    sex: "M",
    age_decimal: 12,
    category: "sub-13",
    measurement_status: "overdue",
    last_measurement_date: null,
    next_due_date: null,
    days_overdue: 10,
    current_phv_status: null,
    measurement_interval_days: 90,
    growth_velocity_cm_month: null,
    growth_alerts: [],
    training_implications: null,
    ...overrides,
  };
}

function makeSummary(athletes: AthleteAlert[]): AlertsSummary {
  return {
    overdue: athletes.filter((a) => a.measurement_status === "overdue").length,
    due_soon: athletes.filter((a) => a.measurement_status === "due_soon").length,
    ok: athletes.filter((a) => a.measurement_status === "ok").length,
    never_measured: athletes.filter((a) => a.measurement_status === "never").length,
    rapid_growth_count: 0,
    athletes,
  };
}

function renderComponent() {
  return render(
    <MemoryRouter>
      <MeasurementAlerts />
    </MemoryRouter>
  );
}

describe("MeasurementAlerts", () => {
  it("ante isError=true muestra ErrorState con Reintentar (no texto ad hoc sin salida)", () => {
    const refetch = vi.fn();
    mockUseAlerts.mockReturnValue({
      data: undefined,
      isPending: false,
      isError: true,
      refetch,
    } as unknown as ReturnType<typeof useAlerts>);

    renderComponent();

    expect(screen.getByRole("alert")).toBeInTheDocument();
    const retryButton = screen.getByRole("button", { name: /Reintentar/ });
    expect(retryButton).toBeInTheDocument();

    fireEvent.click(retryButton);

    expect(refetch).toHaveBeenCalledTimes(1);
  });

  it("muestra maximo 8 filas cuando hay 40 atletas accionables", () => {
    const athletes: AthleteAlert[] = Array.from({ length: 40 }, (_, i) =>
      makeAlert({
        athlete_id: i + 1,
        athlete_name: `Atleta Ficticio ${i + 1}`,
        measurement_status: "overdue",
        days_overdue: i + 1,
      })
    );
    mockUseAlerts.mockReturnValue({
      data: makeSummary(athletes),
      isPending: false,
      isError: false,
    } as ReturnType<typeof useAlerts>);

    renderComponent();

    const rows = screen.getAllByRole("listitem");
    expect(rows).toHaveLength(8);
  });

  it("ordena: vencidas (desc por dias) primero, luego proximas (asc por dias), luego sin medir", () => {
    const athletes: AthleteAlert[] = [
      makeAlert({ athlete_id: 1, athlete_name: "Nunca Medido Ficticio", measurement_status: "never", days_overdue: null }),
      makeAlert({ athlete_id: 2, athlete_name: "Proxima Lejana Ficticio", measurement_status: "due_soon", days_overdue: -10 }),
      makeAlert({ athlete_id: 3, athlete_name: "Vencida Chica Ficticio", measurement_status: "overdue", days_overdue: 5 }),
      makeAlert({ athlete_id: 4, athlete_name: "Vencida Grande Ficticio", measurement_status: "overdue", days_overdue: 20 }),
      makeAlert({ athlete_id: 5, athlete_name: "Proxima Cercana Ficticio", measurement_status: "due_soon", days_overdue: -2 }),
    ];
    mockUseAlerts.mockReturnValue({
      data: makeSummary(athletes),
      isPending: false,
      isError: false,
    } as ReturnType<typeof useAlerts>);

    renderComponent();

    const names = screen
      .getAllByRole("listitem")
      .map((li) => li.querySelector("a")?.textContent);

    expect(names).toEqual([
      "Vencida Grande Ficticio",
      "Vencida Chica Ficticio",
      "Proxima Cercana Ficticio",
      "Proxima Lejana Ficticio",
      "Nunca Medido Ficticio",
    ]);
  });

  it('muestra "Ver todas (N)" con link a /athletes cuando hay mas de 8 accionables', () => {
    const athletes: AthleteAlert[] = Array.from({ length: 40 }, (_, i) =>
      makeAlert({ athlete_id: i + 1, athlete_name: `Atleta Ficticio ${i + 1}` })
    );
    mockUseAlerts.mockReturnValue({
      data: makeSummary(athletes),
      isPending: false,
      isError: false,
    } as ReturnType<typeof useAlerts>);

    renderComponent();

    const link = screen.getByRole("link", { name: "Ver todas (40)" });
    expect(link).toHaveAttribute("href", "/athletes");
    // Única vía a las alertas más allá del tope de 8: objetivo táctil real
    // (≥44px) y tinta legible — el turquesa de marca da 2.42:1 sobre blanco.
    expect(link.className).toMatch(/min-h-11/);
    expect(link.className).toMatch(/text-charcoal/);
    expect(link.className).toMatch(/underline/);
  });

  it('no muestra el link "Ver todas" cuando hay 8 o menos accionables', () => {
    const athletes: AthleteAlert[] = Array.from({ length: 8 }, (_, i) =>
      makeAlert({ athlete_id: i + 1, athlete_name: `Atleta Ficticio ${i + 1}` })
    );
    mockUseAlerts.mockReturnValue({
      data: makeSummary(athletes),
      isPending: false,
      isError: false,
    } as ReturnType<typeof useAlerts>);

    renderComponent();

    expect(screen.queryByRole("link", { name: /Ver todas/ })).not.toBeInTheDocument();
  });

  it("omite la lista cuando no hay atletas accionables (todos al dia)", () => {
    const athletes: AthleteAlert[] = [
      makeAlert({ athlete_id: 1, athlete_name: "Al Dia Ficticio", measurement_status: "ok", days_overdue: null }),
    ];
    mockUseAlerts.mockReturnValue({
      data: makeSummary(athletes),
      isPending: false,
      isError: false,
    } as ReturnType<typeof useAlerts>);

    renderComponent();

    expect(screen.queryByRole("list")).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Ver todas/ })).not.toBeInTheDocument();
  });
});

describe("MeasurementAlerts — training_implications en crecimiento acelerado", () => {
  it("muestra training_implications cuando existe, reemplazando la guía genérica", () => {
    const athlete = makeAlert({
      measurement_status: "ok",
      days_overdue: null,
      growth_alerts: ["rapid_growth"],
      growth_velocity_cm_month: 1.2,
      training_implications: "Reducir intensidad de saltos y aterrizajes por 2 semanas.",
    });
    mockUseAlerts.mockReturnValue({
      data: makeSummary([athlete]),
      isPending: false,
      isError: false,
    } as ReturnType<typeof useAlerts>);

    renderComponent();

    expect(
      screen.getByText(/Reducir intensidad de saltos y aterrizajes por 2 semanas\./)
    ).toBeInTheDocument();
    expect(screen.queryByText(/Revisar carga de entrenamiento\./)).not.toBeInTheDocument();
  });

  it("usa la guía genérica cuando training_implications es null, sin hueco de texto", () => {
    const athlete = makeAlert({
      measurement_status: "ok",
      days_overdue: null,
      growth_alerts: ["rapid_growth"],
      growth_velocity_cm_month: 1.2,
      training_implications: null,
    });
    mockUseAlerts.mockReturnValue({
      data: makeSummary([athlete]),
      isPending: false,
      isError: false,
    } as ReturnType<typeof useAlerts>);

    renderComponent();

    expect(screen.getByText(/Revisar carga de entrenamiento\./)).toBeInTheDocument();
  });
});

describe("MeasurementAlerts — enlace al detalle del atleta según rol (AthleteLink)", () => {
  it('admin: el nombre del atleta se renderiza como texto plano, sin navegación (ProtectedRoute bounce en "/athletes/:id")', () => {
    authState.role = "admin";
    const athlete = makeAlert({
      athlete_id: 7,
      athlete_name: "Admin Ficticio",
      measurement_status: "overdue",
      days_overdue: 3,
      growth_alerts: ["rapid_growth"],
      growth_velocity_cm_month: 1.0,
    });
    mockUseAlerts.mockReturnValue({
      data: makeSummary([athlete]),
      isPending: false,
      isError: false,
    } as ReturnType<typeof useAlerts>);

    renderComponent();

    // Ningún link en toda la sección — ni en la lista de accionables ni en
    // el banner de crecimiento acelerado (con un solo atleta y sin superar
    // MAX_VISIBLE, tampoco aparece "Ver todas").
    expect(screen.queryAllByRole("link")).toHaveLength(0);

    // El nombre sigue visible como texto plano en ambos sitios de render.
    const nameNodes = screen.getAllByText("Admin Ficticio");
    expect(nameNodes.length).toBeGreaterThan(0);
    nameNodes.forEach((node) => expect(node.tagName).not.toBe("A"));
  });

  it("coach: el nombre del atleta es un link funcional a /athletes/{id}", () => {
    authState.role = "coach";
    const athlete = makeAlert({
      athlete_id: 9,
      athlete_name: "Coach Ficticio",
      measurement_status: "overdue",
      days_overdue: 4,
    });
    mockUseAlerts.mockReturnValue({
      data: makeSummary([athlete]),
      isPending: false,
      isError: false,
    } as ReturnType<typeof useAlerts>);

    renderComponent();

    const link = screen.getByRole("link", { name: "Coach Ficticio" });
    expect(link).toHaveAttribute("href", "/athletes/9");
  });

  it("coach: el nombre del atleta en el banner de crecimiento acelerado también es un link funcional", () => {
    authState.role = "coach";
    const athlete = makeAlert({
      athlete_id: 11,
      athlete_name: "Crecimiento Ficticio",
      measurement_status: "ok",
      days_overdue: null,
      growth_alerts: ["rapid_growth"],
      growth_velocity_cm_month: 1.5,
    });
    mockUseAlerts.mockReturnValue({
      data: makeSummary([athlete]),
      isPending: false,
      isError: false,
    } as ReturnType<typeof useAlerts>);

    renderComponent();

    const link = screen.getByRole("link", { name: "Crecimiento Ficticio" });
    expect(link).toHaveAttribute("href", "/athletes/11");
  });
});

// ---------------------------------------------------------------------------
// Feature 035 — encabezado de tarjeta, avatar con inicial e insignia de
// estado por fila (mockup `Main.dc.html`, fila C). Ninguna de estas pruebas
// toca la query ni el orden: sólo la presentación.
// ---------------------------------------------------------------------------

describe("MeasurementAlerts — tarjeta rediseñada (feature 035)", () => {
  it('titula "Alertas de medición" y enlaza a la lista de atletas desde el encabezado (coach)', () => {
    authState.role = "coach";
    mockUseAlerts.mockReturnValue({
      data: makeSummary([makeAlert({ athlete_id: 1, athlete_name: "Samuel Ficticio" })]),
      isPending: false,
      isError: false,
    } as ReturnType<typeof useAlerts>);

    renderComponent();

    const heading = screen.getByRole("heading", { name: "Alertas de medición" });
    const card = heading.closest("section");
    expect(card?.className).toMatch(/rounded-xl/);
    expect(card?.className).toMatch(/shadow-card/);

    const link = screen.getByRole("link", { name: "Ver todos los atletas" });
    expect(link).toHaveAttribute("href", "/athletes");
    // Objetivo táctil ≥44px (Constitution III).
    expect(link.className).toMatch(/min-h-11/);
    // Tinta legible: el turquesa de marca sobre blanco da 2.42:1 (falla AA).
    expect(link.className).toMatch(/text-charcoal/);
    expect(link.className).toMatch(/underline/);
  });

  it("admin: el enlace del encabezado no se renderiza (la lista es coach-only)", () => {
    authState.role = "admin";
    mockUseAlerts.mockReturnValue({
      data: makeSummary([makeAlert({ athlete_id: 1, athlete_name: "Samuel Ficticio" })]),
      isPending: false,
      isError: false,
    } as ReturnType<typeof useAlerts>);

    renderComponent();

    expect(screen.getByRole("heading", { name: "Alertas de medición" })).toBeInTheDocument();
    expect(screen.queryByText("Ver todos los atletas")).not.toBeInTheDocument();
  });

  it("cada fila lleva inicial, línea de detalle (PHV + días) e insignia de estado con texto", () => {
    authState.role = "coach";
    mockUseAlerts.mockReturnValue({
      data: makeSummary([
        makeAlert({
          athlete_id: 5,
          athlete_name: "Samuel Ficticio",
          measurement_status: "overdue",
          days_overdue: 30,
          current_phv_status: "Circa-PHV",
        }),
        makeAlert({
          athlete_id: 6,
          athlete_name: "Valeria Ficticia",
          measurement_status: "due_soon",
          days_overdue: -4,
          current_phv_status: "Pre-PHV",
        }),
      ]),
      isPending: false,
      isError: false,
    } as ReturnType<typeof useAlerts>);

    renderComponent();

    const rows = screen.getAllByRole("listitem");
    expect(rows).toHaveLength(2);

    // Inicial del nombre en el círculo (aria-hidden: el nombre completo ya
    // está en el enlace de la misma fila).
    expect(rows[0].querySelector('[aria-hidden="true"]')?.textContent).toBe("S");
    expect(rows[1].querySelector('[aria-hidden="true"]')?.textContent).toBe("V");

    expect(screen.getByText("Circa-PHV · 30d de atraso")).toBeInTheDocument();
    expect(screen.getByText("Pre-PHV · Vence en 4d")).toBeInTheDocument();

    // El estado nunca se comunica sólo por color: la insignia trae texto.
    expect(screen.getByText("Vencida")).toBeInTheDocument();
    expect(screen.getByText("Próxima")).toBeInTheDocument();
  });

  it("la fila entera es el objetivo táctil, no sólo el ancho del nombre", () => {
    authState.role = "coach";
    mockUseAlerts.mockReturnValue({
      data: makeSummary([makeAlert({ athlete_id: 5, athlete_name: "Samuel Ficticio" })]),
      isPending: false,
      isError: false,
    } as ReturnType<typeof useAlerts>);

    renderComponent();

    const row = screen.getAllByRole("listitem")[0];
    const link = screen.getByRole("link", { name: "Samuel Ficticio" });

    // El ::after del enlace se estira sobre el <li> (su `relative`), así que
    // tocar el avatar, el detalle o la insignia también navega.
    expect(row.className).toMatch(/relative/);
    expect(link.className).toMatch(/after:absolute/);
    expect(link.className).toMatch(/after:inset-0/);
    // El `truncate` vive en el span interior: en el propio enlace su
    // overflow:hidden recortaría el ::after y anularía el área táctil.
    expect(link.className).not.toMatch(/truncate/);
    expect(link.querySelector("span")?.className).toMatch(/truncate/);
  });

  it("la barra de resumen usa el vocabulario de estado compartido, con texto además de color", () => {
    authState.role = "coach";
    mockUseAlerts.mockReturnValue({
      data: makeSummary([
        makeAlert({ athlete_id: 1, measurement_status: "overdue", days_overdue: 5 }),
        makeAlert({ athlete_id: 2, measurement_status: "ok", days_overdue: null }),
        makeAlert({ athlete_id: 3, measurement_status: "never", days_overdue: null }),
      ]),
      isPending: false,
      isError: false,
    } as ReturnType<typeof useAlerts>);

    renderComponent();

    expect(screen.getByText("1 vencidas")).toBeInTheDocument();
    expect(screen.getByText("1 al día")).toBeInTheDocument();
    expect(screen.getByText("1 sin medir")).toBeInTheDocument();
  });
});
