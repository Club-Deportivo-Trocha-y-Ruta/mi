/**
 * Tests para ImportWizard — revisión y confirmación (amendment 2026-09-26,
 * `contracts/ui-review-only.md`). La app ya no sube archivos: toda carga
 * llega ya stageada y el wizard arranca desde `?import=<id>` (T159, MSW,
 * siguiendo el patrón de `ImportWizard.resume.test.tsx`).
 *
 * Cubre:
 *  - Revisar carga: tabla matches renderiza con counts
 *  - Revisar carga: toggle "solo pendientes" filtra correctamente
 *  - Revisar carga: confirmar deshabilitado si ambiguos pendientes
 *  - Revisar carga: resolver ambiguo via combobox habilita confirmar
 *  - Revisar carga: bulk "marcar restantes sin match" (Bug #3)
 *  - Revisar carga: "Volver" navega al tablero
 *  - Resultado: success summary visible
 *  - Resultado: error con botón reintentar
 *  - Resultado: 409 identity_pending / 503 identity_rebuild_timeout
 *  - Modo revisión (F-UP-REV5): banner, warning grande, motivo, commit,
 *    resumen, botón, reset → tablero
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { http, HttpResponse } from "msw";

vi.mock("@/api/athletes", () => ({
  getAthletes: vi.fn(),
  getAthlete: vi.fn(),
}));

vi.mock("@/store/auth.store", () => ({
  useAuthStore: (selector: (s: { accessToken: string }) => unknown) =>
    selector({ accessToken: "test-token" }),
}));

import * as athletesApi from "@/api/athletes";
import { mswServer } from "@/test/setup";
import { makeImportDetail } from "@/test/msw/raceImportsHistoryHandlers";
import { ImportWizard } from "@/components/competitions/import/ImportWizard";
import type {
  DiffRow,
  ImportDryRunMatchesResponse,
  ImportDryRunResponse,
  ImportDryRunRevisionResponse,
} from "@/types/raceImports.types";
import { Sex } from "@/types/enums";

const BASE = "*/api/race-analysis/imports";

function renderAt(importId: string | number = "7") {
  const qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[`/competitions/import?import=${importId}`]}>
        <Routes>
          <Route path="/competitions/import" element={<ImportWizard />} />
          <Route
            path="/competitions/imports"
            element={<div data-testid="board-stub">Tablero</div>}
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

/** Registra el detalle + dry-run de la carga "7" y monta el wizard listo. */
function useDetailAndDryRun(
  dryRun: ImportDryRunResponse,
  detailOverrides?: Parameters<typeof makeImportDetail>[0],
) {
  mswServer.use(
    http.get(`${BASE}/7`, () =>
      HttpResponse.json(makeImportDetail({ id: 7, ...detailOverrides })),
    ),
    http.post(`${BASE}/7/dry-run`, () => HttpResponse.json(dryRun)),
  );
}

const DRY_RUN_CONFIRMED_ONLY: ImportDryRunMatchesResponse = {
  parse_id: "7",
  matches: [
    {
      competitor_normalized_name: "juan perez",
      competitor_name: "Juan Pérez",
      tyr_athlete: { id: 1, full_name: "Juan Pérez" },
      confidence: 0.95,
      is_ambiguous: false,
    },
  ],
  counts: { confirmed: 1, ambiguous: 0, no_match: 0, total: 1 },
  warnings: [],
};

const DRY_RUN_WITH_AMBIGUOUS: ImportDryRunResponse = {
  parse_id: "7",
  matches: [
    {
      competitor_normalized_name: "juan perez",
      competitor_name: "Juan Pérez",
      tyr_athlete: { id: 1, full_name: "Juan Pérez" },
      confidence: 0.95,
      is_ambiguous: false,
    },
    {
      competitor_normalized_name: "maria gonzalez",
      competitor_name: "María González",
      tyr_athlete: null,
      confidence: 0.7,
      is_ambiguous: true,
    },
  ],
  counts: { confirmed: 1, ambiguous: 1, no_match: 0, total: 2 },
  warnings: [],
};

// ---------------- F-UP-REV5 fixtures
const REVISION_DIFF_BASIC: DiffRow[] = [
  {
    action: "update",
    competitor_normalized_name: "andres mejia",
    competitor_display_name: "Andrés Mejía",
    category_code: "JUN_M",
    before: { position: 5, race_time_ms: 3012000, status: "FINISHED" },
    after: { position: 3, race_time_ms: 2948000, status: "FINISHED" },
    result_id: 100,
  },
  {
    action: "create",
    competitor_normalized_name: "maria gomez",
    competitor_display_name: "María Gómez",
    category_code: "INF_A_F",
    before: null,
    after: { position: 7, race_time_ms: 2022000, status: "FINISHED" },
    result_id: null,
  },
];

const REVISION_DIFF_WITH_DELETES: DiffRow[] = [
  ...REVISION_DIFF_BASIC,
  {
    action: "delete",
    competitor_normalized_name: "diego rojas",
    competitor_display_name: "Diego Rojas",
    category_code: "JUN_M",
    before: { position: 8, race_time_ms: 3142000, status: "FINISHED" },
    after: null,
    result_id: 234,
  },
];

const DRY_RUN_REVISION_SAFE: ImportDryRunRevisionResponse = {
  parse_id: "7",
  is_revision: true,
  parent_event_id: 4,
  diff_summary: { n_create: 1, n_update: 1, n_delete: 0, n_unchanged: 78, n_total: 80 },
  diff_rows: REVISION_DIFF_BASIC,
  warnings: [],
};

const DRY_RUN_REVISION_WITH_DELETES: ImportDryRunRevisionResponse = {
  parse_id: "7",
  is_revision: true,
  parent_event_id: 4,
  diff_summary: { n_create: 1, n_update: 1, n_delete: 1, n_unchanged: 77, n_total: 80 },
  diff_rows: REVISION_DIFF_WITH_DELETES,
  warnings: [],
};

const DRY_RUN_REVISION_LARGE: ImportDryRunRevisionResponse = {
  parse_id: "7",
  is_revision: true,
  parent_event_id: 4,
  diff_summary: { n_create: 0, n_update: 0, n_delete: 5, n_unchanged: 10, n_total: 15 },
  diff_rows: REVISION_DIFF_WITH_DELETES,
  warnings: [],
};

beforeEach(() => {
  vi.clearAllMocks();
  mswServer.use(
    http.get(`${BASE}/revision-reasons`, () =>
      HttpResponse.json({
        options: [
          { code: "official_correction", label: "Corrección oficial de la Federación" },
          { code: "timing_fix", label: "Ajuste de tiempos" },
          { code: "data_entry_error", label: "Error de digitación previo" },
        ],
      }),
    ),
  );
  vi.mocked(athletesApi.getAthletes).mockResolvedValue({
    items: [
      {
        id: 1,
        first_name: "Juan",
        last_name: "Pérez",
        sex: Sex.M,
        category: "PJUV-B-M",
        club_id: 1,
        is_active: true,
        user_id: null,
      },
      {
        id: 2,
        first_name: "María",
        last_name: "González",
        sex: Sex.F,
        category: "INF-A-F",
        club_id: 1,
        is_active: true,
        user_id: null,
      },
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
    ] as any,
    total: 2,
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
  } as any);
});

describe("ImportWizard — Revisar carga", () => {
  it("renderiza tabla de matches con counts visibles", async () => {
    useDetailAndDryRun(DRY_RUN_WITH_AMBIGUOUS);
    renderAt();

    await waitFor(() =>
      expect(screen.getByTestId("wizard-counts")).toBeInTheDocument(),
    );
    const counts = screen.getByTestId("wizard-counts");
    expect(within(counts).getByText("Confirmados")).toBeInTheDocument();
    expect(within(counts).getByText("Ambiguos")).toBeInTheDocument();
    expect(screen.getByTestId("wizard-matches-table")).toBeInTheDocument();
  });

  // Regression Bug #1: la columna "Competidor" mostraba vacío porque el
  // frontend leía `competitor_display_name` mientras el backend emite
  // `competitor_name`.
  it("muestra el nombre del competidor (competitor_name) en la columna 'Competidor'", async () => {
    useDetailAndDryRun(DRY_RUN_WITH_AMBIGUOUS);
    renderAt();

    await waitFor(() =>
      expect(screen.getByTestId("wizard-matches-table")).toBeInTheDocument(),
    );

    const ambiguousRow = screen.getByTestId("wizard-match-row-maria gonzalez");
    expect(within(ambiguousRow).getByText("María González")).toBeInTheDocument();

    const confirmedRow = screen.getByTestId("wizard-match-row-juan perez");
    expect(within(confirmedRow).getAllByText("Juan Pérez").length).toBeGreaterThan(0);
    const firstCell = confirmedRow.querySelector("td");
    expect(firstCell).not.toBeNull();
    expect(firstCell?.textContent).toContain("Juan Pérez");
  });

  it("toggle 'solo pendientes' filtra a sólo ambiguos no resueltos", async () => {
    useDetailAndDryRun(DRY_RUN_WITH_AMBIGUOUS);
    const user = userEvent.setup();
    renderAt();

    await waitFor(() =>
      expect(screen.getByTestId("wizard-matches-table")).toBeInTheDocument(),
    );
    expect(screen.getByTestId("wizard-match-row-juan perez")).toBeInTheDocument();
    expect(screen.getByTestId("wizard-match-row-maria gonzalez")).toBeInTheDocument();

    await user.click(screen.getByTestId("wizard-toggle-pending"));

    expect(screen.queryByTestId("wizard-match-row-juan perez")).not.toBeInTheDocument();
    expect(screen.getByTestId("wizard-match-row-maria gonzalez")).toBeInTheDocument();
  });

  it("confirmar está deshabilitado mientras quedan ambiguos pendientes", async () => {
    useDetailAndDryRun(DRY_RUN_WITH_AMBIGUOUS);
    renderAt();

    await waitFor(() =>
      expect(screen.getByTestId("wizard-step2-confirm")).toBeInTheDocument(),
    );
    expect(screen.getByTestId("wizard-step2-confirm")).toBeDisabled();
    expect(screen.getByTestId("wizard-pending-hint")).toHaveTextContent(/matches ambiguos/i);
  });

  it("botón volver navega al tablero de cargas", async () => {
    useDetailAndDryRun(DRY_RUN_CONFIRMED_ONLY);
    const user = userEvent.setup();
    renderAt();

    await waitFor(() =>
      expect(screen.getByTestId("wizard-step2-confirm")).toBeEnabled(),
    );
    await user.click(screen.getByTestId("wizard-step2-back"));
    expect(await screen.findByTestId("board-stub")).toBeInTheDocument();
  });

  it("bulk 'Marcar restantes como sin match' habilita el botón de confirmar (Bug #3)", async () => {
    useDetailAndDryRun(DRY_RUN_WITH_AMBIGUOUS);
    const user = userEvent.setup();
    renderAt();

    await waitFor(() =>
      expect(screen.getByTestId("wizard-step2-confirm")).toBeInTheDocument(),
    );
    expect(screen.getByTestId("wizard-step2-confirm")).toBeDisabled();

    const bulkBtn = screen.getByTestId("wizard-mark-rest-no-match");
    expect(bulkBtn).toBeEnabled();
    await user.click(bulkBtn);

    expect(screen.getByTestId("wizard-step2-confirm")).toBeEnabled();
    expect(screen.queryByTestId("wizard-pending-hint")).not.toBeInTheDocument();
    expect(screen.getByTestId("wizard-mark-rest-no-match")).toBeDisabled();
  });

  it("bulk 'Marcar restantes' NO sobrescribe matches confirmados (Bug #3)", async () => {
    useDetailAndDryRun(DRY_RUN_WITH_AMBIGUOUS);
    let commitBody: unknown;
    mswServer.use(
      http.post(`${BASE}/7/commit`, async ({ request }) => {
        commitBody = await request.json();
        return HttpResponse.json({
          parse_id: "7",
          race_event_id: 4,
          n_results_inserted: 2,
          n_competitors_created: 1,
          n_competitors_linked: 1,
        });
      }),
    );
    const user = userEvent.setup();
    renderAt();

    await waitFor(() =>
      expect(screen.getByTestId("wizard-mark-rest-no-match")).toBeInTheDocument(),
    );
    await user.click(screen.getByTestId("wizard-mark-rest-no-match"));

    await waitFor(() =>
      expect(screen.getByTestId("wizard-step2-confirm")).toBeEnabled(),
    );
    await user.click(screen.getByTestId("wizard-step2-confirm"));

    await waitFor(() => expect(commitBody).toBeDefined());
    const byName: Record<string, number | null> = {};
    for (const rm of (commitBody as { resolved_matches: { competitor_normalized_name: string; athlete_id: number | null }[] }).resolved_matches) {
      byName[rm.competitor_normalized_name] = rm.athlete_id;
    }
    expect(byName["juan perez"]).toBe(1);
    expect(byName["maria gonzalez"]).toBeNull();
  });
});

describe("ImportWizard — Resultado", () => {
  it("success: muestra summary y link a los resultados de la válida", async () => {
    useDetailAndDryRun(DRY_RUN_CONFIRMED_ONLY);
    mswServer.use(
      http.post(`${BASE}/7/commit`, () =>
        HttpResponse.json({
          parse_id: "7",
          race_event_id: 4,
          n_results_inserted: 200,
          n_competitors_created: 198,
          n_competitors_linked: 3,
        }),
      ),
    );
    const user = userEvent.setup();
    renderAt();

    await waitFor(() =>
      expect(screen.getByTestId("wizard-step2-confirm")).toBeEnabled(),
    );
    await user.click(screen.getByTestId("wizard-step2-confirm"));

    await waitFor(() =>
      expect(screen.getByTestId("wizard-step3-success")).toBeInTheDocument(),
    );
    expect(screen.getByTestId("wizard-step3-success")).toHaveTextContent(/200/);
    expect(screen.getByTestId("wizard-step3-link-analysis")).toHaveAttribute(
      "href",
      "/competitions/4?tab=results",
    );
  });

  it("'Cargar otro' navega al tablero de cargas", async () => {
    useDetailAndDryRun(DRY_RUN_CONFIRMED_ONLY);
    mswServer.use(
      http.post(`${BASE}/7/commit`, () =>
        HttpResponse.json({
          parse_id: "7",
          race_event_id: 4,
          n_results_inserted: 200,
          n_competitors_created: 198,
          n_competitors_linked: 3,
        }),
      ),
    );
    const user = userEvent.setup();
    renderAt();

    await waitFor(() =>
      expect(screen.getByTestId("wizard-step2-confirm")).toBeEnabled(),
    );
    await user.click(screen.getByTestId("wizard-step2-confirm"));

    await waitFor(() =>
      expect(screen.getByTestId("wizard-step3-success")).toBeInTheDocument(),
    );
    await userEvent.setup().click(screen.getByTestId("wizard-step3-new"));
    expect(await screen.findByTestId("board-stub")).toBeInTheDocument();
  });

  it("error commit: muestra botón reintentar y vuelve al paso de revisión", async () => {
    useDetailAndDryRun(DRY_RUN_CONFIRMED_ONLY);
    mswServer.use(
      http.post(`${BASE}/7/commit`, () =>
        HttpResponse.json({ detail: "Boom commit" }, { status: 500 }),
      ),
    );
    const user = userEvent.setup();
    renderAt();

    await waitFor(() =>
      expect(screen.getByTestId("wizard-step2-confirm")).toBeEnabled(),
    );
    await user.click(screen.getByTestId("wizard-step2-confirm"));

    await waitFor(() =>
      expect(screen.getByTestId("wizard-step3-error")).toBeInTheDocument(),
    );
    expect(screen.getByTestId("wizard-step3-error")).toHaveTextContent(/Boom commit/);

    await user.click(screen.getByTestId("wizard-step3-retry"));
    expect(screen.getByTestId("import-wizard-step2")).toBeInTheDocument();
  });

  it("commit bloqueado por identidad pendiente (409 identity_pending, cuerpo plano): muestra el copy con el conteo de ESTA carga y un link a review_path", async () => {
    useDetailAndDryRun(DRY_RUN_CONFIRMED_ONLY);
    mswServer.use(
      http.post(`${BASE}/7/commit`, () =>
        HttpResponse.json(
          {
            detail: "identity_pending",
            pending_for_import: 3,
            review_path: "/competitions/imports?seccion=identidades&import=7",
          },
          { status: 409 },
        ),
      ),
    );
    const user = userEvent.setup();
    renderAt();

    await waitFor(() =>
      expect(screen.getByTestId("wizard-step2-confirm")).toBeEnabled(),
    );
    await user.click(screen.getByTestId("wizard-step2-confirm"));

    await waitFor(() =>
      expect(screen.getByTestId("wizard-step3-error")).toBeInTheDocument(),
    );
    expect(screen.getByTestId("wizard-step3-error")).toHaveTextContent(
      "Hay 3 decisiones de identidad pendientes para esta carga. Resuélvelas en «Cargas e identidades» y vuelve: tu carga queda guardada.",
    );
    const link = screen.getByTestId("wizard-identity-review-link");
    expect(link).toHaveAttribute(
      "href",
      "/competitions/imports?seccion=identidades&import=7",
    );
  });

  it("commit bloqueado por timeout de recálculo (503 identity_rebuild_timeout): muestra el mensaje amigable del backend, sin link", async () => {
    useDetailAndDryRun(DRY_RUN_CONFIRMED_ONLY);
    mswServer.use(
      http.post(`${BASE}/7/commit`, () =>
        HttpResponse.json(
          {
            detail: {
              code: "identity_rebuild_timeout",
              message:
                "El recálculo de identidad tardó demasiado antes del commit. Intenta de nuevo en unos minutos.",
            },
          },
          { status: 503 },
        ),
      ),
    );
    const user = userEvent.setup();
    renderAt();

    await waitFor(() =>
      expect(screen.getByTestId("wizard-step2-confirm")).toBeEnabled(),
    );
    await user.click(screen.getByTestId("wizard-step2-confirm"));

    await waitFor(() =>
      expect(screen.getByTestId("wizard-step3-error")).toBeInTheDocument(),
    );
    expect(screen.getByTestId("wizard-step3-error")).toHaveTextContent(
      /El recálculo de identidad tardó demasiado/,
    );
    expect(screen.queryByTestId("wizard-identity-review-link")).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// F-UP-REV5 — Modo revisión
// ---------------------------------------------------------------------------

describe("ImportWizard — Revision mode (F-UP-REV5)", () => {
  async function gotoRevision(dryRun: ImportDryRunRevisionResponse) {
    useDetailAndDryRun(dryRun);
    renderAt();
    await waitFor(() =>
      expect(screen.getByTestId("wizard-revision-mode")).toBeInTheDocument(),
    );
  }

  it("detecta is_revision=true en dry-run → renderiza DiffTable en lugar de matches", async () => {
    await gotoRevision(DRY_RUN_REVISION_SAFE);

    expect(await screen.findByTestId("diff-table")).toBeInTheDocument();
    expect(screen.queryByTestId("wizard-matches-table")).not.toBeInTheDocument();
    expect(screen.queryByTestId("wizard-counts")).not.toBeInTheDocument();
    expect(await screen.findByText("Andrés Mejía")).toBeInTheDocument();
  });

  it("banner amarillo de revisión visible con metadata del padre", async () => {
    await gotoRevision(DRY_RUN_REVISION_SAFE);

    const banner = screen.getByTestId("wizard-revision-banner");
    expect(banner).toHaveTextContent(/Revisión detectada/i);
    expect(banner).toHaveTextContent("1");
    expect(banner).toHaveTextContent("80");
    expect(banner).toHaveTextContent(/Válida/);
  });

  it("banner naranja warning cuando deletes > 20% de unchanged", async () => {
    await gotoRevision(DRY_RUN_REVISION_LARGE);

    expect(screen.getByTestId("wizard-revision-warning-large")).toHaveTextContent(
      /inusualmente grandes/i,
    );
  });

  it("revision_reason obligatorio si n_delete > 0 (botón disabled hasta llenar)", async () => {
    const user = userEvent.setup();
    await gotoRevision(DRY_RUN_REVISION_WITH_DELETES);

    const confirm = screen.getByTestId("wizard-step2-confirm");
    const select = screen.getByTestId("wizard-revision-reason");

    expect(confirm).toBeDisabled();
    expect(select).toHaveAttribute("aria-required", "true");

    await user.selectOptions(select, "official_correction");
    expect(confirm).toBeEnabled();
  });

  it("revision_reason opcional si solo creates/updates (botón enabled sin texto)", async () => {
    await gotoRevision(DRY_RUN_REVISION_SAFE);

    const confirm = screen.getByTestId("wizard-step2-confirm");
    const select = screen.getByTestId("wizard-revision-reason");

    expect(select).not.toHaveAttribute("aria-required", "true");
    expect(confirm).toBeEnabled();
  });

  it("commit envía revision_reason en payload + resultado muestra summary revisión", async () => {
    let commitBody: unknown;
    mswServer.use(
      http.post(`${BASE}/7/commit`, async ({ request }) => {
        commitBody = await request.json();
        return HttpResponse.json({
          parse_id: "7",
          race_event_id: 4,
          n_results_inserted: 0,
          n_competitors_created: 0,
          n_competitors_linked: 0,
        });
      }),
    );
    const user = userEvent.setup();
    await gotoRevision(DRY_RUN_REVISION_WITH_DELETES);

    const select = screen.getByTestId("wizard-revision-reason");
    await user.selectOptions(select, "official_correction");
    await user.click(screen.getByTestId("wizard-step2-confirm"));

    await waitFor(() =>
      expect(screen.getByTestId("wizard-step3-success")).toBeInTheDocument(),
    );

    expect(commitBody).toEqual({
      resolved_matches: [],
      revision_reason: "official_correction",
    });

    expect(screen.getByTestId("wizard-step3-revision-summary")).toHaveTextContent(
      /1.*actualizaciones/,
    );
    expect(screen.getByTestId("wizard-step3-revision-summary")).toHaveTextContent(
      /1.*eliminaciones/,
    );
    expect(screen.getByText(/Revisión aplicada/)).toBeInTheDocument();
  });

  it("texto del botón en modo revisión es 'Confirmar y aplicar revisión'", async () => {
    await gotoRevision(DRY_RUN_REVISION_SAFE);
    expect(screen.getByTestId("wizard-step2-confirm")).toHaveTextContent(/aplicar revisión/i);
  });

  it("'Cargar otro' desde el resultado de una revisión navega al tablero", async () => {
    mswServer.use(
      http.post(`${BASE}/7/commit`, () =>
        HttpResponse.json({
          parse_id: "7",
          race_event_id: 4,
          n_results_inserted: 0,
          n_competitors_created: 0,
          n_competitors_linked: 0,
        }),
      ),
    );
    const user = userEvent.setup();
    await gotoRevision(DRY_RUN_REVISION_WITH_DELETES);

    await user.selectOptions(
      screen.getByTestId("wizard-revision-reason"),
      "official_correction",
    );
    await user.click(screen.getByTestId("wizard-step2-confirm"));

    await waitFor(() =>
      expect(screen.getByTestId("wizard-step3-success")).toBeInTheDocument(),
    );
    await user.click(screen.getByTestId("wizard-step3-new"));
    expect(await screen.findByTestId("board-stub")).toBeInTheDocument();
  });
});
