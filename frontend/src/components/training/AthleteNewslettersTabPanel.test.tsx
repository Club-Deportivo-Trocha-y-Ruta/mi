/**
 * Tests para AthleteNewslettersTabPanel.
 *
 * Cubre: render lista, estado vacío, RBAC (parent no ve el panel por control
 * en AthleteDetailPage — aquí validamos que el panel renderiza correctamente
 * para coach), navegación "Ver detalle →", paginación "Ver más".
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { axe } from "jest-axe";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock("@/api/athleteNewsletters", () => ({
  useAthleteNewsletters: vi.fn(),
}));

vi.mock("@/store/auth.store", () => ({
  useAuthStore: vi.fn((sel: (s: unknown) => unknown) =>
    sel({
      accessToken: "tok",
      user: { role: "coach", id: 10 },
    }),
  ),
}));

import { useAthleteNewsletters } from "@/api/athleteNewsletters";
import { makeNewsletter } from "@/test/msw/newsletterHandlers";
import { AthleteNewslettersTabPanel } from "./AthleteNewslettersTabPanel";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function renderPanel(athleteId = 1) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <AthleteNewslettersTabPanel athleteId={athleteId} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function mockQuery(
  overrides: Partial<ReturnType<typeof useAthleteNewsletters>> = {},
) {
  vi.mocked(useAthleteNewsletters).mockReturnValue({
    isLoading: false,
    isError: false,
    data: [],
    ...overrides,
  } as unknown as ReturnType<typeof useAthleteNewsletters>);
}

beforeEach(() => {
  vi.clearAllMocks();
});

// ---------------------------------------------------------------------------
// Estado vacío
// ---------------------------------------------------------------------------

describe("AthleteNewslettersTabPanel — estado vacío", () => {
  it("muestra empty state cuando no hay boletines", () => {
    mockQuery({ data: [] });
    renderPanel();
    expect(screen.getByTestId("newsletters-empty-state")).toBeInTheDocument();
    expect(
      screen.getByText(/Aun no hay boletines para este atleta/i),
    ).toBeInTheDocument();
  });

  it("muestra CTA 'Generar boletin de este mes' para coach", () => {
    mockQuery({ data: [] });
    renderPanel();
    expect(screen.getByTestId("generate-newsletter-cta")).toBeInTheDocument();
  });

  it("muestra link 'Ir al dashboard de boletines'", () => {
    mockQuery({ data: [] });
    renderPanel();
    const link = screen.getByTestId("dashboard-newsletters-link");
    expect(link).toBeInTheDocument();
    expect(link).toHaveAttribute("href", "/training/athlete-newsletters");
  });
});

// ---------------------------------------------------------------------------
// Lista de boletines
// ---------------------------------------------------------------------------

describe("AthleteNewslettersTabPanel — lista", () => {
  const newsletters = [
    makeNewsletter({ id: 1, year: 2026, month: 5, status: "sent" }),
    makeNewsletter({ id: 2, year: 2026, month: 4, status: "approved" }),
    makeNewsletter({ id: 3, year: 2026, month: 3, status: "draft" }),
    makeNewsletter({ id: 4, year: 2025, month: 12, status: "failed" }),
  ];

  it("renderiza el panel cuando hay boletines", () => {
    mockQuery({ data: newsletters });
    renderPanel();
    expect(screen.getByTestId("newsletters-tab-panel")).toBeInTheDocument();
  });

  it("muestra 'Mayo 2026' para mes 5 año 2026", () => {
    mockQuery({ data: newsletters });
    renderPanel();
    expect(screen.getAllByText(/Mayo 2026/i).length).toBeGreaterThan(0);
  });

  it("muestra chip de estado 'Enviado' para newsletter sent", () => {
    mockQuery({ data: newsletters });
    renderPanel();
    expect(screen.getAllByText("Enviado").length).toBeGreaterThan(0);
  });

  it("muestra chip de estado 'Aprobado' para newsletter approved", () => {
    mockQuery({ data: newsletters });
    renderPanel();
    expect(screen.getAllByText("Aprobado").length).toBeGreaterThan(0);
  });

  it("muestra chip de estado 'Borrador' para newsletter draft", () => {
    mockQuery({ data: newsletters });
    renderPanel();
    expect(screen.getAllByText("Borrador").length).toBeGreaterThan(0);
  });

  it("muestra chip de estado 'Falló' para newsletter failed", () => {
    mockQuery({ data: newsletters });
    renderPanel();
    expect(screen.getAllByText("Falló").length).toBeGreaterThan(0);
  });

  it("el link 'Ver detalle' navega a la URL correcta", () => {
    mockQuery({ data: [makeNewsletter({ id: 7, athlete_id: 1 })] });
    renderPanel(1);
    const link = screen.getByTestId("newsletter-detail-link-7");
    expect(link).toHaveAttribute(
      "href",
      "/training/athlete-newsletters/1/7",
    );
  });
});

// ---------------------------------------------------------------------------
// Ordenamiento
// ---------------------------------------------------------------------------

describe("AthleteNewslettersTabPanel — ordenamiento", () => {
  it("ordena de más reciente a más antiguo (año desc, mes desc)", () => {
    const newsletters = [
      makeNewsletter({ id: 10, year: 2025, month: 3, status: "sent" }),
      makeNewsletter({ id: 11, year: 2026, month: 1, status: "draft" }),
      makeNewsletter({ id: 12, year: 2026, month: 5, status: "approved" }),
    ];
    mockQuery({ data: newsletters });
    renderPanel();

    // En la tabla desktop los meses aparecen en orden
    const rows = screen.getAllByTestId(/newsletter-row-/);
    // Primer row: Mayo 2026 (id 12)
    expect(rows[0]).toHaveAttribute("data-testid", "newsletter-row-12");
    // Segundo: Enero 2026 (id 11)
    expect(rows[1]).toHaveAttribute("data-testid", "newsletter-row-11");
    // Tercero: Marzo 2025 (id 10)
    expect(rows[2]).toHaveAttribute("data-testid", "newsletter-row-10");
  });
});

// ---------------------------------------------------------------------------
// Paginación
// ---------------------------------------------------------------------------

describe("AthleteNewslettersTabPanel — paginación", () => {
  it("NO muestra 'Ver más' si hay 12 o menos boletines", () => {
    const newsletters = Array.from({ length: 12 }, (_, i) =>
      makeNewsletter({ id: i + 1, year: 2026, month: i + 1, status: "draft" }),
    );
    mockQuery({ data: newsletters });
    renderPanel();
    expect(screen.queryByTestId("ver-mas-btn")).not.toBeInTheDocument();
  });

  it("muestra 'Ver más' si hay más de 12 boletines", () => {
    const newsletters = Array.from({ length: 13 }, (_, i) =>
      makeNewsletter({ id: i + 1, year: 2026, month: (i % 12) + 1, status: "draft" }),
    );
    mockQuery({ data: newsletters });
    renderPanel();
    expect(screen.getByTestId("ver-mas-btn")).toBeInTheDocument();
  });

  it("'Ver más' carga el siguiente lote al hacer click", async () => {
    const user = userEvent.setup();
    const newsletters = Array.from({ length: 14 }, (_, i) =>
      makeNewsletter({ id: i + 1, year: 2026 - Math.floor(i / 12), month: (i % 12) + 1, status: "draft" }),
    );
    mockQuery({ data: newsletters });
    renderPanel();

    // Solo se ven 12 inicialmente en la tabla
    expect(screen.getAllByTestId(/newsletter-row-/).length).toBe(12);

    await user.click(screen.getByTestId("ver-mas-btn"));

    // Ahora se ven los 14
    expect(screen.getAllByTestId(/newsletter-row-/).length).toBe(14);
    expect(screen.queryByTestId("ver-mas-btn")).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Estados de carga / error
// ---------------------------------------------------------------------------

describe("AthleteNewslettersTabPanel — estados de carga y error", () => {
  it("muestra skeleton mientras carga", () => {
    mockQuery({ isLoading: true, data: undefined });
    renderPanel();
    expect(screen.getByTestId("newsletters-skeleton")).toBeInTheDocument();
  });

  it("muestra mensaje de error cuando falla la query", () => {
    mockQuery({ isError: true, data: undefined });
    renderPanel();
    expect(screen.getByTestId("newsletters-error")).toBeInTheDocument();
    expect(
      screen.getByText(/Error al cargar los boletines/i),
    ).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Accesibilidad
// ---------------------------------------------------------------------------

describe("AthleteNewslettersTabPanel — a11y", () => {
  it("no tiene violaciones a11y en estado vacío", async () => {
    mockQuery({ data: [] });
    const { container } = renderPanel();
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it("no tiene violaciones a11y con lista de boletines", async () => {
    mockQuery({
      data: [
        makeNewsletter({ id: 1, status: "sent" }),
        makeNewsletter({ id: 2, status: "draft" }),
      ],
    });
    const { container } = renderPanel();
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
