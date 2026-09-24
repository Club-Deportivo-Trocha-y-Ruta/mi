/**
 * ImportWizard — retomar una carga persistida (feature 045, US3, T054).
 *
 * Contexto: antes, salir del wizard a resolver identidades (o recargar la
 * página) perdía la carga — el estado vivía solo en memoria y había que
 * volver a subir el PDF. Ahora la carga vive en el servidor: el wizard escribe
 * `?import=<id>` al parsear y, si llega con ese parámetro, la retoma en el
 * paso 2 sin subir nada.
 *
 * Cubre:
 *  - REGRESIÓN «salir ya no pierde la carga»: parsear → 409 identity_pending →
 *    salir por el enlace → volver → el wizard retoma en el paso 2 SIN volver a
 *    llamar a /parse, y el commit posterior funciona.
 *  - `pending` → revisión, `dry_run` → confirmación (mismo paso, copy distinto).
 *  - `committed` / `discarded` / 404 → aviso, sin retomar, con «Empezar una
 *    carga nueva».
 *  - Descartar con confirmación (POST /discard) y volver al paso 1.
 *  - Categorías rehidratadas (conteo de filas desde el meta) y a11y (axe).
 *
 * Solo `parseRaceImport` (multipart) se simula; dry-run, commit, detalle y
 * descarte pasan por axios real + MSW. Datos sintéticos.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  Link,
  MemoryRouter,
  Route,
  Routes,
  useLocation,
  useSearchParams,
} from "react-router-dom";
import { axe } from "jest-axe";
import { http, HttpResponse } from "msw";

vi.mock("@/api/raceImports", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/raceImports")>();
  return { ...actual, parseRaceImport: vi.fn() };
});
vi.mock("@/store/auth.store", () => ({
  useAuthStore: (selector: (s: { accessToken: string }) => unknown) =>
    selector({ accessToken: "test-token" }),
}));
vi.mock("sonner", () => ({
  toast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }),
}));

import * as importsApi from "@/api/raceImports";
import { mswServer } from "@/test/setup";
import {
  identityPendingBody,
  makeCommitResponse,
  makeImportDetail,
} from "@/test/msw/raceImportsHistoryHandlers";
import { ImportWizard } from "@/components/competitions/import/ImportWizard";
import { formatDateTime } from "@/lib/datetime";
import type {
  ImportDryRunMatchesResponse,
  ImportDryRunRevisionResponse,
  ImportParseResponse,
} from "@/types/raceImports.types";

const BASE = "*/api/race-analysis/imports";

const PARSE_RESPONSE: ImportParseResponse = {
  parse_id: "7",
  sha256: "abcd",
  header: {
    series_name: "Copa Valle de Ciclomontañismo",
    season: 2026,
    valida_num: 1,
    event_name: "Válida I — Ciudad Prueba",
  },
  n_rows_resultados: 20,
  n_rows_general: 0,
  warnings: [],
};

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

function LocationProbe() {
  const location = useLocation();
  return (
    <div data-testid="loc">
      {location.pathname}
      {location.search}
    </div>
  );
}

/** Stand-in de «Cargas e identidades»: ofrece volver a la carga con ?import. */
function IdentitiesStub() {
  const [params] = useSearchParams();
  return (
    <div data-testid="identities-page">
      <Link
        to={`/competitions/import?import=${params.get("import")}`}
        data-testid="back-to-import"
      >
        Volver a la carga
      </Link>
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
        <LocationProbe />
        <Routes>
          <Route path="/competitions/import" element={<ImportWizard />} />
          <Route path="/competitions/imports" element={<IdentitiesStub />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function makeValidPdf(name = "valida_1_2026.pdf"): File {
  const header = new TextEncoder().encode("%PDF-1.4\n");
  return new File([header, new Uint8Array(512)], name, {
    type: "application/pdf",
  });
}

async function fillStep1AndSubmit(user: ReturnType<typeof userEvent.setup>) {
  await user.type(
    screen.getByTestId("wizard-series-name"),
    "Copa Valle de Ciclomontañismo",
  );
  fireEvent.change(screen.getByTestId("wizard-valida-num"), {
    target: { value: "1" },
  });
  await user.type(
    screen.getByTestId("wizard-event-name"),
    "Válida I — Ciudad Prueba",
  );
  fireEvent.change(screen.getByTestId("wizard-event-date"), {
    target: { value: "2026-03-15" },
  });
  await user.type(screen.getByTestId("wizard-location"), "Ciudad Prueba");

  const input = screen.getByTestId(
    "race-upload-resultados-input",
  ) as HTMLInputElement;
  Object.defineProperty(input, "files", { value: [makeValidPdf()] });
  fireEvent.change(input);
  await waitFor(() =>
    expect(
      screen.getByTestId("race-upload-resultados-preview"),
    ).toBeInTheDocument(),
  );
  await user.click(screen.getByTestId("wizard-step1-submit"));
}

describe("ImportWizard — retomar una carga (feature 045, US3)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("REGRESIÓN: salir a resolver identidades ya no pierde la carga — se retoma sin volver a subir el archivo", async () => {
    vi.mocked(importsApi.parseRaceImport).mockResolvedValue(PARSE_RESPONSE);
    const calls = useBaseHandlers();
    let commitAttempts = 0;
    mswServer.use(
      http.post(`${BASE}/7/commit`, () => {
        commitAttempts += 1;
        // 1.er intento: hay decisiones de identidad de ESTA carga por resolver.
        // 2.º intento (tras resolverlas y volver): la carga se confirma.
        return commitAttempts === 1
          ? HttpResponse.json(identityPendingBody(7, 2), { status: 409 })
          : HttpResponse.json(makeCommitResponse({ parse_id: "7" }));
      }),
    );

    const user = userEvent.setup();
    renderAt("/competitions/import");

    // 1) Subir y parsear: el wizard deja `?import=7` en la URL.
    await fillStep1AndSubmit(user);
    await waitFor(() =>
      expect(screen.getByTestId("wizard-step2-confirm")).toBeEnabled(),
    );
    expect(screen.getByTestId("loc")).toHaveTextContent(
      "/competitions/import?import=7",
    );
    expect(importsApi.parseRaceImport).toHaveBeenCalledTimes(1);

    // 2) Confirmar → 409 identity_pending con el conteo de ESTA carga.
    await user.click(screen.getByTestId("wizard-step2-confirm"));
    expect(
      await screen.findByTestId("wizard-identity-gate-message"),
    ).toHaveTextContent(
      "Hay 2 decisiones de identidad pendientes para esta carga. Resuélvelas en «Cargas e identidades» y vuelve: tu carga queda guardada.",
    );

    // 3) Salir por el enlace a las decisiones (`review_path`): el wizard se
    //    desmonta y con él TODO su estado en memoria.
    await user.click(screen.getByTestId("wizard-identity-review-link"));
    expect(await screen.findByTestId("identities-page")).toBeInTheDocument();
    expect(screen.queryByTestId("import-wizard")).not.toBeInTheDocument();
    expect(screen.getByTestId("loc")).toHaveTextContent(
      "/competitions/imports?seccion=identidades&import=7",
    );

    // 4) Volver a la carga: se retoma en el paso 2, con el archivo intacto.
    await user.click(screen.getByTestId("back-to-import"));
    expect(await screen.findByTestId("wizard-resumed-notice")).toHaveTextContent(
      "Retomaste tu carga «valida_1_2026.pdf». El archivo sigue guardado.",
    );
    expect(screen.getByTestId("import-wizard-step2")).toBeInTheDocument();
    // El formulario del paso 1 NUNCA reaparece: no hay que volver a subir nada.
    expect(screen.queryByTestId("wizard-step1-submit")).not.toBeInTheDocument();
    expect(importsApi.parseRaceImport).toHaveBeenCalledTimes(1);

    // 5) Ya resueltas las decisiones, el commit de la MISMA carga funciona.
    await waitFor(() =>
      expect(screen.getByTestId("wizard-step2-confirm")).toBeEnabled(),
    );
    await user.click(screen.getByTestId("wizard-step2-confirm"));
    expect(await screen.findByTestId("wizard-step3-success")).toBeInTheDocument();
    expect(commitAttempts).toBe(2);
    expect(calls.dryRun).toBe(2); // uno al parsear, otro al retomar
    // Carga confirmada: el parámetro ya no apunta a una carga en curso.
    expect(screen.getByTestId("loc")).not.toHaveTextContent("import=");
    // Flujo largo (parseo → 409 → salir → volver → commit): con la suite
    // completa en paralelo supera el timeout por defecto de 5 s.
  }, 15_000);

  it("?import=<id> en estado pending: retoma en el paso 2 (revisión) con las categorías del meta", async () => {
    const calls = useBaseHandlers();
    renderAt("/competitions/import?import=7");

    expect(await screen.findByTestId("import-wizard-step2")).toBeInTheDocument();
    expect(screen.getByTestId("wizard-resumed-notice")).toHaveTextContent(
      "Revisa las coincidencias y confirma.",
    );
    // El meta persistido solo guarda el CONTEO de filas por categoría.
    expect(screen.getByTestId("category-row-Sub-15 Mujeres")).toHaveTextContent(
      "12",
    );
    expect(screen.getByTestId("category-row-Sub-15 Hombres")).toHaveTextContent(
      "8",
    );
    await waitFor(() => expect(calls.dryRun).toBe(1));
    expect(importsApi.parseRaceImport).not.toHaveBeenCalled();
  });

  it("?import=<id> en estado dry_run: retoma en el paso 2 (confirmación)", async () => {
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
    // Intl separa la hora de «p. m.» con espacios no separables; el DOM que
    // compara Testing Library ya viene con los espacios normalizados.
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
      http.post(`${BASE}/7/dry-run`, () =>
        HttpResponse.json(DRY_RUN_CONFIRMED_ONLY),
      ),
    );
    renderAt("/competitions/import?import=7");

    expect(screen.getByTestId("resume-loading")).toHaveTextContent(
      "Retomando tu carga…",
    );
    expect(screen.queryByTestId("wizard-step1-submit")).not.toBeInTheDocument();
    expect(await screen.findByTestId("import-wizard-step2")).toBeInTheDocument();
  });

  it.each([
    ["committed", "Esta carga ya se confirmó."],
    ["discarded", "Esta carga se descartó."],
    ["failed", "Esta carga no se pudo leer. Sube el archivo de nuevo."],
  ] as const)(
    "carga %s: no se retoma, avisa y ofrece empezar una carga nueva",
    async (status, message) => {
      useBaseHandlers({ detail: { status, parse_meta: null } });
      const user = userEvent.setup();
      renderAt("/competitions/import?import=7");

      const notice = await screen.findByTestId("resume-status-notice");
      expect(notice).toHaveTextContent(message);
      expect(screen.queryByTestId("import-wizard-step2")).not.toBeInTheDocument();
      expect(screen.queryByTestId("wizard-step1-submit")).not.toBeInTheDocument();

      await user.click(screen.getByTestId("resume-start-new"));
      expect(await screen.findByTestId("wizard-step1-submit")).toBeInTheDocument();
      expect(screen.getByTestId("loc")).not.toHaveTextContent("import=");
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

  it("carga inexistente o de otro club (404): avisa sin exponer más y permite empezar de nuevo", async () => {
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
    expect(await screen.findByTestId("wizard-step1-submit")).toBeInTheDocument();
  });

  it("descartar: pide confirmación, llama a POST /discard y vuelve al paso 1 sin ?import", async () => {
    const calls = useBaseHandlers();
    const user = userEvent.setup();
    renderAt("/competitions/import?import=7");

    await user.click(await screen.findByTestId("wizard-discard"));
    const dialog = await screen.findByTestId("discard-import-dialog");
    // Descartar es destructivo: hasta confirmar no se llama al servidor.
    expect(calls.discard).toEqual([]);
    expect(dialog).toHaveTextContent("valida_1_2026.pdf");

    await user.click(within(dialog).getByTestId("confirm-discard-import"));
    await waitFor(() => expect(calls.discard).toEqual(["7"]));

    expect(await screen.findByTestId("wizard-step1-submit")).toBeInTheDocument();
    expect(screen.getByTestId("loc")).not.toHaveTextContent("import=");
    expect(screen.queryByTestId("resume-status-notice")).not.toBeInTheDocument();
  });

  it("descartar: cancelar el diálogo conserva la carga", async () => {
    const calls = useBaseHandlers();
    const user = userEvent.setup();
    renderAt("/competitions/import?import=7");

    await user.click(await screen.findByTestId("wizard-discard"));
    const dialog = await screen.findByTestId("discard-import-dialog");
    await user.click(within(dialog).getByRole("button", { name: "Cancelar" }));

    await waitFor(() =>
      expect(
        screen.queryByTestId("discard-import-dialog"),
      ).not.toBeInTheDocument(),
    );
    expect(calls.discard).toEqual([]);
    expect(screen.getByTestId("import-wizard-step2")).toBeInTheDocument();
    expect(screen.getByTestId("loc")).toHaveTextContent("import=7");
  });

  it("a11y: cero violaciones en el paso 2 retomado", async () => {
    useBaseHandlers();
    const { container } = renderAt("/competitions/import?import=7");
    await screen.findByTestId("wizard-resumed-notice");
    await waitFor(() =>
      expect(screen.getByTestId("wizard-step2-confirm")).toBeEnabled(),
    );
    expect(await axe(container)).toHaveNoViolations();
  });

  it("a11y: cero violaciones en el diálogo de descartar", async () => {
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
