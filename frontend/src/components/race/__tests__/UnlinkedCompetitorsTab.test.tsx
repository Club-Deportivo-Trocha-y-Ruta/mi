/**
 * Tests para UnlinkedCompetitorsTab (Option A R1).
 *
 * Cubre:
 *  - Loading skeleton mientras carga
 *  - Empty state cuando no hay competitors
 *  - Render de cards con sugerencias y badges (chips de seasons, club, sex)
 *  - Click en "Enlazar" sobre sugerencia dispara mutation y muestra toast
 *  - Toast info diferenciado cuando already_linked=true
 *  - Error 409 → toast destructive con copy esperado
 *  - Confirm dialog antes de unlink + click "Sí, desvincular"
 *  - Filtros: toggle "Solo Trocha y Ruta" + select season actualizan la query
 *  - a11y básico: roles correctos, progressbar con aria-valuenow
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement, type ReactNode } from "react";

vi.mock("@/api/raceCompetitors", () => ({
  listUnlinkedCompetitors: vi.fn(),
  getCompetitorSuggestions: vi.fn(),
  linkCompetitor: vi.fn(),
  unlinkCompetitor: vi.fn(),
}));

vi.mock("@/api/athletes", () => ({
  getAthletes: vi.fn().mockResolvedValue({ items: [], total: 0 }),
  getAthlete: vi.fn(),
}));

vi.mock("@/store/auth.store", () => ({
  useAuthStore: (selector: (s: { accessToken: string }) => unknown) =>
    selector({ accessToken: "test-token" }),
}));

import * as api from "@/api/raceCompetitors";
import { UnlinkedCompetitorsTab } from "@/components/race/UnlinkedCompetitorsTab";
import type { UnlinkedCompetitorItem } from "@/types/raceCompetitors.types";

function wrap(ui: ReactNode) {
  const qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  return render(createElement(QueryClientProvider, { client: qc }, ui));
}

function makeCompetitor(
  overrides: Partial<UnlinkedCompetitorItem> = {},
): UnlinkedCompetitorItem {
  return {
    id: 1,
    display_name: "JUAN PEREZ",
    normalized_name: "juan perez",
    club_text: "Trocha y Ruta",
    sex: "M",
    results_count: 3,
    seasons: [2025, 2026],
    suggestions: [
      {
        athlete_id: 7,
        full_name: "Tomás García",
        score: 0.93,
        reason: "Match nombre 0.92 + categoría INF_A",
      },
      {
        athlete_id: 8,
        full_name: "Otro Atleta",
        score: 0.72,
        reason: "Fuzzy parcial",
      },
      {
        athlete_id: 9,
        full_name: "Tercer Match",
        score: 0.55,
        reason: "Score bajo",
      },
    ],
    ...overrides,
  };
}

beforeEach(() => vi.clearAllMocks());

describe("UnlinkedCompetitorsTab — render", () => {
  it("muestra loading skeleton mientras carga", () => {
    vi.mocked(api.listUnlinkedCompetitors).mockImplementation(
      () => new Promise(() => {}),
    );
    wrap(<UnlinkedCompetitorsTab />);
    expect(screen.getAllByTestId("competitor-skeleton").length).toBeGreaterThan(0);
  });

  it("muestra empty state cuando no hay competitors", async () => {
    vi.mocked(api.listUnlinkedCompetitors).mockResolvedValue({
      items: [],
      total: 0,
    });
    wrap(<UnlinkedCompetitorsTab />);
    await waitFor(() =>
      expect(screen.getByTestId("unlinked-empty")).toBeInTheDocument(),
    );
    // El copy aparece en el counter Y en el empty card — usamos getAllByText
    const matches = screen.getAllByText(
      /Todos los competidores están enlazados/i,
    );
    expect(matches.length).toBeGreaterThanOrEqual(1);
  });

  it("muestra el contador y renderiza una card por competitor con chips y sugerencias", async () => {
    vi.mocked(api.listUnlinkedCompetitors).mockResolvedValue({
      items: [makeCompetitor()],
      total: 1,
    });

    wrap(<UnlinkedCompetitorsTab />);

    await waitFor(() =>
      expect(screen.getByTestId("competitor-card-1")).toBeInTheDocument(),
    );

    // Contador
    expect(screen.getByTestId("unlinked-count").textContent).toMatch(/1.*pendiente/i);

    // Chips de season + club + resultados — busco dentro de la card para
    // evitar colisión con las <option> del select de filtro
    const card = screen.getByTestId("competitor-card-1");
    expect(within(card).getByText("Trocha y Ruta")).toBeInTheDocument();
    expect(within(card).getByText("2025")).toBeInTheDocument();
    expect(within(card).getByText("2026")).toBeInTheDocument();
    expect(within(card).getByText(/3 resultados/i)).toBeInTheDocument();

    // 3 sugerencias
    expect(
      screen.getByTestId("competitor-1-suggestion-0"),
    ).toBeInTheDocument();
    expect(
      screen.getByTestId("competitor-1-suggestion-1"),
    ).toBeInTheDocument();
    expect(
      screen.getByTestId("competitor-1-suggestion-2"),
    ).toBeInTheDocument();

    // Progressbar accesible (score)
    const bars = screen.getAllByRole("progressbar");
    expect(bars.length).toBeGreaterThanOrEqual(3);
    // El primero corresponde al score más alto = 93
    expect(bars[0].getAttribute("aria-valuenow")).toBe("93");
  });
});

describe("UnlinkedCompetitorsTab — link flow", () => {
  it("click en 'Enlazar' dispara linkCompetitor y muestra toast success", async () => {
    vi.mocked(api.listUnlinkedCompetitors).mockResolvedValue({
      items: [makeCompetitor()],
      total: 1,
    });
    vi.mocked(api.linkCompetitor).mockResolvedValue({
      competitor_id: 1,
      athlete_id: 7,
      linked_at: "2026-05-22T10:00:00Z",
      results_propagated: 3,
      already_linked: false,
    });

    const user = userEvent.setup();
    wrap(<UnlinkedCompetitorsTab />);

    await waitFor(() =>
      expect(screen.getByTestId("competitor-card-1")).toBeInTheDocument(),
    );

    const suggestion = screen.getByTestId("competitor-1-suggestion-0");
    const linkBtn = within(suggestion).getByTestId(
      "competitor-1-suggestion-0-link-btn",
    );
    await user.click(linkBtn);

    await waitFor(() =>
      expect(api.linkCompetitor).toHaveBeenCalledWith(1, 7),
    );

    await waitFor(() =>
      expect(screen.getByTestId("toast-success")).toBeInTheDocument(),
    );
    expect(screen.getByTestId("toast-success").textContent).toMatch(
      /3 resultados asociados a Tomás García/i,
    );
  });

  it("already_linked=true muestra toast info diferenciado", async () => {
    vi.mocked(api.listUnlinkedCompetitors).mockResolvedValue({
      items: [makeCompetitor()],
      total: 1,
    });
    vi.mocked(api.linkCompetitor).mockResolvedValue({
      competitor_id: 1,
      athlete_id: 7,
      linked_at: "2026-05-22T10:00:00Z",
      results_propagated: 0,
      already_linked: true,
    });

    const user = userEvent.setup();
    wrap(<UnlinkedCompetitorsTab />);
    await waitFor(() =>
      expect(screen.getByTestId("competitor-card-1")).toBeInTheDocument(),
    );

    await user.click(
      screen.getByTestId("competitor-1-suggestion-0-link-btn"),
    );

    await waitFor(() =>
      expect(screen.getByTestId("toast-info")).toBeInTheDocument(),
    );
    expect(screen.getByTestId("toast-info").textContent).toMatch(
      /ya estaba enlazado/i,
    );
  });

  it("error 409 muestra toast destructive con copy esperado", async () => {
    vi.mocked(api.listUnlinkedCompetitors).mockResolvedValue({
      items: [makeCompetitor()],
      total: 1,
    });
    vi.mocked(api.linkCompetitor).mockRejectedValue({
      response: { status: 409 },
    });

    const user = userEvent.setup();
    wrap(<UnlinkedCompetitorsTab />);
    await waitFor(() =>
      expect(screen.getByTestId("competitor-card-1")).toBeInTheDocument(),
    );

    await user.click(
      screen.getByTestId("competitor-1-suggestion-0-link-btn"),
    );

    await waitFor(() =>
      expect(screen.getByTestId("toast-error")).toBeInTheDocument(),
    );
    expect(screen.getByTestId("toast-error").textContent).toMatch(
      /ya está enlazado a otro atleta/i,
    );
  });

  it("error 403 muestra toast con 'sin permiso'", async () => {
    vi.mocked(api.listUnlinkedCompetitors).mockResolvedValue({
      items: [makeCompetitor()],
      total: 1,
    });
    vi.mocked(api.linkCompetitor).mockRejectedValue({
      response: { status: 403 },
    });

    const user = userEvent.setup();
    wrap(<UnlinkedCompetitorsTab />);
    await waitFor(() =>
      expect(screen.getByTestId("competitor-card-1")).toBeInTheDocument(),
    );
    await user.click(
      screen.getByTestId("competitor-1-suggestion-0-link-btn"),
    );

    await waitFor(() =>
      expect(screen.getByTestId("toast-error").textContent).toMatch(
        /sin permiso/i,
      ),
    );
  });
});

describe("UnlinkedCompetitorsTab — unlink flow", () => {
  it("abre confirm dialog y al confirmar dispara unlinkCompetitor", async () => {
    vi.mocked(api.listUnlinkedCompetitors).mockResolvedValue({
      items: [makeCompetitor({ results_count: 5 })],
      total: 1,
    });
    vi.mocked(api.unlinkCompetitor).mockResolvedValue({
      competitor_id: 1,
      was_linked: true,
      results_propagated: 5,
    });

    const user = userEvent.setup();
    wrap(<UnlinkedCompetitorsTab />);

    await waitFor(() =>
      expect(screen.getByTestId("competitor-card-1")).toBeInTheDocument(),
    );

    // Abrir menú overflow
    await user.click(screen.getByTestId("competitor-1-overflow"));
    // Click "Desvincular" en menú
    await user.click(screen.getByText("Desvincular"));

    // Dialog visible
    await waitFor(() =>
      expect(screen.getByTestId("unlink-confirm-dialog")).toBeInTheDocument(),
    );

    // Confirmar
    await user.click(screen.getByTestId("unlink-confirm-btn"));

    await waitFor(() =>
      expect(api.unlinkCompetitor).toHaveBeenCalledWith(1),
    );

    await waitFor(() =>
      expect(screen.getByTestId("toast-info").textContent).toMatch(
        /5 resultados sin atleta asociado/i,
      ),
    );
  });
});

describe("UnlinkedCompetitorsTab — filtros", () => {
  it("toggle 'Solo Trocha y Ruta' dispara refetch con club_filter undefined", async () => {
    vi.mocked(api.listUnlinkedCompetitors).mockResolvedValue({
      items: [],
      total: 0,
    });
    const user = userEvent.setup();
    wrap(<UnlinkedCompetitorsTab />);

    // Primera llamada con club_filter:'trocha' (default true)
    await waitFor(() =>
      expect(api.listUnlinkedCompetitors).toHaveBeenCalledWith(
        expect.objectContaining({ club_filter: "trocha" }),
      ),
    );

    // Desactivar toggle
    await user.click(screen.getByTestId("filter-only-trocha"));

    // Re-llama sin club_filter
    await waitFor(() => {
      const lastCall = vi.mocked(api.listUnlinkedCompetitors).mock.calls.at(-1);
      expect(lastCall?.[0]).not.toHaveProperty("club_filter");
    });
  });

  it("select de season dispara refetch con season=N", async () => {
    vi.mocked(api.listUnlinkedCompetitors).mockResolvedValue({
      items: [],
      total: 0,
    });

    const user = userEvent.setup();
    wrap(<UnlinkedCompetitorsTab />);

    await waitFor(() =>
      expect(api.listUnlinkedCompetitors).toHaveBeenCalled(),
    );

    const select = screen.getByTestId("filter-season") as HTMLSelectElement;
    // Selecciono la opción correspondiente al año actual
    const currentYear = new Date().getFullYear();
    await user.selectOptions(select, String(currentYear));

    await waitFor(() => {
      const calls = vi.mocked(api.listUnlinkedCompetitors).mock.calls;
      const matched = calls.some(([params]) =>
        (params as { season?: number })?.season === currentYear,
      );
      expect(matched).toBe(true);
    });
  });
});

describe("UnlinkedCompetitorsTab — error y callback", () => {
  it("muestra alert cuando la query falla", async () => {
    vi.mocked(api.listUnlinkedCompetitors).mockRejectedValue(new Error("boom"));
    wrap(<UnlinkedCompetitorsTab />);
    await waitFor(() =>
      expect(screen.getByTestId("unlinked-error")).toBeInTheDocument(),
    );
  });

  it("invoca onUnlinkedCountChange con el total", async () => {
    vi.mocked(api.listUnlinkedCompetitors).mockResolvedValue({
      items: [makeCompetitor()],
      total: 7,
    });
    const onChange = vi.fn();
    wrap(<UnlinkedCompetitorsTab onUnlinkedCountChange={onChange} />);
    await waitFor(() => expect(onChange).toHaveBeenCalledWith(7));
  });
});
