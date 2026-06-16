/**
 * T012 — spec 014 Cup vs Championship
 * CompetitionFormPage — ruta campeonato (US1) y sin serie por defecto (US2).
 *
 * Cubre:
 *  - US1/T012: selector "Tipo de competencia" presente y funcional.
 *  - US1/T012: cambiar a "Campeonato" oculta el campo "Número de válida".
 *  - US1/T012: payload de submit para campeonato omite sequence_number.
 *  - US2/T016: sin serie pre-seleccionada al abrir el formulario.
 *  - US2/T016: campo round condicional al kind (presente para copa, ausente para campeonato).
 *  - US2/T016: modo edit de un campeonato no revierte a copa con número de válida.
 *  - 0 violaciones a11y (jest-axe) en create vacío con campeonato seleccionado.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { http, HttpResponse } from "msw";

// Mock de auth.store (patrón del repo).
vi.mock("@/store/auth.store", () => ({
  useAuthStore: vi.fn((sel: (s: unknown) => unknown) =>
    sel({
      accessToken: "test-token",
      user: { id: 1, role: "coach", first_name: "Entrenador", last_name: "Ficticio" },
      isAuthenticated: true,
    }),
  ),
}));

const mockNavigate = vi.fn();
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>(
    "react-router-dom",
  );
  return { ...actual, useNavigate: () => mockNavigate };
});

import { mswServer } from "@/test/setup";
import {
  makeRaceEventRead,
  raceEventsHandlers,
} from "@/test/msw/raceEventsHandlers";
import {
  raceSeriesHandlers,
  makeRaceSeriesRead,
  makeChampionshipSeriesRead,
} from "@/test/msw/raceSeriesHandlers";
import { CompetitionFormPage } from "@/routes/competitions/CompetitionFormPage";

// ---------------------------------------------------------------------------
// Helper: render del formulario
// ---------------------------------------------------------------------------

function renderForm(
  mode: "create" | "edit",
  initialEntry = mode === "edit" ? "/competitions/1/edit" : "/competitions/new",
) {
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
          <Route
            path="/competitions/new"
            element={<CompetitionFormPage mode="create" />}
          />
          <Route
            path="/competitions/:id/edit"
            element={<CompetitionFormPage mode={mode} />}
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

// ---------------------------------------------------------------------------
// Setup
// ---------------------------------------------------------------------------

beforeEach(() => {
  vi.clearAllMocks();
  // Handlers base: race-events + race-series (dinámico por kind).
  mswServer.use(...raceEventsHandlers, ...raceSeriesHandlers);
});

// ---------------------------------------------------------------------------
// US1 (T012) — selector de tipo + campo válida oculto para campeonato
// ---------------------------------------------------------------------------

describe("CompetitionFormPage spec-014 — US1: championship path", () => {
  it("muestra el selector 'Tipo de competencia' con opción Copa y Campeonato", async () => {
    renderForm("create");

    // El selector de tipo siempre está presente en create.
    const kindSelect = await screen.findByLabelText(/Tipo de competencia/i);
    expect(kindSelect).toBeInTheDocument();
    expect(kindSelect).toHaveDisplayValue(/Copa/i);

    // Ambas opciones accesibles en el DOM.
    const options = Array.from(
      (kindSelect as HTMLSelectElement).options,
    ).map((o) => o.value);
    expect(options).toContain("cup");
    expect(options).toContain("championship");
  });

  it("en create (copa por defecto) muestra el campo 'Número de válida'", async () => {
    renderForm("create");
    await screen.findByLabelText(/Tipo de competencia/i);
    // El campo de número de válida debe estar presente para copa.
    expect(screen.getByLabelText(/Número de válida/i)).toBeInTheDocument();
  });

  it("al cambiar a 'Campeonato' oculta completamente el campo 'Número de válida'", async () => {
    const user = userEvent.setup();
    renderForm("create");

    const kindSelect = await screen.findByLabelText(/Tipo de competencia/i);
    // Cambiamos a campeonato.
    await user.selectOptions(kindSelect, "championship");

    // El campo de número de válida NO debe existir.
    await waitFor(() =>
      expect(screen.queryByLabelText(/Número de válida/i)).not.toBeInTheDocument(),
    );
  });

  it("al cambiar a Campeonato muestra el picker de serie (cargando series de tipo championship)", async () => {
    const user = userEvent.setup();
    renderForm("create");

    const kindSelect = await screen.findByLabelText(/Tipo de competencia/i);
    await user.selectOptions(kindSelect, "championship");

    // Debe aparecer la serie de campeonato en el picker.
    await waitFor(() =>
      expect(
        screen.queryByText(/Campeonato Departamental 2026/i),
      ).toBeInTheDocument(),
    );
  });

  it("payload de submit para campeonato omite sequence_number y usa series_id correcto", async () => {
    // Devolvemos la serie de campeonato para que el picker tenga un item.
    mswServer.use(
      http.get("*/api/race-analysis/race-series", ({ request }) => {
        const url = new URL(request.url);
        const kind = url.searchParams.get("kind");
        if (kind === "championship") {
          return HttpResponse.json({
            items: [makeChampionshipSeriesRead({ id: 9 })],
            total: 1,
          });
        }
        return HttpResponse.json({ items: [makeRaceSeriesRead({ id: 2 })], total: 1 });
      }),
    );

    let capturedBody: unknown = null;
    mswServer.use(
      http.post("*/api/race-analysis/race-events/", async ({ request }) => {
        capturedBody = await request.json();
        return HttpResponse.json(makeRaceEventRead({ id: 77 }), { status: 201 });
      }),
    );

    const user = userEvent.setup();
    renderForm("create");

    // Seleccionamos campeonato.
    const kindSelect = await screen.findByLabelText(/Tipo de competencia/i);
    await user.selectOptions(kindSelect, "championship");

    // Esperamos que cargue la serie de campeonato.
    const seriesSelect = await screen.findByLabelText(/Serie/i);
    await waitFor(() =>
      expect(
        Array.from((seriesSelect as HTMLSelectElement).options).some(
          (o) => o.value === "9",
        ),
      ).toBe(true),
    );
    await user.selectOptions(seriesSelect, "9");

    // Rellenamos campos obligatorios.
    await user.type(screen.getByLabelText("Nombre"), "Campeonato Departamental · Ginebra");
    await user.type(screen.getByLabelText("Fecha"), "2026-06-12");

    await user.click(
      screen.getByRole("button", { name: /Crear competencia/i }),
    );

    await waitFor(() => expect(capturedBody).not.toBeNull());

    // Para campeonato: NO debe incluir sequence_number.
    expect(capturedBody).not.toHaveProperty("sequence_number");
    // Sí debe incluir series_id = 9.
    expect(capturedBody).toMatchObject({
      series_id: 9,
      name: "Campeonato Departamental · Ginebra",
      event_date: "2026-06-12",
    });
  });

  it("navigate al detalle tras crear un campeonato exitosamente", async () => {
    mswServer.use(
      http.get("*/api/race-analysis/race-series", ({ request }) => {
        const url = new URL(request.url);
        if (url.searchParams.get("kind") === "championship") {
          return HttpResponse.json({ items: [makeChampionshipSeriesRead({ id: 9 })], total: 1 });
        }
        return HttpResponse.json({ items: [makeRaceSeriesRead()], total: 1 });
      }),
      http.post("*/api/race-analysis/race-events/", () =>
        HttpResponse.json(makeRaceEventRead({ id: 88, is_championship: true }), {
          status: 201,
        }),
      ),
    );

    const user = userEvent.setup();
    renderForm("create");

    const kindSelect = await screen.findByLabelText(/Tipo de competencia/i);
    await user.selectOptions(kindSelect, "championship");

    const seriesSelect = await screen.findByLabelText(/Serie/i);
    await waitFor(() =>
      expect(
        Array.from((seriesSelect as HTMLSelectElement).options).some((o) => o.value === "9"),
      ).toBe(true),
    );
    await user.selectOptions(seriesSelect, "9");

    await user.type(screen.getByLabelText("Nombre"), "CD Departamental");
    await user.type(screen.getByLabelText("Fecha"), "2026-06-12");

    await user.click(
      screen.getByRole("button", { name: /Crear competencia/i }),
    );

    await waitFor(() =>
      expect(mockNavigate).toHaveBeenCalledWith("/competitions/88"),
    );
  });

  it("0 violaciones a11y en formulario create con tipo campeonato seleccionado", async () => {
    const user = userEvent.setup();
    const { container } = renderForm("create");

    const kindSelect = await screen.findByLabelText(/Tipo de competencia/i);
    await user.selectOptions(kindSelect, "championship");

    // Esperamos que el selector de series esté listo.
    await waitFor(() =>
      expect(screen.queryByText(/Cargando series/i)).not.toBeInTheDocument(),
    );

    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});

// ---------------------------------------------------------------------------
// US2 (T016) — sin serie por defecto; round condicional; edit mode campeonato
// ---------------------------------------------------------------------------

describe("CompetitionFormPage spec-014 — US2: no default series, conditional round", () => {
  it("en create no hay ninguna serie preseleccionada — el picker está en 'Selecciona una serie…'", async () => {
    renderForm("create");
    await screen.findByLabelText(/Tipo de competencia/i);

    // La lista de series copa debe cargarse; el valor seleccionado debe ser
    // el placeholder (value=0, disabled).
    const seriesSelect = await screen.findByLabelText(/Serie/i);
    expect((seriesSelect as HTMLSelectElement).value).toBe("0");
  });

  it("en create tipo=copa muestra el campo Número de válida", async () => {
    renderForm("create");
    await screen.findByLabelText(/Tipo de competencia/i);
    // Copa es el valor por defecto → el campo de válida debe estar presente.
    expect(await screen.findByLabelText(/Número de válida/i)).toBeInTheDocument();
  });

  it("en create tipo=campeonato NO hay campo Número de válida", async () => {
    const user = userEvent.setup();
    renderForm("create");

    const kindSelect = await screen.findByLabelText(/Tipo de competencia/i);
    await user.selectOptions(kindSelect, "championship");

    await waitFor(() =>
      expect(screen.queryByLabelText(/Número de válida/i)).not.toBeInTheDocument(),
    );
  });

  it("volver a copa desde campeonato restaura el campo Número de válida", async () => {
    const user = userEvent.setup();
    renderForm("create");

    const kindSelect = await screen.findByLabelText(/Tipo de competencia/i);
    // Copa → campeonato → copa
    await user.selectOptions(kindSelect, "championship");
    await waitFor(() =>
      expect(screen.queryByLabelText(/Número de válida/i)).not.toBeInTheDocument(),
    );
    await user.selectOptions(kindSelect, "cup");
    expect(await screen.findByLabelText(/Número de válida/i)).toBeInTheDocument();
  });

  it("modo edit: un campeonato preexistente no muestra el campo Número de válida", async () => {
    // El evento id=1 se carga como campeonato (is_championship=true).
    mswServer.use(
      http.get("*/api/race-analysis/race-events/1", () =>
        HttpResponse.json(
          makeRaceEventRead({
            id: 1,
            is_championship: true,
            sequence_number: 1,
            name: "Campeonato Departamental · Ginebra",
            event_date: "2026-06-12",
          }),
        ),
      ),
      // El picker de series carga series de tipo championship.
      http.get("*/api/race-analysis/race-series", () =>
        HttpResponse.json({
          items: [makeChampionshipSeriesRead({ id: 9 })],
          total: 1,
        }),
      ),
    );

    renderForm("edit");

    // Esperamos que el formulario cargue el evento.
    await waitFor(() =>
      expect(
        (screen.getByLabelText("Nombre") as HTMLInputElement).value,
      ).toBe("Campeonato Departamental · Ginebra"),
    );

    // El campo Número de válida NO debe aparecer para un campeonato en edit.
    expect(screen.queryByLabelText(/Número de válida/i)).not.toBeInTheDocument();
  });

  it("modo edit: el selector de tipo está deshabilitado (no se puede cambiar kind)", async () => {
    mswServer.use(
      http.get("*/api/race-analysis/race-events/1", () =>
        HttpResponse.json(
          makeRaceEventRead({
            id: 1,
            is_championship: true,
            name: "CD Test",
            event_date: "2026-06-12",
          }),
        ),
      ),
      http.get("*/api/race-analysis/race-series", () =>
        HttpResponse.json({ items: [makeChampionshipSeriesRead()], total: 1 }),
      ),
    );

    renderForm("edit");
    await waitFor(() =>
      expect(
        (screen.getByLabelText("Nombre") as HTMLInputElement).value,
      ).toBe("CD Test"),
    );

    const kindSelect = screen.getByLabelText(/Tipo de competencia/i) as HTMLSelectElement;
    // En modo edit el kind no se puede cambiar — debe estar disabled.
    expect(kindSelect).toBeDisabled();
  });

  it("0 violaciones a11y en create vacío (tipo copa, estado inicial)", async () => {
    const { container } = renderForm("create");
    await screen.findByLabelText(/Tipo de competencia/i);
    // Esperamos que el picker de series cargue.
    await waitFor(() =>
      expect(screen.queryByText(/Cargando series/i)).not.toBeInTheDocument(),
    );
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
