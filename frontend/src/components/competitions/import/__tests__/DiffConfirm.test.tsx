/**
 * DiffConfirm — pruebas de integración del flujo de confirmación de diff (US4).
 * Amendment 2026-09-26 (T159): arranca desde `?import=<id>` con MSW en vez
 * de llenar el paso 1 (retirado), a través de la forma real de dry-run de
 * revisión (`contracts/ui-review-only.md`).
 *
 * Verifica que:
 *  1. El diff agrupa los cambios por tipo de acción (create/update/delete/unchanged).
 *  2. El botón "Confirmar y aplicar revisión" queda deshabilitado si hay
 *     deletes y no se ha elegido un motivo del catálogo cerrado.
 *  3. Al confirmar con motivo elegido, el commit se ejecuta con el payload
 *     correcto (FR-016: motivo obligatorio con deletes).
 *  4. Un diff que NO tiene deletes permite confirmar sin elegir motivo.
 *  5. jest-axe: el paso de revisión en modo revisión no tiene violaciones.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { http, HttpResponse } from "msw";
import { axe, toHaveNoViolations } from "jest-axe";

expect.extend(toHaveNoViolations);

vi.mock("@/store/auth.store", () => ({
  useAuthStore: (selector: (s: { accessToken: string }) => unknown) =>
    selector({ accessToken: "test-token" }),
}));

import { mswServer } from "@/test/setup";
import { makeImportDetail } from "@/test/msw/raceImportsHistoryHandlers";
import { ImportWizard } from "@/components/competitions/import/ImportWizard";
import type { DiffRow, ImportDryRunRevisionResponse } from "@/types/raceImports.types";

const BASE = "*/api/race-analysis/imports";

function renderAt() {
  const qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/competitions/import?import=7"]}>
        <Routes>
          <Route path="/competitions/import" element={<ImportWizard />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

// Diff con los cuatro tipos de cambio (grouped por action)
const DIFF_ROWS_ALL_TYPES: DiffRow[] = [
  {
    action: "create",
    competitor_normalized_name: "sofia rueda",
    competitor_display_name: "Sofía Rueda",
    category_code: "INF_A_F",
    before: null,
    after: { position: 5, race_time_ms: 1800000, status: "FINISHED" },
    result_id: null,
  },
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
    action: "delete",
    competitor_normalized_name: "diego rojas",
    competitor_display_name: "Diego Rojas",
    category_code: "JUN_M",
    before: { position: 8, race_time_ms: 3142000, status: "FINISHED" },
    after: null,
    result_id: 234,
  },
  {
    action: "unchanged",
    competitor_normalized_name: "juan perez",
    competitor_display_name: "Juan Pérez",
    category_code: "INF_A_M",
    before: { position: 4, race_time_ms: 2500000, status: "FINISHED" },
    after: { position: 4, race_time_ms: 2500000, status: "FINISHED" },
    result_id: 100,
  },
];

const DRY_RUN_WITH_DELETES: ImportDryRunRevisionResponse = {
  parse_id: "7",
  is_revision: true,
  parent_event_id: 4,
  diff_summary: { n_create: 1, n_update: 1, n_delete: 1, n_unchanged: 77, n_total: 80 },
  diff_rows: DIFF_ROWS_ALL_TYPES,
  warnings: [],
};

const DRY_RUN_NO_DELETES: ImportDryRunRevisionResponse = {
  parse_id: "7",
  is_revision: true,
  parent_event_id: 4,
  diff_summary: { n_create: 1, n_update: 1, n_delete: 0, n_unchanged: 78, n_total: 80 },
  diff_rows: DIFF_ROWS_ALL_TYPES.filter((r) => r.action !== "delete"),
  warnings: [],
};

async function renderAndGoToRevision(dryRun: ImportDryRunRevisionResponse) {
  mswServer.use(
    http.get(`${BASE}/7`, () => HttpResponse.json(makeImportDetail({ id: 7 }))),
    http.post(`${BASE}/7/dry-run`, () => HttpResponse.json(dryRun)),
    http.get(`${BASE}/revision-reasons`, () =>
      HttpResponse.json({
        options: [
          { code: "official_correction", label: "Corrección oficial de la Federación" },
          { code: "timing_fix", label: "Ajuste de tiempos" },
        ],
      }),
    ),
  );

  const user = userEvent.setup();
  renderAt();

  await waitFor(() =>
    expect(screen.getByTestId("wizard-revision-mode")).toBeInTheDocument(),
  );

  return user;
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("Diff-confirm flow (US4 / FR-014…017)", () => {
  it("renderiza los cuatro tipos de cambio como badges en el DiffTable", async () => {
    await renderAndGoToRevision(DRY_RUN_WITH_DELETES);

    const diffTable = await screen.findByTestId("diff-table");
    expect(diffTable).toBeInTheDocument();

    expect(within(diffTable).getByTestId("diff-badge-create")).toBeInTheDocument();
    expect(within(diffTable).getByTestId("diff-badge-update")).toBeInTheDocument();
    expect(within(diffTable).getByTestId("diff-badge-delete")).toBeInTheDocument();
    expect(within(diffTable).getByTestId("diff-badge-unchanged")).toBeInTheDocument();
  });

  it("muestra los nombres de los competidores en las filas del diff", async () => {
    await renderAndGoToRevision(DRY_RUN_WITH_DELETES);

    const diffTable = await screen.findByTestId("diff-table");
    expect(within(diffTable).getByText("Sofía Rueda")).toBeInTheDocument();
    expect(within(diffTable).getByText("Andrés Mejía")).toBeInTheDocument();
    expect(within(diffTable).getByText("Diego Rojas")).toBeInTheDocument();
    expect(within(diffTable).getByText("Juan Pérez")).toBeInTheDocument();
  });

  it("requiere confirmar explícitamente: botón deshabilitado con deletes sin motivo", async () => {
    await renderAndGoToRevision(DRY_RUN_WITH_DELETES);

    await screen.findByTestId("diff-table");
    expect(screen.getByTestId("wizard-step2-confirm")).toBeDisabled();
  });

  it("permite confirmar una vez seleccionado el motivo del catálogo cerrado", async () => {
    const user = await renderAndGoToRevision(DRY_RUN_WITH_DELETES);

    await screen.findByTestId("diff-table");
    const confirm = screen.getByTestId("wizard-step2-confirm");
    const select = screen.getByTestId("wizard-revision-reason");

    expect(confirm).toBeDisabled();
    await user.selectOptions(select, "official_correction");
    expect(confirm).toBeEnabled();
  });

  it("sin deletes el commit no requiere motivo (botón habilitado desde el inicio)", async () => {
    await renderAndGoToRevision(DRY_RUN_NO_DELETES);

    await screen.findByTestId("diff-table");
    expect(screen.getByTestId("wizard-revision-reason")).not.toHaveAttribute(
      "aria-required",
      "true",
    );
    expect(screen.getByTestId("wizard-step2-confirm")).toBeEnabled();
  });

  it("commit envía el código del motivo (no texto libre) en el payload", async () => {
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

    const user = await renderAndGoToRevision(DRY_RUN_WITH_DELETES);
    await screen.findByTestId("diff-table");

    await user.selectOptions(screen.getByTestId("wizard-revision-reason"), "timing_fix");
    await user.click(screen.getByTestId("wizard-step2-confirm"));

    await waitFor(() => expect(commitBody).toBeDefined());
    // El payload debe contener el CODE del catálogo, NO texto libre (PR4).
    expect(commitBody).toEqual({
      resolved_matches: [],
      revision_reason: "timing_fix",
    });
  });

  it("el filtro 'solo cambios' oculta las filas sin cambios por defecto cuando hay >20 unchanged", async () => {
    const manyUnchanged: DiffRow[] = [];
    for (let i = 0; i < 25; i++) {
      manyUnchanged.push({
        action: "unchanged",
        competitor_normalized_name: `comp-sin-cambio-${i}`,
        competitor_display_name: `Corredor ${i}`,
        category_code: "INF_A_M",
        before: { position: i + 1, race_time_ms: 1000 * i, status: "FINISHED" },
        after: { position: i + 1, race_time_ms: 1000 * i, status: "FINISHED" },
        result_id: 500 + i,
      });
    }
    const dryRunManyUnchanged: ImportDryRunRevisionResponse = {
      parse_id: "7",
      is_revision: true,
      parent_event_id: 4,
      diff_summary: { n_create: 1, n_update: 1, n_delete: 1, n_unchanged: 25, n_total: 28 },
      diff_rows: [
        {
          action: "update",
          competitor_normalized_name: "c-updated",
          competitor_display_name: "Competidor Actualizado",
          category_code: "JUN_M",
          before: { position: 3 },
          after: { position: 2 },
          result_id: 999,
        },
        ...manyUnchanged,
      ],
      warnings: [],
    };

    await renderAndGoToRevision(dryRunManyUnchanged);
    const diffTable = await screen.findByTestId("diff-table");

    const toggle = within(diffTable).getByTestId("diff-toggle-only-changes") as HTMLInputElement;
    expect(toggle.checked).toBe(true);

    expect(within(diffTable).getByText("Competidor Actualizado")).toBeInTheDocument();
    expect(within(diffTable).queryByText("Corredor 0")).not.toBeInTheDocument();
  });

  it("jest-axe: modo revisión sin violaciones de accesibilidad", async () => {
    await renderAndGoToRevision(DRY_RUN_WITH_DELETES);
    await screen.findByTestId("diff-table");

    const container = screen.getByTestId("import-wizard").closest("section") as HTMLElement;
    const results = await axe(container ?? document.body);
    expect(results).toHaveNoViolations();
  });
});
