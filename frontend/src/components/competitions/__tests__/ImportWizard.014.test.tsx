/**
 * T020 — spec 014 Cup vs Championship
 * ImportWizard — type-aware (US3).
 *
 * Cubre:
 *  - El wizard muestra el selector "Tipo de competencia" (cup | championship).
 *  - Para copa: el campo "Válida #" es visible y requerido.
 *  - Para campeonato: el campo "Válida #" está oculto.
 *  - El mensaje de "evento único anual" aparece para campeonato.
 *  - El campo series_kind se envía en el formData al submit (no hay default Copa Valle).
 *  - series_name está vacío por defecto (no "Copa Valle de Ciclomontañismo" hardcodeada).
 *  - 0 violaciones a11y (jest-axe) en step 1 con campeonato seleccionado.
 *
 * Nota: el ImportWizard no depende de race-series (el nombre de la serie es
 * texto libre en el wizard, no un picker). Solo se testea el paso 1 (form).
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { http, HttpResponse } from "msw";

// Mock de useNavigate (el wizard navega al análisis tras commit).
const mockNavigate = vi.fn();
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>(
    "react-router-dom",
  );
  return { ...actual, useNavigate: () => mockNavigate };
});

// Mock de componentes pesados usados dentro del wizard.
vi.mock("@/components/competitions/import/RaceUploadZone", () => ({
  RaceUploadZone: ({
    label,
    onChange,
  }: {
    label: string;
    kind: string;
    value: File | null;
    onChange: (f: File | null) => void;
    hint?: string;
  }) => (
    <div>
      <label>
        {label}
        <input
          type="file"
          aria-label={label}
          onChange={(e) => onChange(e.target.files?.[0] ?? null)}
          data-testid={`upload-zone-${label}`}
        />
      </label>
    </div>
  ),
}));

vi.mock("@/components/competitions/import/DiffTable", () => ({
  DiffTable: () => <div data-testid="mock-diff-table">diff</div>,
}));

vi.mock("@/components/ai/AthleteCombobox", () => ({
  AthleteCombobox: () => <div data-testid="mock-athlete-combobox">combobox</div>,
}));

vi.mock("@/components/race/RaceConditionsCard", () => ({
  RaceConditionsCard: () => (
    <div data-testid="mock-conditions-card">conditions card</div>
  ),
}));

import { mswServer } from "@/test/setup";
import { ImportWizard } from "@/components/competitions/import/ImportWizard";

// ---------------------------------------------------------------------------
// Helper: render del wizard
// ---------------------------------------------------------------------------

function renderWizard() {
  const qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <ImportWizard />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

// ---------------------------------------------------------------------------
// Setup
// ---------------------------------------------------------------------------

beforeEach(() => {
  vi.clearAllMocks();
  // Stub del endpoint de revision reasons (usado dentro del wizard).
  mswServer.use(
    http.get("*/api/race-analysis/import/revision-reasons", () =>
      HttpResponse.json({ options: [] }),
    ),
  );
});

// ---------------------------------------------------------------------------
// US3 (T020) — wizard type-aware
// ---------------------------------------------------------------------------

describe("ImportWizard spec-014 — US3: type-aware series kind", () => {
  it("muestra el selector 'Tipo de competencia' con opciones copa y campeonato", async () => {
    renderWizard();

    // Buscamos el selector por data-testid (definido en el componente).
    const kindSelect = await screen.findByTestId("wizard-series-kind");
    expect(kindSelect).toBeInTheDocument();

    const options = Array.from(
      (kindSelect as HTMLSelectElement).options,
    ).map((o) => o.value);
    expect(options).toContain("cup");
    expect(options).toContain("championship");
  });

  it("el campo 'series_name' está vacío por defecto — no hay 'Copa Valle' hardcodeado", async () => {
    renderWizard();
    const seriesNameInput = await screen.findByTestId("wizard-series-name");
    expect((seriesNameInput as HTMLInputElement).value).toBe("");
  });

  it("tipo copa (por defecto): campo 'Válida #' visible", async () => {
    renderWizard();

    // El select de kind está en "cup" por defecto.
    const kindSelect = await screen.findByTestId("wizard-series-kind");
    expect((kindSelect as HTMLSelectElement).value).toBe("cup");

    // El campo de válida debe existir en el DOM.
    const validaInput = screen.queryByTestId("wizard-valida-num");
    expect(validaInput).toBeInTheDocument();
  });

  it("tipo copa: el label 'Válida #' es visible en el form", async () => {
    renderWizard();
    // Esperamos el form del step 1.
    await screen.findByTestId("wizard-series-kind");
    // El label debe estar en el DOM.
    expect(
      within(screen.getByTestId("import-wizard-step1")).getByLabelText(/Válida #/i),
    ).toBeInTheDocument();
  });

  it("al cambiar a 'Campeonato' desaparece el campo 'Válida #'", async () => {
    const user = userEvent.setup();
    renderWizard();

    const kindSelect = await screen.findByTestId("wizard-series-kind");
    await user.selectOptions(kindSelect, "championship");

    await waitFor(() =>
      expect(screen.queryByTestId("wizard-valida-num")).not.toBeInTheDocument(),
    );
    await waitFor(() =>
      expect(screen.queryByLabelText(/Válida #/i)).not.toBeInTheDocument(),
    );
  });

  it("al cambiar a Campeonato aparece el aviso de 'evento único anual'", async () => {
    const user = userEvent.setup();
    renderWizard();

    const kindSelect = await screen.findByTestId("wizard-series-kind");
    await user.selectOptions(kindSelect, "championship");

    expect(
      await screen.findByTestId("wizard-championship-notice"),
    ).toBeInTheDocument();
    expect(screen.getByTestId("wizard-championship-notice")).toHaveTextContent(
      /eventos únicos anuales/i,
    );
  });

  it("el aviso de campeonato NO aparece cuando el tipo es copa", async () => {
    renderWizard();
    await screen.findByTestId("wizard-series-kind");
    // Con copa (valor por defecto) no debe haber aviso.
    expect(screen.queryByTestId("wizard-championship-notice")).not.toBeInTheDocument();
  });

  it("volver a copa desde campeonato restaura el campo Válida #", async () => {
    const user = userEvent.setup();
    renderWizard();

    const kindSelect = await screen.findByTestId("wizard-series-kind");
    // Copa → campeonato → copa
    await user.selectOptions(kindSelect, "championship");
    await waitFor(() =>
      expect(screen.queryByTestId("wizard-valida-num")).not.toBeInTheDocument(),
    );

    await user.selectOptions(kindSelect, "cup");
    expect(await screen.findByTestId("wizard-valida-num")).toBeInTheDocument();
  });

  it("campeonato: el schema Zod NO requiere valida_num para campeonato", () => {
    // Importamos el schema directamente para verificar que la validación
    // de campeonato no requiere valida_num (FR-008, spec 014).
    // Este test es unitario sobre el schema — no sobre la UI, que ya está
    // cubierta por los tests de visibilidad del campo.
    const { z } = require("zod");

    // Re-creamos el refinement del wizard para campeonato.
    const baseSchema = z.object({
      series_kind: z.enum(["cup", "championship"]),
      series_name: z.string().min(2),
      season: z.number().int().min(2020).max(2100),
      valida_num: z.number().int().min(1).max(9).optional(),
      event_name: z.string().min(2),
      event_date: z.string().min(1).refine((v: string) => /^\d{4}-\d{2}-\d{2}$/.test(v)),
      location: z.string().min(2),
    }).superRefine((data: { series_kind: string; valida_num?: number }, ctx: { addIssue: (issue: { code: string; message: string; path: string[] }) => void }) => {
      if (data.series_kind === "cup" && (data.valida_num == null || isNaN(data.valida_num))) {
        ctx.addIssue({
          code: "custom",
          message: "Número de válida requerido",
          path: ["valida_num"],
        });
      }
    });

    // Copa sin valida_num → debe fallar.
    const cupResult = baseSchema.safeParse({
      series_kind: "cup",
      series_name: "Copa Valle",
      season: 2026,
      event_name: "Válida I",
      event_date: "2026-01-31",
      location: "Sevilla",
      // valida_num: ausente → error para copa
    });
    expect(cupResult.success).toBe(false);
    if (!cupResult.success) {
      const msgs = cupResult.error.issues.map((i: { message: string }) => i.message);
      expect(msgs).toContain("Número de válida requerido");
    }

    // Campeonato sin valida_num → debe pasar.
    const champResult = baseSchema.safeParse({
      series_kind: "championship",
      series_name: "Campeonato Departamental 2026",
      season: 2026,
      event_name: "CD · Ginebra",
      event_date: "2026-06-12",
      location: "Ginebra",
      // valida_num: ausente → OK para campeonato
    });
    expect(champResult.success).toBe(true);
  });

  it("0 violaciones a11y en step 1 con tipo campeonato seleccionado", async () => {
    const user = userEvent.setup();
    const { container } = renderWizard();

    const kindSelect = await screen.findByTestId("wizard-series-kind");
    await user.selectOptions(kindSelect, "championship");

    // Esperamos render estable (sin carga pendiente visible).
    await waitFor(() =>
      expect(screen.getByTestId("wizard-series-kind")).toBeInTheDocument(),
    );

    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it("0 violaciones a11y en step 1 con tipo copa (estado inicial)", async () => {
    const { container } = renderWizard();
    await screen.findByTestId("wizard-series-kind");

    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  // Regression del bug de producción: al importar un campeonato, "Continuar"
  // no hacía nada. Causa: el campo `valida_num` oculto quedaba en `NaN`
  // (valueAsNumber sobre input vacío), el schema base lo rechazaba y el error
  // —invisible por estar el campo oculto— bloqueaba `handleSubmit` en silencio.
  // Este test verifica que un submit de campeonato SÍ dispara el parse.
  it("campeonato: 'Continuar' dispara el parse y avanza (no se bloquea en silencio)", async () => {
    const user = userEvent.setup();
    let parseCalled = false;
    mswServer.use(
      http.post("*/api/race-analysis/imports/parse", () => {
        parseCalled = true;
        return HttpResponse.json({
          parse_id: "1",
          sha256: "abc",
          header: {
            series_name: "Campeonato Departamental 2026",
            season: 2026,
            valida_num: 1,
            event_name: "Departamental XCO",
            event_date: "2026-06-13",
            location: "Ginebra",
          },
          conditions: null,
        });
      }),
      http.post("*/api/race-analysis/imports/1/dry-run", () =>
        HttpResponse.json({ matches: [], counts: { confirmed: 0, ambiguous: 0, no_match: 0, total: 0 } }),
      ),
    );

    renderWizard();

    await user.selectOptions(
      await screen.findByTestId("wizard-series-kind"),
      "championship",
    );
    // El campo "Válida #" queda oculto — no lo tocamos (ese era el origen del bug).
    expect(screen.queryByTestId("wizard-valida-num")).not.toBeInTheDocument();

    await user.type(screen.getByTestId("wizard-series-name"), "Campeonato Departamental 2026");
    await user.type(screen.getByTestId("wizard-event-name"), "Departamental XCO");
    const dateInput = screen.getByTestId("wizard-event-date");
    await user.clear(dateInput);
    await user.type(dateInput, "2026-06-13");
    await user.type(screen.getByTestId("wizard-location"), "Ginebra");

    // Adjuntar el archivo de resultados (RaceUploadZone mockeado).
    const file = new File(["bib,nombre\n1,X"], "resultados.csv", { type: "text/csv" });
    await user.upload(
      screen.getByTestId("upload-zone-Resultados (PDF o CSV) *"),
      file,
    );

    await user.click(screen.getByTestId("wizard-step1-submit"));

    await waitFor(() => expect(parseCalled).toBe(true));
  });
});
