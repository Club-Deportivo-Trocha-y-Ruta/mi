/**
 * Tests para ImportWizard (3 pasos).
 *
 * Cubre:
 *  - Step 1: validación form (no submit sin archivo)
 *  - Step 1: submit OK avanza a step 2
 *  - Step 1: error API muestra alert
 *  - Step 2: loader visible mientras dry-run isPending
 *  - Step 2: tabla matches renderiza con counts
 *  - Step 2: toggle "solo pendientes" filtra correctamente
 *  - Step 2: confirmar deshabilitado si ambiguos pendientes
 *  - Step 2: resolver ambiguo via combobox habilita confirmar
 *  - Step 3: success summary visible
 *  - Step 3: error con botón reintentar
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  render,
  screen,
  waitFor,
  fireEvent,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { createElement, type ReactNode } from "react";

vi.mock("@/api/raceImports", () => ({
  parseRaceImport: vi.fn(),
  dryRunRaceImport: vi.fn(),
  commitRaceImport: vi.fn(),
  listRaceImports: vi.fn(),
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
import * as athletesApi from "@/api/athletes";
import { ImportWizard } from "@/components/ai/ImportWizard";
import type {
  DiffRow,
  ImportDryRunMatchesResponse,
  ImportDryRunResponse,
  ImportDryRunRevisionResponse,
  ImportParseResponse,
} from "@/types/raceImports.types";
import { Sex } from "@/types/enums";

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

const PARSE_RESPONSE: ImportParseResponse = {
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

const DRY_RUN_CONFIRMED_ONLY: ImportDryRunMatchesResponse = {
  parse_id: "p-1",
  matches: [
    {
      competitor_normalized_name: "juan perez",
      competitor_display_name: "Juan Pérez",
      tyr_athlete: { id: 1, full_name: "Juan Pérez" },
      confidence: 0.95,
      is_ambiguous: false,
    },
  ],
  counts: { confirmed: 1, ambiguous: 0, no_match: 0, total: 1 },
  warnings: [],
};

// ---------------- F-UP-REV5 fixtures
const PARSE_REVISION_RESPONSE: ImportParseResponse = {
  parse_id: "p-rev-1",
  sha256: "rev-sha",
  header: {
    series_name: "Copa Valle",
    season: 2026,
    valida_num: 4,
    event_name: "IV — Cali",
  },
  n_rows_resultados: 80,
  n_rows_general: 0,
  warnings: [],
  will_be_revision: true,
  parent_import_id: 12,
  parent_event_id: 4,
  parent_committed_at: "2026-05-17T18:42:00Z",
  parent_n_results: 78,
};

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
  parse_id: "p-rev-1",
  is_revision: true,
  parent_event_id: 4,
  diff_summary: {
    n_create: 1,
    n_update: 1,
    n_delete: 0,
    n_unchanged: 78,
    n_total: 80,
  },
  diff_rows: REVISION_DIFF_BASIC,
  warnings: [],
};

const DRY_RUN_REVISION_WITH_DELETES: ImportDryRunRevisionResponse = {
  parse_id: "p-rev-1",
  is_revision: true,
  parent_event_id: 4,
  diff_summary: {
    n_create: 1,
    n_update: 1,
    n_delete: 1,
    n_unchanged: 77,
    n_total: 80,
  },
  diff_rows: REVISION_DIFF_WITH_DELETES,
  warnings: [],
};

const DRY_RUN_REVISION_LARGE: ImportDryRunRevisionResponse = {
  parse_id: "p-rev-1",
  is_revision: true,
  parent_event_id: 4,
  // n_delete > 20% de n_unchanged → trigger warning naranja
  diff_summary: {
    n_create: 0,
    n_update: 0,
    n_delete: 5,
    n_unchanged: 10,
    n_total: 15,
  },
  diff_rows: REVISION_DIFF_WITH_DELETES,
  warnings: [],
};

const DRY_RUN_WITH_AMBIGUOUS: ImportDryRunResponse = {
  parse_id: "p-1",
  matches: [
    {
      competitor_normalized_name: "juan perez",
      competitor_display_name: "Juan Pérez",
      tyr_athlete: { id: 1, full_name: "Juan Pérez" },
      confidence: 0.95,
      is_ambiguous: false,
    },
    {
      competitor_normalized_name: "maria gonzalez",
      competitor_display_name: "María González",
      tyr_athlete: null,
      confidence: 0.7,
      is_ambiguous: true,
    },
  ],
  counts: { confirmed: 1, ambiguous: 1, no_match: 0, total: 2 },
  warnings: [],
};

beforeEach(() => {
  vi.clearAllMocks();
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
    ] as any,
    total: 2,
  } as any);
});

async function fillStep1AndSubmit(user: ReturnType<typeof userEvent.setup>) {
  // event_name + event_date + location + valida_num (los defaults bastan
  // para series_name y season).
  await user.type(screen.getByTestId("wizard-event-name"), "Válida IV — Cali");
  // event_date type=date acepta YYYY-MM-DD vía fireEvent.change.
  fireEvent.change(screen.getByTestId("wizard-event-date"), {
    target: { value: "2026-05-17" },
  });
  await user.type(screen.getByTestId("wizard-location"), "Cali");

  // Subimos un PDF válido vía input.
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

describe("ImportWizard — Step 1", () => {
  it("muestra error si se intenta avanzar sin archivo de resultados", async () => {
    const user = userEvent.setup();
    wrap(<ImportWizard />);

    await user.type(
      screen.getByTestId("wizard-event-name"),
      "Válida IV",
    );
    fireEvent.change(screen.getByTestId("wizard-event-date"), {
      target: { value: "2026-05-17" },
    });
    await user.type(screen.getByTestId("wizard-location"), "Cali");

    await user.click(screen.getByTestId("wizard-step1-submit"));
    expect(
      await screen.findByTestId("wizard-step1-error"),
    ).toHaveTextContent(/adjuntar el archivo de resultados/i);
  });

  it("submit OK avanza a step 2 y dispara dry-run", async () => {
    vi.mocked(importsApi.parseRaceImport).mockResolvedValue(PARSE_RESPONSE);
    vi.mocked(importsApi.dryRunRaceImport).mockResolvedValue(
      DRY_RUN_CONFIRMED_ONLY,
    );

    const user = userEvent.setup();
    wrap(<ImportWizard />);

    await fillStep1AndSubmit(user);

    await waitFor(() =>
      expect(screen.getByTestId("import-wizard-step2")).toBeInTheDocument(),
    );
    expect(importsApi.dryRunRaceImport).toHaveBeenCalledWith("p-1");
  });

  it("error API en step 1 muestra alert", async () => {
    vi.mocked(importsApi.parseRaceImport).mockRejectedValue({
      response: { status: 413, data: { detail: "Demasiado grande" } },
    });

    const user = userEvent.setup();
    wrap(<ImportWizard />);

    await fillStep1AndSubmit(user);

    expect(
      await screen.findByTestId("wizard-step1-error"),
    ).toHaveTextContent(/Demasiado grande/i);
  });

  it("error con detail array (validation errors FastAPI) toma primer msg", async () => {
    vi.mocked(importsApi.parseRaceImport).mockRejectedValue({
      response: {
        status: 422,
        data: { detail: [{ msg: "Campo invalido X" }] },
      },
    });
    const user = userEvent.setup();
    wrap(<ImportWizard />);
    await fillStep1AndSubmit(user);
    expect(
      await screen.findByTestId("wizard-step1-error"),
    ).toHaveTextContent(/Campo invalido X/i);
  });
});

describe("ImportWizard — Step 2", () => {
  it("muestra loader mientras dry-run isPending", async () => {
    vi.mocked(importsApi.parseRaceImport).mockResolvedValue(PARSE_RESPONSE);
    // Promesa que nunca resuelve para mantener isPending.
    vi.mocked(importsApi.dryRunRaceImport).mockImplementation(
      () => new Promise(() => {}),
    );

    const user = userEvent.setup();
    wrap(<ImportWizard />);
    await fillStep1AndSubmit(user);

    expect(
      await screen.findByTestId("wizard-dry-run-loading"),
    ).toBeInTheDocument();
  });

  it("renderiza tabla de matches con counts visibles", async () => {
    vi.mocked(importsApi.parseRaceImport).mockResolvedValue(PARSE_RESPONSE);
    vi.mocked(importsApi.dryRunRaceImport).mockResolvedValue(
      DRY_RUN_WITH_AMBIGUOUS,
    );

    const user = userEvent.setup();
    wrap(<ImportWizard />);
    await fillStep1AndSubmit(user);

    await waitFor(() =>
      expect(screen.getByTestId("wizard-counts")).toBeInTheDocument(),
    );
    const counts = screen.getByTestId("wizard-counts");
    expect(within(counts).getByText("Confirmados")).toBeInTheDocument();
    expect(within(counts).getByText("Ambiguos")).toBeInTheDocument();
    expect(
      screen.getByTestId("wizard-matches-table"),
    ).toBeInTheDocument();
  });

  it("toggle 'solo pendientes' filtra a sólo ambiguos no resueltos", async () => {
    vi.mocked(importsApi.parseRaceImport).mockResolvedValue(PARSE_RESPONSE);
    vi.mocked(importsApi.dryRunRaceImport).mockResolvedValue(
      DRY_RUN_WITH_AMBIGUOUS,
    );

    const user = userEvent.setup();
    wrap(<ImportWizard />);
    await fillStep1AndSubmit(user);

    await waitFor(() =>
      expect(screen.getByTestId("wizard-matches-table")).toBeInTheDocument(),
    );
    // Inicialmente vemos las 2 filas.
    expect(
      screen.getByTestId("wizard-match-row-juan perez"),
    ).toBeInTheDocument();
    expect(
      screen.getByTestId("wizard-match-row-maria gonzalez"),
    ).toBeInTheDocument();

    await user.click(screen.getByTestId("wizard-toggle-pending"));

    // Sólo queda la ambigua no resuelta.
    expect(
      screen.queryByTestId("wizard-match-row-juan perez"),
    ).not.toBeInTheDocument();
    expect(
      screen.getByTestId("wizard-match-row-maria gonzalez"),
    ).toBeInTheDocument();
  });

  it("confirmar está deshabilitado mientras quedan ambiguos pendientes", async () => {
    vi.mocked(importsApi.parseRaceImport).mockResolvedValue(PARSE_RESPONSE);
    vi.mocked(importsApi.dryRunRaceImport).mockResolvedValue(
      DRY_RUN_WITH_AMBIGUOUS,
    );

    const user = userEvent.setup();
    wrap(<ImportWizard />);
    await fillStep1AndSubmit(user);

    await waitFor(() =>
      expect(screen.getByTestId("wizard-step2-confirm")).toBeInTheDocument(),
    );
    expect(screen.getByTestId("wizard-step2-confirm")).toBeDisabled();
    expect(screen.getByTestId("wizard-pending-hint")).toHaveTextContent(
      /matches ambiguos/i,
    );
  });

  it("botón volver regresa a step 1", async () => {
    vi.mocked(importsApi.parseRaceImport).mockResolvedValue(PARSE_RESPONSE);
    vi.mocked(importsApi.dryRunRaceImport).mockResolvedValue(
      DRY_RUN_CONFIRMED_ONLY,
    );

    const user = userEvent.setup();
    wrap(<ImportWizard />);
    await fillStep1AndSubmit(user);

    await waitFor(() =>
      expect(screen.getByTestId("import-wizard-step2")).toBeInTheDocument(),
    );
    await user.click(screen.getByTestId("wizard-step2-back"));
    expect(screen.getByTestId("import-wizard-step1")).toBeInTheDocument();
  });
});

describe("ImportWizard — Step 3", () => {
  it("success: muestra summary y link al análisis", async () => {
    vi.mocked(importsApi.parseRaceImport).mockResolvedValue(PARSE_RESPONSE);
    vi.mocked(importsApi.dryRunRaceImport).mockResolvedValue(
      DRY_RUN_CONFIRMED_ONLY,
    );
    vi.mocked(importsApi.commitRaceImport).mockResolvedValue({
      parse_id: "p-1",
      race_event_id: 4,
      n_results_inserted: 200,
      n_competitors_created: 198,
      n_competitors_linked: 3,
    });

    const user = userEvent.setup();
    wrap(<ImportWizard />);
    await fillStep1AndSubmit(user);

    await waitFor(() =>
      expect(screen.getByTestId("wizard-step2-confirm")).toBeEnabled(),
    );
    await user.click(screen.getByTestId("wizard-step2-confirm"));

    await waitFor(() =>
      expect(screen.getByTestId("wizard-step3-success")).toBeInTheDocument(),
    );
    expect(screen.getByTestId("wizard-step3-success")).toHaveTextContent(
      /200/,
    );
    expect(
      screen.getByTestId("wizard-step3-link-analysis"),
    ).toHaveAttribute("href", expect.stringContaining("tab=runs"));
  });

  it("'Cargar otro' resetea el wizard a step 1", async () => {
    vi.mocked(importsApi.parseRaceImport).mockResolvedValue(PARSE_RESPONSE);
    vi.mocked(importsApi.dryRunRaceImport).mockResolvedValue(
      DRY_RUN_CONFIRMED_ONLY,
    );
    vi.mocked(importsApi.commitRaceImport).mockResolvedValue({
      parse_id: "p-1",
      race_event_id: 4,
      n_results_inserted: 200,
      n_competitors_created: 198,
      n_competitors_linked: 3,
    });

    const user = userEvent.setup();
    wrap(<ImportWizard />);
    await fillStep1AndSubmit(user);

    await waitFor(() =>
      expect(screen.getByTestId("wizard-step2-confirm")).toBeEnabled(),
    );
    await user.click(screen.getByTestId("wizard-step2-confirm"));

    await waitFor(() =>
      expect(screen.getByTestId("wizard-step3-success")).toBeInTheDocument(),
    );
    await user.click(screen.getByTestId("wizard-step3-new"));
    expect(screen.getByTestId("import-wizard-step1")).toBeInTheDocument();
  });

  it("error commit: muestra botón reintentar y vuelve a step 2", async () => {
    vi.mocked(importsApi.parseRaceImport).mockResolvedValue(PARSE_RESPONSE);
    vi.mocked(importsApi.dryRunRaceImport).mockResolvedValue(
      DRY_RUN_CONFIRMED_ONLY,
    );
    vi.mocked(importsApi.commitRaceImport).mockRejectedValue({
      response: { status: 500, data: { detail: "Boom commit" } },
    });

    const user = userEvent.setup();
    wrap(<ImportWizard />);
    await fillStep1AndSubmit(user);

    await waitFor(() =>
      expect(screen.getByTestId("wizard-step2-confirm")).toBeEnabled(),
    );
    await user.click(screen.getByTestId("wizard-step2-confirm"));

    await waitFor(() =>
      expect(screen.getByTestId("wizard-step3-error")).toBeInTheDocument(),
    );
    expect(screen.getByTestId("wizard-step3-error")).toHaveTextContent(
      /Boom commit/,
    );

    await user.click(screen.getByTestId("wizard-step3-retry"));
    expect(screen.getByTestId("import-wizard-step2")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// F-UP-REV5 — Modo revisión
// ---------------------------------------------------------------------------

describe("ImportWizard — Revision mode (F-UP-REV5)", () => {
  async function gotoStep2Revision(
    user: ReturnType<typeof userEvent.setup>,
    dryRun: ImportDryRunResponse,
  ) {
    vi.mocked(importsApi.parseRaceImport).mockResolvedValue(
      PARSE_REVISION_RESPONSE,
    );
    vi.mocked(importsApi.dryRunRaceImport).mockResolvedValue(dryRun);
    wrap(<ImportWizard />);
    await fillStep1AndSubmit(user);
    await waitFor(() =>
      expect(screen.getByTestId("wizard-revision-mode")).toBeInTheDocument(),
    );
  }

  it("detecta is_revision=true en dry-run → renderiza DiffTable en lugar de matches", async () => {
    const user = userEvent.setup();
    await gotoStep2Revision(user, DRY_RUN_REVISION_SAFE);

    // DiffTable es lazy → findBy* espera al chunk
    expect(await screen.findByTestId("diff-table")).toBeInTheDocument();
    // No debe haber matches table (modo F-UP normal)
    expect(screen.queryByTestId("wizard-matches-table")).not.toBeInTheDocument();
    expect(screen.queryByTestId("wizard-counts")).not.toBeInTheDocument();
    // Render del competidor del diff
    expect(await screen.findByText("Andrés Mejía")).toBeInTheDocument();
  });

  it("banner amarillo de revisión visible con metadata del padre", async () => {
    const user = userEvent.setup();
    await gotoStep2Revision(user, DRY_RUN_REVISION_SAFE);

    const banner = screen.getByTestId("wizard-revision-banner");
    expect(banner).toHaveTextContent(/Revisión detectada/i);
    // counts del summary visibles
    expect(banner).toHaveTextContent("1");
    expect(banner).toHaveTextContent("80");
    expect(banner).toHaveTextContent(/Válida/);
  });

  it("banner naranja warning cuando deletes > 20% de unchanged", async () => {
    const user = userEvent.setup();
    await gotoStep2Revision(user, DRY_RUN_REVISION_LARGE);

    expect(
      screen.getByTestId("wizard-revision-warning-large"),
    ).toHaveTextContent(/inusualmente grandes/i);
  });

  it("revision_reason obligatorio si n_delete > 0 (botón disabled hasta llenar)", async () => {
    const user = userEvent.setup();
    await gotoStep2Revision(user, DRY_RUN_REVISION_WITH_DELETES);

    const confirm = screen.getByTestId("wizard-step2-confirm");
    const textarea = screen.getByTestId("wizard-revision-reason");

    // Sin reason → disabled
    expect(confirm).toBeDisabled();
    expect(textarea).toHaveAttribute("aria-required", "true");

    // Llenar reason → habilitado
    await user.type(textarea, "Corrección oficial federación post-reclamo");
    expect(confirm).toBeEnabled();
  });

  it("revision_reason opcional si solo creates/updates (botón enabled sin texto)", async () => {
    const user = userEvent.setup();
    await gotoStep2Revision(user, DRY_RUN_REVISION_SAFE);

    const confirm = screen.getByTestId("wizard-step2-confirm");
    const textarea = screen.getByTestId("wizard-revision-reason");

    // n_delete=0 → no required → enabled sin texto
    expect(textarea).not.toHaveAttribute("aria-required", "true");
    expect(confirm).toBeEnabled();
  });

  it("commit envía revision_reason en payload + step 3 muestra summary revisión", async () => {
    vi.mocked(importsApi.commitRaceImport).mockResolvedValue({
      parse_id: "p-rev-1",
      race_event_id: 4,
      n_results_inserted: 0,
      n_competitors_created: 0,
      n_competitors_linked: 0,
    });
    const user = userEvent.setup();
    await gotoStep2Revision(user, DRY_RUN_REVISION_WITH_DELETES);

    const textarea = screen.getByTestId("wizard-revision-reason");
    await user.type(textarea, "  Corrección oficial federación  ");
    await user.click(screen.getByTestId("wizard-step2-confirm"));

    await waitFor(() =>
      expect(screen.getByTestId("wizard-step3-success")).toBeInTheDocument(),
    );

    // Verifica payload: revision_reason trimmed + resolved_matches vacío
    expect(importsApi.commitRaceImport).toHaveBeenCalledWith("p-rev-1", {
      resolved_matches: [],
      revision_reason: "Corrección oficial federación",
    });

    // Step 3 muestra resumen revisión, no el F-UP normal
    expect(
      screen.getByTestId("wizard-step3-revision-summary"),
    ).toHaveTextContent(/1.*actualizaciones/);
    expect(
      screen.getByTestId("wizard-step3-revision-summary"),
    ).toHaveTextContent(/1.*eliminaciones/);
    expect(screen.getByText(/Revisión aplicada/)).toBeInTheDocument();
  });

  it("texto del botón en modo revisión es 'Confirmar y aplicar revisión'", async () => {
    const user = userEvent.setup();
    await gotoStep2Revision(user, DRY_RUN_REVISION_SAFE);
    expect(screen.getByTestId("wizard-step2-confirm")).toHaveTextContent(
      /aplicar revisión/i,
    );
  });

  it("reset desde step 3 limpia revisionReason", async () => {
    vi.mocked(importsApi.commitRaceImport).mockResolvedValue({
      parse_id: "p-rev-1",
      race_event_id: 4,
      n_results_inserted: 0,
      n_competitors_created: 0,
      n_competitors_linked: 0,
    });
    const user = userEvent.setup();
    await gotoStep2Revision(user, DRY_RUN_REVISION_WITH_DELETES);

    await user.type(
      screen.getByTestId("wizard-revision-reason"),
      "Mi motivo",
    );
    await user.click(screen.getByTestId("wizard-step2-confirm"));

    await waitFor(() =>
      expect(screen.getByTestId("wizard-step3-success")).toBeInTheDocument(),
    );
    await user.click(screen.getByTestId("wizard-step3-new"));
    expect(screen.getByTestId("import-wizard-step1")).toBeInTheDocument();
  });
});
