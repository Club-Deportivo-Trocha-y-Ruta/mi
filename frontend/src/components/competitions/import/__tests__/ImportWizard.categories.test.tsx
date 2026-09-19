/**
 * ImportWizard — integración con la integridad de lectura del acta
 * (feature 044, US1 + US2, T022/T023).
 *
 * Cubre los estados del wizard alrededor de `CategoryMappingTable`:
 *  - `parseResult.categories` se monta en step 2 con el aviso de filas
 *    ilegibles.
 *  - El botón de confirmar muestra "Confirmar categorías completas (N de
 *    M)" cuando el parse trae categorías, y conserva el copy previo
 *    "Confirmar e ingestar" cuando no las trae (compatibilidad hacia atrás
 *    — aditivo, FR-… de `contracts/reading-integrity.md`).
 *  - Corregir la fila faltante desde el wizard actualiza el conteo N de M
 *    del botón sin bloquear la confirmación (el commit real deja las
 *    categorías no listas en `pending_categories`, no es esta pantalla la
 *    que bloquea).
 *
 * Mismo patrón de mocks que `ImportWizard.test.tsx` (mock de
 * `@/api/raceImports` y `@/api/athletes`, sin MSW — este módulo no está en
 * el registro global de handlers).
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { createElement, type ReactNode } from "react";

vi.mock("@/api/raceImports", () => ({
  parseRaceImport: vi.fn(),
  dryRunRaceImport: vi.fn(),
  commitRaceImport: vi.fn(),
  listRaceImports: vi.fn(),
  getRevisionReasons: vi.fn(),
  getRaceEventDiff: vi.fn(),
  addRaceImportRowCorrection: vi.fn(),
  acknowledgeRaceImportCategory: vi.fn(),
  getAcknowledgeReasons: vi.fn(),
}));

vi.mock("@/api/athletes", () => ({
  getAthletes: vi.fn(),
  getAthlete: vi.fn(),
}));

vi.mock("@/store/auth.store", () => ({
  useAuthStore: (selector: (s: { accessToken: string }) => unknown) =>
    selector({ accessToken: "test-token" }),
}));

import * as importsApi from "@/api/raceImports";
import { ImportWizard } from "@/components/competitions/import/ImportWizard";
import type {
  ImportDryRunMatchesResponse,
  ImportParseResponse,
} from "@/types/raceImports.types";

function wrap(ui: ReactNode) {
  const qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  return render(
    createElement(
      QueryClientProvider,
      { client: qc },
      createElement(MemoryRouter, null, ui),
    ),
  );
}

function makeValidPdf(name = "ok.pdf"): File {
  const header = new TextEncoder().encode("%PDF-1.4\n");
  return new File([header, new Uint8Array(512)], name, {
    type: "application/pdf",
  });
}

async function fillStep1AndSubmit(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByTestId("wizard-series-name"), "Copa Valle");
  fireEvent.change(screen.getByTestId("wizard-valida-num"), {
    target: { value: "4" },
  });
  await user.type(screen.getByTestId("wizard-event-name"), "Válida IV — Cali");
  fireEvent.change(screen.getByTestId("wizard-event-date"), {
    target: { value: "2026-05-17" },
  });
  await user.type(screen.getByTestId("wizard-location"), "Cali");

  const input = screen.getByTestId(
    "race-upload-resultados-input",
  ) as HTMLInputElement;
  const pdf = makeValidPdf();
  Object.defineProperty(input, "files", { value: [pdf] });
  fireEvent.change(input);

  await waitFor(() =>
    expect(
      screen.getByTestId("race-upload-resultados-preview"),
    ).toBeInTheDocument(),
  );

  await user.click(screen.getByTestId("wizard-step1-submit"));
}

const DRY_RUN_CONFIRMED_ONLY: ImportDryRunMatchesResponse = {
  parse_id: "p-1",
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

const PARSE_RESPONSE_NO_CATEGORIES: ImportParseResponse = {
  parse_id: "p-1",
  sha256: "abcd",
  header: {
    series_name: "Copa Valle",
    season: 2026,
    valida_num: 4,
    event_name: "IV — Cali",
  },
  n_rows_resultados: 200,
  n_rows_general: 0,
  warnings: [],
};

const PARSE_RESPONSE_WITH_CATEGORIES: ImportParseResponse = {
  ...PARSE_RESPONSE_NO_CATEGORIES,
  categories: [
    {
      header_raw: "PREJUVENIL A DAMAS",
      code: "PREJ_A_F",
      mapping_kind: "exact",
      rows: [
        {
          position: 1,
          bib: "101",
          name: "Corredora Uno",
          city: "Cali",
          club: "Club Ficticio",
          time_raw: "00:40:00",
          points: 0,
        },
      ],
      completeness: { status: "ok", missing: [], duplicated: [] },
    },
    {
      header_raw: "INFANTIL A DAMAS",
      code: "INF_A_F",
      mapping_kind: "rename",
      rows: [
        { position: 1, bib: "1", name: "A", city: "", club: "", time_raw: "", points: 0 },
        { position: 2, bib: "2", name: "B", city: "", club: "", time_raw: "", points: 0 },
      ],
      completeness: { status: "inconsistent", missing: [3], duplicated: [] },
    },
  ],
  unreadable_rows: [{ page: 5, ordinal: null }],
};

beforeEach(() => {
  vi.clearAllMocks();
});

describe("ImportWizard — categorías (feature 044)", () => {
  it("sin categorías en el parse: mantiene el copy previo 'Confirmar e ingestar'", async () => {
    vi.mocked(importsApi.parseRaceImport).mockResolvedValue(
      PARSE_RESPONSE_NO_CATEGORIES,
    );
    vi.mocked(importsApi.dryRunRaceImport).mockResolvedValue(
      DRY_RUN_CONFIRMED_ONLY,
    );

    const user = userEvent.setup();
    wrap(<ImportWizard />);
    await fillStep1AndSubmit(user);

    expect(await screen.findByTestId("wizard-step2-confirm-label")).toHaveTextContent(
      "Confirmar e ingestar",
    );
    expect(screen.queryByTestId("category-mapping-table")).not.toBeInTheDocument();
  });

  it("con categorías: monta CategoryMappingTable y el aviso de filas ilegibles", async () => {
    vi.mocked(importsApi.parseRaceImport).mockResolvedValue(
      PARSE_RESPONSE_WITH_CATEGORIES,
    );
    vi.mocked(importsApi.dryRunRaceImport).mockResolvedValue(
      DRY_RUN_CONFIRMED_ONLY,
    );

    const user = userEvent.setup();
    wrap(<ImportWizard />);
    await fillStep1AndSubmit(user);

    expect(await screen.findByTestId("category-mapping-table")).toBeInTheDocument();
    expect(screen.getByTestId("unreadable-rows-notice")).toHaveTextContent(
      /página 5/i,
    );
  });

  it("el botón de confirmar muestra 'Confirmar categorías completas (1 de 2)'", async () => {
    vi.mocked(importsApi.parseRaceImport).mockResolvedValue(
      PARSE_RESPONSE_WITH_CATEGORIES,
    );
    vi.mocked(importsApi.dryRunRaceImport).mockResolvedValue(
      DRY_RUN_CONFIRMED_ONLY,
    );

    const user = userEvent.setup();
    wrap(<ImportWizard />);
    await fillStep1AndSubmit(user);

    expect(
      await screen.findByTestId("wizard-step2-confirm-label"),
    ).toHaveTextContent("Confirmar categorías completas (1 de 2)");
  });

  it("corregir la categoría inconsistente sube el conteo del botón a (2 de 2)", async () => {
    vi.mocked(importsApi.parseRaceImport).mockResolvedValue(
      PARSE_RESPONSE_WITH_CATEGORIES,
    );
    vi.mocked(importsApi.dryRunRaceImport).mockResolvedValue(
      DRY_RUN_CONFIRMED_ONLY,
    );
    vi.mocked(importsApi.addRaceImportRowCorrection).mockResolvedValue({
      category_header: "INFANTIL A DAMAS",
      completeness: { status: "ok", missing: [], duplicated: [] },
    });

    const user = userEvent.setup();
    wrap(<ImportWizard />);
    await fillStep1AndSubmit(user);

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
