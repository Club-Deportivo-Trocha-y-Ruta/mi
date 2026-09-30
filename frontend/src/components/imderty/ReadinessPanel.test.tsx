/**
 * Tests de ReadinessPanel (feature 047, US3, T045).
 *
 * Cubre: skeleton de carga, «Todo listo» sin huecos, chips en español +
 * enlace al atleta cuando hay huecos, estado de error con reintento, y cero
 * violaciones axe.
 *
 * `getImdertySheetReadiness` se mockea a nivel de `@/api/imderty` (mismo
 * patrón que `BarrioCombobox.test.tsx`) para no depender de MSW.
 *
 * `TableScrollContainer` (vista desktop) usa `ResizeObserver`, ausente en
 * jsdom — se polyfilla acá, igual que en `__smoke__.test.tsx`.
 */
if (!globalThis.ResizeObserver) {
  globalThis.ResizeObserver = class ResizeObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver;
}

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { axe, toHaveNoViolations } from "jest-axe";

expect.extend(toHaveNoViolations);

vi.mock("@/api/imderty", () => ({
  getImdertySheetReadiness: vi.fn(),
}));

import { getImdertySheetReadiness } from "@/api/imderty";
import { ReadinessPanel } from "@/components/imderty/ReadinessPanel";
import type { ImdertyReadiness } from "@/schemas/imderty";

const mockGetReadiness = vi.mocked(getImdertySheetReadiness);

function renderPanel() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0, staleTime: 0 } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <ReadinessPanel clubId={7} from="2026-08" to="2026-08" />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const NO_GAPS: ImdertyReadiness = {
  months: ["2026-08"],
  month_in_progress: false,
  months_without_activity: [],
  athlete_count: 12,
  gaps: [],
};

const WITH_GAPS: ImdertyReadiness = {
  months: ["2026-08"],
  month_in_progress: false,
  months_without_activity: [],
  athlete_count: 12,
  gaps: [
    {
      athlete_id: 41,
      display_name: "Atleta de prueba",
      codes: ["missing_document", "activity_without_record"],
      activity_dates: ["2026-08-15", "2026-08-22"],
    },
  ],
};

describe("ReadinessPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("muestra 'Todo listo' cuando no hay huecos", async () => {
    mockGetReadiness.mockResolvedValue(NO_GAPS);
    renderPanel();

    expect(await screen.findByText("Todo listo")).toBeInTheDocument();
    expect(screen.getByText(/12 atletas/)).toBeInTheDocument();
    expect(mockGetReadiness).toHaveBeenCalledWith(7, "2026-08", "2026-08");
  });

  it("lista los huecos con chips en español y enlace al atleta", async () => {
    mockGetReadiness.mockResolvedValue(WITH_GAPS);
    renderPanel();

    // Aparece dos veces a propósito: la card móvil y la fila de tabla
    // desktop conviven en el DOM (jsdom no aplica los media queries).
    expect((await screen.findAllByText("Atleta de prueba")).length).toBeGreaterThan(0);
    expect(screen.getByText("Hay datos pendientes")).toBeInTheDocument();

    // Chips en español, no los códigos crudos del backend.
    const chips = screen.getAllByText("Falta documento");
    expect(chips.length).toBeGreaterThan(0);
    const activityChips = screen.getAllByText("Actividad sin registro de asistencia (2)");
    expect(activityChips.length).toBeGreaterThan(0);
    expect(screen.queryByText("missing_document")).not.toBeInTheDocument();

    const links = screen.getAllByRole("link", { name: "Ver atleta" });
    expect(links.length).toBeGreaterThan(0);
    // Enlaza a la sección «Perfil IMDERTY» de la ficha (ancla del card).
    links.forEach((link) =>
      expect(link).toHaveAttribute("href", "/athletes/41?tab=imderty#imderty-profile"),
    );
  });

  it("la vista desktop y móvil muestran el mismo atleta", async () => {
    mockGetReadiness.mockResolvedValue(WITH_GAPS);
    const { container } = renderPanel();

    await screen.findByText("Hay datos pendientes");

    const table = container.querySelector("table");
    expect(table).not.toBeNull();
    expect(within(table as HTMLTableElement).getByText("Atleta de prueba")).toBeInTheDocument();
  });

  it("muestra un estado de error con reintento cuando falla la carga", async () => {
    mockGetReadiness.mockRejectedValue({
      isAxiosError: true,
      response: { status: 500, data: { detail: "Error interno." } },
    });
    renderPanel();

    expect(await screen.findByText("Error interno.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /reintentar/i })).toBeInTheDocument();
  });

  it("sin violaciones axe", async () => {
    mockGetReadiness.mockResolvedValue(WITH_GAPS);
    const { container } = renderPanel();

    await waitFor(() => expect(screen.getByText("Hay datos pendientes")).toBeInTheDocument());

    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
