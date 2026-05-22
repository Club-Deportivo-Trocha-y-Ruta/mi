/**
 * Tests vitest para ComparatorPanel (FE-3).
 *
 * Cubre:
 *  - Renderiza header con select season + 2 columnas A/B con selects.
 *  - Side-by-side con deltas cuando ambos insights existen.
 *  - Empty placeholder por lado cuando una válida no tiene insight aprobado.
 *  - Cambio de validaA dispara nueva request.
 *
 * Notas:
 *  - El componente hace 4 queries (listA, listB, detailA, detailB) — usamos
 *    MSW para responder con shapes válidos en cada caso.
 *  - Para empty-per-side, devolvemos items=[] para una válida puntual.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { http, HttpResponse } from "msw";

vi.mock("@/store/auth.store", () => ({
  useAuthStore: vi.fn((sel: (s: unknown) => unknown) =>
    sel({
      accessToken: "test-token",
      user: { id: 1, role: "coach", first_name: "Coach", last_name: "Test" },
      isAuthenticated: true,
    }),
  ),
}));

import { mswServer } from "@/test/setup";
import {
  mockInsight,
  mockInsightDetail,
  mockMetricsSnapshot,
} from "@/test/msw/athleteRaceAnalysisHandlers";
import { renderWithProviders } from "@/test/helpers/renderWithProviders";
import { ComparatorPanel } from "@/components/athletes/ai/ComparatorPanel";

/** Responde lista según valida_num: devuelve un insight con id derivado
 * para que el detail handler luego retorne snapshots distintos. */
function makeListHandler(opts: {
  missingFor?: number[];
}) {
  return http.get(
    "*/api/athletes/:athleteId/race-analysis/insights",
    ({ request }) => {
      const url = new URL(request.url);
      const validaParam = url.searchParams.get("valida_num");
      const valida = validaParam !== null ? Number(validaParam) : null;
      if (valida !== null && opts.missingFor?.includes(valida)) {
        return HttpResponse.json({ items: [], total: 0, limit: 1, offset: 0 });
      }
      return HttpResponse.json({
        items: [
          mockInsight({
            id: valida === null ? 1 : valida * 10,
            valida_num: valida,
          }),
        ],
        total: 1,
        limit: 1,
        offset: 0,
      });
    },
  );
}

function makeDetailHandler(snapshotByInsightId: Record<number, ReturnType<typeof mockMetricsSnapshot>>) {
  return http.get(
    "*/api/athletes/:athleteId/race-analysis/insights/:insightId",
    ({ params }) => {
      const insightId = Number(params.insightId);
      const snapshot = snapshotByInsightId[insightId] ?? mockMetricsSnapshot();
      return HttpResponse.json(
        mockInsightDetail({
          id: insightId,
          metrics_snapshot: snapshot,
        }),
      );
    },
  );
}

describe("ComparatorPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renderiza header + select season + columnas A y B", () => {
    renderWithProviders(<ComparatorPanel athleteId={42} />);
    expect(screen.getByTestId("comparator-panel")).toBeInTheDocument();
    expect(screen.getByTestId("comparator-season-select")).toBeInTheDocument();
    expect(screen.getByTestId("comparator-col-a")).toBeInTheDocument();
    expect(screen.getByTestId("comparator-col-b")).toBeInTheDocument();
  });

  it("muestra side-by-side con métricas cuando ambos insights existen", async () => {
    mswServer.use(
      makeListHandler({}),
      makeDetailHandler({
        10: mockMetricsSnapshot({
          race_time_ms: 1_800_000,
          ranking_in_category: 3,
          podium_gap_ms: 45_000,
        }),
        20: mockMetricsSnapshot({
          race_time_ms: 1_700_000,
          ranking_in_category: 2,
          podium_gap_ms: 20_000,
        }),
      }),
    );
    renderWithProviders(<ComparatorPanel athleteId={42} />);

    await waitFor(() => {
      // Las dos columnas tienen métricas "Tiempo"
      expect(screen.getAllByText(/tiempo/i).length).toBeGreaterThan(0);
    });

    // Pos 3 (col A) y Pos 2 (col B)
    await waitFor(() => {
      expect(screen.getByText("P3")).toBeInTheDocument();
      expect(screen.getByText("P2")).toBeInTheDocument();
    });

    // Bloque delta visible
    expect(screen.getByText(/diferencia b\s*−\s*a/i)).toBeInTheDocument();
  });

  it("muestra empty placeholder en una columna cuando falta el insight", async () => {
    // Falta para valida_num=1 (col A por default).
    mswServer.use(
      makeListHandler({ missingFor: [1] }),
      makeDetailHandler({}),
    );
    renderWithProviders(<ComparatorPanel athleteId={42} />);
    await waitFor(() => {
      expect(
        screen.getByText(/sin análisis aprobado para esta válida/i),
      ).toBeInTheDocument();
    });
    // Pero la columna B sí debería mostrar contenido
    await waitFor(() => {
      const tiempoNodes = screen.getAllByText(/tiempo/i);
      expect(tiempoNodes.length).toBeGreaterThan(0);
    });
  });

  it("cambiar la válida en col A dispara nueva query con valida_num", async () => {
    const calls: string[] = [];
    mswServer.use(
      http.get(
        "*/api/athletes/:athleteId/race-analysis/insights",
        ({ request }) => {
          const url = new URL(request.url);
          calls.push(url.search);
          return HttpResponse.json({
            items: [mockInsight({ id: 1 })],
            total: 1,
            limit: 1,
            offset: 0,
          });
        },
      ),
    );

    const user = userEvent.setup();
    renderWithProviders(<ComparatorPanel athleteId={42} />);
    await waitFor(() => {
      expect(screen.getByTestId("comparator-col-a")).toBeInTheDocument();
    });

    // El select de col-A no tiene testid propio — buscamos por aria-label.
    const colASelect = screen.getByLabelText(
      /Válida A — seleccionar válida/i,
    ) as HTMLSelectElement;
    await user.selectOptions(colASelect, "5");

    await waitFor(() => {
      expect(calls.some((s) => s.includes("valida_num=5"))).toBe(true);
    });
  });

  it("no tiene violaciones a11y (estado completo con deltas)", async () => {
    mswServer.use(
      makeListHandler({}),
      makeDetailHandler({}),
    );
    const { container } = renderWithProviders(<ComparatorPanel athleteId={42} />);
    await waitFor(() => {
      expect(screen.getByText(/diferencia b\s*−\s*a/i)).toBeInTheDocument();
    });
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it("no tiene violaciones a11y (estado parcial con empty placeholder)", async () => {
    mswServer.use(
      makeListHandler({ missingFor: [1] }),
      makeDetailHandler({}),
    );
    const { container } = renderWithProviders(<ComparatorPanel athleteId={42} />);
    await waitFor(() => {
      expect(
        screen.getByText(/sin análisis aprobado para esta válida/i),
      ).toBeInTheDocument();
    });
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
