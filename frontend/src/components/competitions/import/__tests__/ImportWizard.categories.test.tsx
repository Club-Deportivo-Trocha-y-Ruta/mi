/**
 * ImportWizard — integración con la integridad de lectura del acta
 * (feature 044, US1 + US2). Amendment 2026-09-26 (T159): la app ya no sube
 * archivos, así que el wizard arranca desde `?import=<id>` con MSW,
 * siguiendo el patrón de `ImportWizard.resume.test.tsx`.
 *
 * Cubre los estados del wizard alrededor de `CategoryMappingTable`:
 *  - `parseResult.categories` se monta en el paso de revisión con el aviso
 *    de filas ilegibles.
 *  - El botón de confirmar muestra "Confirmar categorías completas (N de
 *    M)" cuando el parse trae categorías, y conserva "Confirmar carga"
 *    cuando no las trae.
 *  - Corregir la fila faltante desde el wizard actualiza el conteo N de M
 *    del botón sin bloquear la confirmación.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { http, HttpResponse } from "msw";

vi.mock("@/store/auth.store", () => ({
  useAuthStore: (selector: (s: { accessToken: string }) => unknown) =>
    selector({ accessToken: "test-token" }),
}));

import { mswServer } from "@/test/setup";
import { makeImportDetail } from "@/test/msw/raceImportsHistoryHandlers";
import { ImportWizard } from "@/components/competitions/import/ImportWizard";
import type {
  ImportDryRunMatchesResponse,
  ImportParseMeta,
} from "@/types/raceImports.types";

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
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
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

const META_NO_CATEGORIES: ImportParseMeta = {
  header: {
    series_name: "Copa Valle",
    season: 2026,
    valida_num: 4,
    event_name: "IV — Cali",
  },
  n_rows_resultados: 200,
  n_rows_general: 0,
};

const META_WITH_CATEGORIES: ImportParseMeta = {
  ...META_NO_CATEGORIES,
  categories: [
    {
      header_raw: "PREJUVENIL A DAMAS",
      code: "PREJ_A_F",
      mapping_kind: "exact",
      rows: 1,
      completeness: { status: "ok", missing: [], duplicated: [] },
    },
    {
      header_raw: "INFANTIL A DAMAS",
      code: "INF_A_F",
      mapping_kind: "rename",
      rows: 2,
      completeness: { status: "inconsistent", missing: [3], duplicated: [] },
    },
  ],
  unreadable_rows: [{ page: 5, ordinal: null }],
};

function useDetailAndDryRun(meta: ImportParseMeta) {
  mswServer.use(
    http.get(`${BASE}/7`, () =>
      HttpResponse.json(makeImportDetail({ id: 7, parse_meta: meta })),
    ),
    http.post(`${BASE}/7/dry-run`, () =>
      HttpResponse.json(DRY_RUN_CONFIRMED_ONLY),
    ),
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("ImportWizard — categorías (feature 044)", () => {
  it("sin categorías en el parse: mantiene el copy previo 'Confirmar carga'", async () => {
    useDetailAndDryRun(META_NO_CATEGORIES);
    renderAt();

    expect(await screen.findByTestId("wizard-step2-confirm-label")).toHaveTextContent(
      "Confirmar carga",
    );
    expect(screen.queryByTestId("category-mapping-table")).not.toBeInTheDocument();
  });

  it("con categorías: monta CategoryMappingTable y el aviso de filas ilegibles", async () => {
    useDetailAndDryRun(META_WITH_CATEGORIES);
    renderAt();

    expect(await screen.findByTestId("category-mapping-table")).toBeInTheDocument();
    expect(screen.getByTestId("unreadable-rows-notice")).toHaveTextContent(/página 5/i);
  });

  it("el botón de confirmar muestra 'Confirmar categorías completas (1 de 2)'", async () => {
    useDetailAndDryRun(META_WITH_CATEGORIES);
    renderAt();

    expect(await screen.findByTestId("wizard-step2-confirm-label")).toHaveTextContent(
      "Confirmar categorías completas (1 de 2)",
    );
  });

  it("corregir la categoría inconsistente sube el conteo del botón a (2 de 2)", async () => {
    useDetailAndDryRun(META_WITH_CATEGORIES);
    mswServer.use(
      http.post(`${BASE}/7/corrections`, () =>
        HttpResponse.json({
          category_header: "INFANTIL A DAMAS",
          completeness: { status: "ok", missing: [], duplicated: [] },
        }),
      ),
    );
    const user = userEvent.setup();
    renderAt();

    await screen.findByTestId("category-mapping-table");
    await user.click(screen.getByTestId("correct-row-INFANTIL A DAMAS"));
    await user.type(await screen.findByLabelText(/^nombre$/i), "Corredora Nueva");
    await user.click(screen.getByRole("button", { name: /^Guardar$/i }));

    await waitFor(() =>
      expect(screen.getByTestId("wizard-step2-confirm-label")).toHaveTextContent(
        "Confirmar categorías completas (2 de 2)",
      ),
    );
  });
});
