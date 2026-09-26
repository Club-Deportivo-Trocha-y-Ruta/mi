/**
 * ImportWizard — retomar una carga persistida (feature 045, US3).
 *
 * Amendment 2026-09-26 (`contracts/ui-review-only.md`, T159): la app ya no
 * sube archivos — toda carga llega ya stageada y el wizard SIEMPRE arranca
 * desde `?import=<id>`. Cubre:
 *  - `pending` → revisión, `dry_run` → confirmación (mismo paso, copy
 *    distinto).
 *  - `committed` / `discarded` / `failed` / 404 → aviso, sin retomar, con
 *    «Empezar una carga nueva» (navega al tablero).
 *  - Legacy (`restage_required`): aviso propio, solo *Descartar*.
 *  - REGRESIÓN «salir a resolver identidades ya no pierde la carga»: 409
 *    identity_pending → salir por el enlace → volver → retoma sin re-
 *    consultar el dry-run innecesariamente y el commit posterior funciona.
 *  - Descartar con confirmación (POST /discard) y vuelta al tablero.
 *  - Categorías rehidratadas (conteo de filas desde el meta) y a11y (axe).
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Link, MemoryRouter, Route, Routes, useSearchParams } from "react-router-dom";
import { axe } from "jest-axe";
import { http, HttpResponse } from "msw";

vi.mock("@/store/auth.store", () => ({
  useAuthStore: (selector: (s: { accessToken: string }) => unknown) =>
    selector({ accessToken: "test-token" }),
}));
vi.mock("sonner", () => ({
  toast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }),
}));

import { mswServer } from "@/test/setup";
import { makeCommitResponse, makeImportDetail } from "@/test/msw/raceImportsHistoryHandlers";
import { ImportWizard } from "@/components/competitions/import/ImportWizard";
import { formatDateTime } from "@/lib/datetime";
import type {
  ImportDryRunMatchesResponse,
  ImportDryRunRevisionResponse,
} from "@/types/raceImports.types";

const BASE = "*/api/race-analysis/imports";

const DRY_RUN_CONFIRMED_ONLY: ImportDryRunMatchesResponse = {
  parse_id: "7",
  matches: [
    {
      competitor_normalized_name: "ana prueba uno",
      competitor_name: "Ana Prueba Uno",
      tyr_athlete: { id: 1, full_name: "Ana Prueba Uno" },
      confidence: 0.95,
      is_ambiguous: false,
    },
  ],
  counts: { confirmed: 1, ambiguous: 0, no_match: 0, total: 1 },
  warnings: [],
};

/** Handlers base: la carga 7 está `pending` y su dry-run no tiene ambiguos. */
function useBaseHandlers(overrides?: {
  detail?: Parameters<typeof makeImportDetail>[0];
}) {
  const calls = { dryRun: 0, discard: [] as string[] };
  mswServer.use(
    http.get(`${BASE}/7`, () =>
      HttpResponse.json(makeImportDetail({ id: 7, ...overrides?.detail })),
    ),
    http.post(`${BASE}/7/dry-run`, () => {
      calls.dryRun += 1;
      return HttpResponse.json(DRY_RUN_CONFIRMED_ONLY);
    }),
    http.post(`${BASE}/7/discard`, () => {
      calls.discard.push("7");
      return HttpResponse.json(makeImportDetail({ id: 7, status: "discarded" }));
    }),
  );
  return calls;
}

/** Stand-in del tablero: ofrece volver a la carga con `?import=<id>`. */
function BoardStub() {
  const [params] = useSearchParams();
  const importId = params.get("import");
  return (
    <div data-testid="board-stub">
      Tablero
      {importId && (
        <Link to={`/competitions/import?import=${importId}`} data-testid="back-to-import">
          Volver a la carga
        </Link>
      )}
    </div>
  );
}

function renderAt(initialEntry: string) {
  const qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <Routes>
          <Route path="/competitions/import" element={<ImportWizard />} />
          <Route path="/competitions/imports" element={<BoardStub />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("ImportWizard — retomar una carga (feature 045, US3)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("REGRESIÓN: salir a resolver identidades ya no pierde la carga — se retoma sin volver a subir nada", async () => {
    const calls = useBaseHandlers();
    let commitAttempts = 0;
    mswServer.use(
      http.post(`${BASE}/7/commit`, () => {
        commitAttempts += 1;
        return commitAttempts === 1
          ? HttpResponse.json(
              {
                detail: "identity_pending",
                pending_for_import: 2,
                review_path: "/competitions/imports?seccion=identidades&import=7",
              },
              { status: 409 },
            )
          : HttpResponse.json(makeCommitResponse({ parse_id: "7" }));
      }),
    );

    const user = userEvent.setup();
    renderAt("/competitions/import?import=7");

    await waitFor(() =>
      expect(screen.getByTestId("wizard-step2-confirm")).toBeEnabled(),
    );

    // 1) Confirmar → 409 identity_pending con el conteo de ESTA carga.
    await user.click(screen.getByTestId("wizard-step2-confirm"));
    expect(
      await screen.findByTestId("wizard-identity-gate-message"),
    ).toHaveTextContent(
      "Hay 2 decisiones de identidad pendientes para esta carga. Resuélvelas en «Cargas e identidades» y vuelve: tu carga queda guardada.",
    );

    // 2) Salir por el enlace a las decisiones (`review_path`): el wizard se
    //    desmonta y con él TODO su estado en memoria.
    await user.click(screen.getByTestId("wizard-identity-review-link"));
    expect(await screen.findByTestId("board-stub")).toBeInTheDocument();
    expect(screen.queryByTestId("import-wizard")).not.toBeInTheDocument();

    // 3) Volver a la carga: se retoma en el mismo paso, con la carga intacta.
    await user.click(screen.getByTestId("back-to-import"));
    expect(await screen.findByTestId("wizard-resumed-notice")).toHaveTextContent(
      "Retomaste tu carga «valida_1_2026.pdf». El archivo sigue guardado.",
    );
    expect(screen.getByTestId("import-wizard-step2")).toBeInTheDocument();

    // 4) Ya resueltas las decisiones, el commit de la MISMA carga funciona.
    await waitFor(() =>
      expect(screen.getByTestId("wizard-step2-confirm")).toBeEnabled(),
    );
    await user.click(screen.getByTestId("wizard-step2-confirm"));
    expect(await screen.findByTestId("wizard-step3-success")).toBeInTheDocument();
    expect(commitAttempts).toBe(2);
    expect(calls.dryRun).toBe(2); // uno al montar, otro al retomar
  }, 15_000);

  it("?import=<id> en estado pending: retoma con las categorías del meta", async () => {
    const calls = useBaseHandlers();
    renderAt("/competitions/import?import=7");

    expect(await screen.findByTestId("import-wizard-step2")).toBeInTheDocument();
    expect(screen.getByTestId("wizard-resumed-notice")).toHaveTextContent(
      "Revisa las coincidencias y confirma.",
    );
    // El meta persistido solo guarda el CONTEO de filas por categoría.
    expect(screen.getByTestId("category-row-Sub-15 Mujeres")).toHaveTextContent("12");
    expect(screen.getByTestId("category-row-Sub-15 Hombres")).toHaveTextContent("8");
    await waitFor(() => expect(calls.dryRun).toBe(1));
  });

  it("?import=<id> en estado dry_run: retoma en confirmación", async () => {
    useBaseHandlers({ detail: { status: "dry_run" } });
    renderAt("/competitions/import?import=7");

    expect(await screen.findByTestId("wizard-resumed-notice")).toHaveTextContent(
      "Ya se validó: confirma para cargarla.",
    );
    await waitFor(() =>
      expect(screen.getByTestId("wizard-step2-confirm")).toBeEnabled(),
    );
  });

  it("retomar una revisión: el aviso muestra cuándo se importó la versión previa (no «—»)", async () => {
    const parentCommittedAt = "2026-05-17T18:42:00";
    const revisionDryRun: ImportDryRunRevisionResponse = {
      parse_id: "7",
      is_revision: true,
      parent_event_id: 4,
      diff_summary: { n_create: 0, n_update: 1, n_delete: 0, n_unchanged: 19, n_total: 20 },
      diff_rows: [],
      warnings: [],
    };
    mswServer.use(
      http.get(`${BASE}/7`, () =>
        HttpResponse.json(
          makeImportDetail({ id: 7, parent_committed_at: parentCommittedAt }),
        ),
      ),
      http.post(`${BASE}/7/dry-run`, () => HttpResponse.json(revisionDryRun)),
    );
    renderAt("/competitions/import?import=7");

    const banner = await screen.findByTestId("wizard-revision-banner");
    const expected = formatDateTime(parentCommittedAt).replace(/\s+/g, " ");
    expect(expected).not.toBe("");
    expect(banner).toHaveTextContent(`ya fue importada el ${expected}`);
    expect(banner).not.toHaveTextContent("ya fue importada el —");
  });

  it("mientras consulta la carga muestra el estado de retomando (nunca un spinner pelado)", async () => {
    mswServer.use(
      http.get(`${BASE}/7`, async () => {
        await new Promise((resolve) => setTimeout(resolve, 60));
        return HttpResponse.json(makeImportDetail({ id: 7 }));
      }),
      http.post(`${BASE}/7/dry-run`, () => HttpResponse.json(DRY_RUN_CONFIRMED_ONLY)),
    );
    renderAt("/competitions/import?import=7");

    expect(screen.getByTestId("resume-loading")).toHaveTextContent("Retomando tu carga…");
    expect(await screen.findByTestId("import-wizard-step2")).toBeInTheDocument();
  });

  it.each([
    ["committed", "Esta carga ya se confirmó."],
    ["discarded", "Esta carga se descartó."],
    ["failed", "Esta carga no se pudo leer. Sube el archivo de nuevo."],
  ] as const)(
    "carga %s: no se retoma, avisa y ofrece empezar una carga nueva (navega al tablero)",
    async (status, message) => {
      useBaseHandlers({ detail: { status, parse_meta: null } });
      const user = userEvent.setup();
      renderAt("/competitions/import?import=7");

      const notice = await screen.findByTestId("resume-status-notice");
      expect(notice).toHaveTextContent(message);
      expect(screen.queryByTestId("import-wizard-step2")).not.toBeInTheDocument();

      await user.click(screen.getByTestId("resume-start-new"));
      expect(await screen.findByTestId("board-stub")).toBeInTheDocument();
    },
  );

  it("carga confirmada con evento: ofrece ver los resultados", async () => {
    useBaseHandlers({
      detail: { status: "committed", parse_meta: null, event_id: 501 },
    });
    renderAt("/competitions/import?import=7");

    expect(await screen.findByTestId("resume-view-results")).toHaveAttribute(
      "href",
      "/competitions/501?tab=results",
    );
  });

  it("carga inexistente o de otro club (404): avisa sin exponer más y permite volver al tablero", async () => {
    mswServer.use(
      http.get(`${BASE}/7`, () =>
        HttpResponse.json({ detail: "no existe" }, { status: 404 }),
      ),
    );
    const user = userEvent.setup();
    renderAt("/competitions/import?import=7");

    const notice = await screen.findByRole("alert");
    expect(notice).toHaveTextContent("No encontramos esa carga.");
    await user.click(within(notice).getByTestId("resume-start-new"));
    expect(await screen.findByTestId("board-stub")).toBeInTheDocument();
  });

  it("descartar: pide confirmación, llama a POST /discard y navega al tablero", async () => {
    const calls = useBaseHandlers();
    const user = userEvent.setup();
    renderAt("/competitions/import?import=7");

    await user.click(await screen.findByTestId("wizard-discard"));
    const dialog = await screen.findByTestId("discard-import-dialog");
    expect(calls.discard).toEqual([]);
    expect(dialog).toHaveTextContent("valida_1_2026.pdf");

    await user.click(within(dialog).getByTestId("confirm-discard-import"));
    await waitFor(() => expect(calls.discard).toEqual(["7"]));

    expect(await screen.findByTestId("board-stub")).toBeInTheDocument();
  });

  it("descartar: cancelar el diálogo conserva la carga", async () => {
    const calls = useBaseHandlers();
    const user = userEvent.setup();
    renderAt("/competitions/import?import=7");

    await user.click(await screen.findByTestId("wizard-discard"));
    const dialog = await screen.findByTestId("discard-import-dialog");
    await user.click(within(dialog).getByRole("button", { name: "Cancelar" }));

    await waitFor(() =>
      expect(screen.queryByTestId("discard-import-dialog")).not.toBeInTheDocument(),
    );
    expect(calls.discard).toEqual([]);
    expect(screen.getByTestId("import-wizard-step2")).toBeInTheDocument();
  });

  // ---------------------------------------------------------------------------
  // Amendment 2026-09-26 — carga legacy (`restage_required`, C2 / T158-adjacent)
  // ---------------------------------------------------------------------------

  it("carga legacy (restage_required): muestra el aviso propio y solo ofrece Descartar", async () => {
    mswServer.use(
      http.get(`${BASE}/7`, () =>
        HttpResponse.json(makeImportDetail({ id: 7, restage_required: true })),
      ),
    );
    renderAt("/competitions/import?import=7");

    const notice = await screen.findByTestId("resume-status-notice");
    expect(notice).toHaveTextContent(
      "Esta carga se preparó con el método anterior y ya no se puede revisar. Descártala y pide que se prepare de nuevo.",
    );
    expect(screen.queryByTestId("resume-start-new")).not.toBeInTheDocument();
    expect(screen.getByTestId("resume-legacy-discard")).toBeInTheDocument();
  });

  it("carga legacy: descartar navega al tablero", async () => {
    mswServer.use(
      http.get(`${BASE}/7`, () =>
        HttpResponse.json(makeImportDetail({ id: 7, restage_required: true })),
      ),
      http.post(`${BASE}/7/discard`, () =>
        HttpResponse.json(
          makeImportDetail({ id: 7, status: "discarded", restage_required: true }),
        ),
      ),
    );
    const user = userEvent.setup();
    renderAt("/competitions/import?import=7");

    await user.click(await screen.findByTestId("resume-legacy-discard"));
    const dialog = await screen.findByTestId("discard-import-dialog");
    await user.click(within(dialog).getByTestId("confirm-discard-import"));

    expect(await screen.findByTestId("board-stub")).toBeInTheDocument();
  });

  it("a11y: cero violaciones en la carga legacy", async () => {
    mswServer.use(
      http.get(`${BASE}/7`, () =>
        HttpResponse.json(makeImportDetail({ id: 7, restage_required: true })),
      ),
    );
    const { container } = renderAt("/competitions/import?import=7");
    await screen.findByTestId("resume-status-notice");
    expect(await axe(container)).toHaveNoViolations();
  });

  // ---------------------------------------------------------------------------
  // a11y — jest-axe (C2, análisis 044): la revisión (`?import=<id>`) y el
  // diálogo de descarte deben quedar en cero violaciones.
  // ---------------------------------------------------------------------------

  it("a11y: cero violaciones en la revisión retomada", async () => {
    useBaseHandlers();
    const { container } = renderAt("/competitions/import?import=7");
    await screen.findByTestId("wizard-resumed-notice");
    await waitFor(() =>
      expect(screen.getByTestId("wizard-step2-confirm")).toBeEnabled(),
    );
    expect(await axe(container)).toHaveNoViolations();
  });

  it("a11y: cero violaciones en el diálogo de descartar (DiscardImportDialog)", async () => {
    useBaseHandlers();
    const user = userEvent.setup();
    renderAt("/competitions/import?import=7");
    await user.click(await screen.findByTestId("wizard-discard"));
    await screen.findByTestId("discard-import-dialog");
    // El diálogo vive en un portal: se audita el documento completo.
    expect(await axe(document.body)).toHaveNoViolations();
  });

  it("a11y: cero violaciones en el aviso de una carga que no se puede retomar", async () => {
    useBaseHandlers({ detail: { status: "committed", parse_meta: null } });
    const { container } = renderAt("/competitions/import?import=7");
    await screen.findByTestId("resume-status-notice");
    expect(await axe(container)).toHaveNoViolations();
  });
});
