/**
 * DiffConfirm — pruebas de integración del flujo de confirmación de diff (US4).
 *
 * Verifica que:
 *  1. El diff agrupa los cambios por tipo de acción (create/update/delete/unchanged).
 *  2. El botón "Confirmar y aplicar revisión" queda deshabilitado si hay
 *     deletes y no se ha elegido un motivo del catálogo cerrado.
 *  3. Al confirmar con motivo elegido, el commit se ejecuta con el payload
 *     correcto (FR-016: motivo obligatorio con deletes).
 *  4. Un diff que NO tiene deletes permite confirmar sin elegir motivo
 *     (FR-016: solo obligatorio con deletes).
 *  5. jest-axe: el step 2 en modo revisión no tiene violaciones a11y.
 *
 * Nota: este archivo se enfoca en la INTERFAZ de confirmación del diff.
 * Los tests de ciclo completo del wizard (parse → dry-run → commit → step 3)
 * viven en ImportWizard.test.tsx.
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
import { axe, toHaveNoViolations } from "jest-axe";

expect.extend(toHaveNoViolations);

vi.mock("@/api/raceImports", () => ({
  parseRaceImport: vi.fn(),
  dryRunRaceImport: vi.fn(),
  commitRaceImport: vi.fn(),
  listRaceImports: vi.fn(),
  getRevisionReasons: vi.fn(),
  getRaceEventDiff: vi.fn(),
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
import { ImportWizard } from "@/components/competitions/import/ImportWizard";
import type {
  DiffRow,
  ImportDryRunRevisionResponse,
  ImportParseResponse,
} from "@/types/raceImports.types";
import { Sex } from "@/types/enums";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

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

function makeValidPdf(name = "resultados.pdf"): File {
  const header = new TextEncoder().encode("%PDF-1.4\n");
  return new File([header, new Uint8Array(512)], name, {
    type: "application/pdf",
  });
}

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const PARSE_REVISION: ImportParseResponse = {
  parse_id: "p-rev",
  sha256: "sha-rev",
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
  parent_import_id: 10,
  parent_event_id: 4,
  parent_committed_at: "2026-05-17T18:42:00Z",
  parent_n_results: 78,
};

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
  parse_id: "p-rev",
  is_revision: true,
  parent_event_id: 4,
  diff_summary: {
    n_create: 1,
    n_update: 1,
    n_delete: 1,
    n_unchanged: 77,
    n_total: 80,
  },
  diff_rows: DIFF_ROWS_ALL_TYPES,
  warnings: [],
};

const DRY_RUN_NO_DELETES: ImportDryRunRevisionResponse = {
  parse_id: "p-rev",
  is_revision: true,
  parent_event_id: 4,
  diff_summary: {
    n_create: 1,
    n_update: 1,
    n_delete: 0,
    n_unchanged: 78,
    n_total: 80,
  },
  diff_rows: DIFF_ROWS_ALL_TYPES.filter((r) => r.action !== "delete"),
  warnings: [],
};

// ---------------------------------------------------------------------------
// Setup
// ---------------------------------------------------------------------------

async function renderAndGoToRevisionStep2(
  dryRun: ImportDryRunRevisionResponse,
) {
  vi.mocked(importsApi.parseRaceImport).mockResolvedValue(PARSE_REVISION);
  vi.mocked(importsApi.dryRunRaceImport).mockResolvedValue(dryRun);

  const user = userEvent.setup();
  wrap(<ImportWizard />);

  // Paso 1: rellenar campos mínimos y subir PDF
  // Spec 014: series_name y valida_num son requeridos para copa.
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

  // Esperar a que el wizard entre en modo revisión
  await waitFor(() =>
    expect(screen.getByTestId("wizard-revision-mode")).toBeInTheDocument(),
  );

  return user;
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(importsApi.getRevisionReasons).mockResolvedValue({
    options: [
      { code: "official_correction", label: "Corrección oficial de la Federación" },
      { code: "timing_fix", label: "Ajuste de tiempos" },
    ],
  });
  vi.mocked(athletesApi.getAthletes).mockResolvedValue({
    items: [
      {
        id: 1,
        first_name: "Juan",
        last_name: "Pérez",
        sex: Sex.M,
        category: "INF-A-M",
        club_id: 1,
        is_active: true,
        user_id: null,
      },
    ] as unknown[],
    total: 1,
  } as Awaited<ReturnType<typeof athletesApi.getAthletes>>);
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("Diff-confirm flow (US4 / FR-014…017)", () => {
  it("renderiza los cuatro tipos de cambio como badges en el DiffTable", async () => {
    await renderAndGoToRevisionStep2(DRY_RUN_WITH_DELETES);

    // DiffTable es lazy — esperar hasta que esté montado
    const diffTable = await screen.findByTestId("diff-table");
    expect(diffTable).toBeInTheDocument();

    // Verificar presencia de las 4 acciones (agrupadas por badge)
    expect(within(diffTable).getByTestId("diff-badge-create")).toBeInTheDocument();
    expect(within(diffTable).getByTestId("diff-badge-update")).toBeInTheDocument();
    expect(within(diffTable).getByTestId("diff-badge-delete")).toBeInTheDocument();
    expect(within(diffTable).getByTestId("diff-badge-unchanged")).toBeInTheDocument();
  });

  it("muestra los nombres de los competidores en las filas del diff", async () => {
    await renderAndGoToRevisionStep2(DRY_RUN_WITH_DELETES);

    const diffTable = await screen.findByTestId("diff-table");
    // Competidores de todos los tipos
    expect(within(diffTable).getByText("Sofía Rueda")).toBeInTheDocument();
    expect(within(diffTable).getByText("Andrés Mejía")).toBeInTheDocument();
    expect(within(diffTable).getByText("Diego Rojas")).toBeInTheDocument();
    expect(within(diffTable).getByText("Juan Pérez")).toBeInTheDocument();
  });

  it("requiere confirmar explícitamente: botón deshabilitado con deletes sin motivo", async () => {
    await renderAndGoToRevisionStep2(DRY_RUN_WITH_DELETES);

    await screen.findByTestId("diff-table");
    const confirm = screen.getByTestId("wizard-step2-confirm");

    // Con deletions y sin motivo seleccionado → disabled (FR-016)
    expect(confirm).toBeDisabled();
  });

  it("permite confirmar una vez seleccionado el motivo del catálogo cerrado", async () => {
    const user = await renderAndGoToRevisionStep2(DRY_RUN_WITH_DELETES);

    await screen.findByTestId("diff-table");
    const confirm = screen.getByTestId("wizard-step2-confirm");
    const select = screen.getByTestId("wizard-revision-reason");

    // Antes de elegir motivo → disabled
    expect(confirm).toBeDisabled();

    // Elegir motivo del catálogo (sin texto libre)
    await user.selectOptions(select, "official_correction");

    // Ahora el botón debe estar habilitado (FR-017: aplicación explícita)
    expect(confirm).toBeEnabled();
  });

  it("sin deletes el commit no requiere motivo (botón habilitado desde el inicio)", async () => {
    await renderAndGoToRevisionStep2(DRY_RUN_NO_DELETES);

    await screen.findByTestId("diff-table");
    const confirm = screen.getByTestId("wizard-step2-confirm");
    const select = screen.getByTestId("wizard-revision-reason");

    // n_delete=0 → motivo no requerido → enabled
    expect(select).not.toHaveAttribute("aria-required", "true");
    expect(confirm).toBeEnabled();
  });

  it("commit envía el código del motivo (no texto libre) en el payload", async () => {
    vi.mocked(importsApi.commitRaceImport).mockResolvedValue({
      parse_id: "p-rev",
      race_event_id: 4,
      n_results_inserted: 0,
      n_competitors_created: 0,
      n_competitors_linked: 0,
    });

    const user = await renderAndGoToRevisionStep2(DRY_RUN_WITH_DELETES);
    await screen.findByTestId("diff-table");

    await user.selectOptions(
      screen.getByTestId("wizard-revision-reason"),
      "timing_fix",
    );
    await user.click(screen.getByTestId("wizard-step2-confirm"));

    await waitFor(() =>
      expect(importsApi.commitRaceImport).toHaveBeenCalledTimes(1),
    );

    // El payload debe contener el CODE del catálogo, NO texto libre (PR4)
    const [, body] = vi.mocked(importsApi.commitRaceImport).mock.calls[0];
    expect(body.revision_reason).toBe("timing_fix");
    // Y el commit envía matches vacíos en modo revisión
    expect(body.resolved_matches).toHaveLength(0);
  });

  it("el filtro 'solo cambios' oculta las filas sin cambios por defecto cuando hay >20 unchanged", async () => {
    // Diff con muchos unchanged para disparar el default de la DiffTable
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
      parse_id: "p-rev",
      is_revision: true,
      parent_event_id: 4,
      diff_summary: {
        n_create: 1,
        n_update: 1,
        n_delete: 1,
        n_unchanged: 25,
        n_total: 28,
      },
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

    await renderAndGoToRevisionStep2(dryRunManyUnchanged);
    const diffTable = await screen.findByTestId("diff-table");

    // El toggle debe estar ON por defecto (>20 unchanged)
    const toggle = within(diffTable).getByTestId(
      "diff-toggle-only-changes",
    ) as HTMLInputElement;
    expect(toggle.checked).toBe(true);

    // Los sin-cambios no se muestran, el actualizado sí
    expect(within(diffTable).getByText("Competidor Actualizado")).toBeInTheDocument();
    expect(within(diffTable).queryByText("Corredor 0")).not.toBeInTheDocument();
  });

  it("jest-axe: modo revisión step 2 sin violaciones de accesibilidad", async () => {
    await renderAndGoToRevisionStep2(DRY_RUN_WITH_DELETES);
    await screen.findByTestId("diff-table");

    // axe sobre el wizard completo en estado step 2
    const container = screen
      .getByTestId("import-wizard")
      .closest("section") as HTMLElement;
    const results = await axe(container ?? document.body);
    expect(results).toHaveNoViolations();
  });
});
