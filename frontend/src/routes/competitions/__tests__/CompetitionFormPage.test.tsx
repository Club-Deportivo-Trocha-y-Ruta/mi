/**
 * Tests para CompetitionFormPage — modo create y edit.
 *
 * Cubre:
 *  - mode=create: submit valido → POST → navigate al detalle.
 *  - mode=edit: precarga valores desde useRaceEvent.
 *  - Auto-altitud: seleccionar Cali pone 1000 msnm.
 *  - Validacion Zod: name vacio impide submit y muestra error inline.
 *  - Error 409 (sequence_number duplicado) → mensaje inline en el campo.
 *  - ?returnTo=... → navigate a esa URL tras success.
 *  - mode=edit + cambio status=cancelled → banner aparece.
 *  - 0 violaciones a11y (create vacio).
 *
 * Spec 023 — National Championship Level (T008):
 *  - tipo=Campeonato + form inline de crear serie abierto → select de nivel
 *    visible (Departamental/Nacional), default Departamental.
 *  - tipo=Copa → el select de nivel no existe.
 *  - Crear serie con Nacional → payload de la mutación incluye level:"national".
 *  - 0 violaciones a11y con el select de nivel visible.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { http, HttpResponse } from "msw";

vi.mock("@/store/auth.store", () => ({
  useAuthStore: vi.fn((sel: (s: unknown) => unknown) =>
    sel({
      accessToken: "test-token",
      user: { id: 1, role: "coach", first_name: "C", last_name: "T" },
      isAuthenticated: true,
    }),
  ),
}));

const mockNavigate = vi.fn();
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>(
    "react-router-dom",
  );
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

import { mswServer } from "@/test/setup";
import {
  makeRaceEventRead,
  raceEventsHandlers,
  raceEventsCreateConflictHandler,
} from "@/test/msw/raceEventsHandlers";
import {
  raceSeriesHandlers,
  raceSeriesEmptyHandler,
} from "@/test/msw/raceSeriesHandlers";
import { CompetitionFormPage } from "@/routes/competitions/CompetitionFormPage";

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

beforeEach(() => {
  vi.clearAllMocks();
  // Spec 014: el picker de serie es requerido. Registramos los handlers de
  // race-series para que el select cargue la lista (copa por defecto, id=2).
  mswServer.use(...raceEventsHandlers, ...raceSeriesHandlers);
});

describe("CompetitionFormPage — mode=create", () => {
  it("submit valido → POST → navigate al detalle del id devuelto", async () => {
    let receivedBody: unknown = null;
    mswServer.use(
      http.post("*/api/race-analysis/race-events/", async ({ request }) => {
        receivedBody = await request.json();
        return HttpResponse.json(makeRaceEventRead({ id: 555 }), {
          status: 201,
        });
      }),
    );
    const user = userEvent.setup();
    renderForm("create");

    // Spec 014: el picker de serie es requerido. Esperamos que cargue y
    // seleccionamos la copa (id=2 según raceSeriesHandlers).
    const seriesSelect = await screen.findByLabelText(/Serie/i);
    await waitFor(() =>
      expect(
        Array.from((seriesSelect as HTMLSelectElement).options).some(
          (o) => o.value === "2",
        ),
      ).toBe(true),
    );
    await user.selectOptions(seriesSelect, "2");

    // Llenamos el form (sequence_number=4, name vacio se auto-sugiere)
    await user.selectOptions(screen.getByLabelText("Número de válida"), "4");
    await user.type(screen.getByLabelText("Nombre"), "Válida 4 · Cali");
    await user.selectOptions(screen.getByLabelText(/Sede/), "Cali");

    const dateInput = screen.getByLabelText("Fecha");
    // El input type=date acepta YYYY-MM-DD directamente.
    await user.type(dateInput, "2026-05-17");

    await user.click(
      screen.getByRole("button", { name: /Crear competencia/i }),
    );

    await waitFor(() => expect(receivedBody).not.toBeNull());
    expect(receivedBody).toMatchObject({
      sequence_number: 4,
      name: "Válida 4 · Cali",
      event_date: "2026-05-17",
      location: "Cali",
    });
    await waitFor(() =>
      expect(mockNavigate).toHaveBeenCalledWith("/competitions/555"),
    );
  });

  it("seleccionar Cali auto-completa altitud=1000 msnm en campo readonly", async () => {
    const user = userEvent.setup();
    renderForm("create");
    await user.selectOptions(screen.getByLabelText(/Sede/), "Cali");

    const altitudInput = (await screen.findByLabelText(
      /Altitud en metros sobre el nivel del mar/i,
    )) as HTMLInputElement;
    expect(altitudInput.value).toBe("1000");
    expect(altitudInput).toHaveAttribute("readOnly");
  });

  it("validacion Zod: name vacio sin auto-sugerencia muestra error inline", async () => {
    const user = userEvent.setup();
    renderForm("create");
    // Submit directamente sin sede (no se auto-completa name).
    // Aseguramos que el name esté realmente vacío.
    const nameInput = screen.getByLabelText("Nombre") as HTMLInputElement;
    expect(nameInput.value).toBe("");
    await user.type(screen.getByLabelText("Fecha"), "2026-05-17");
    await user.click(
      screen.getByRole("button", { name: /Crear competencia/i }),
    );
    expect(
      await screen.findByText(/El nombre es obligatorio/i),
    ).toBeInTheDocument();
  });

  it("error 409 → mensaje inline en el campo sequence_number", async () => {
    mswServer.use(raceEventsCreateConflictHandler);
    const user = userEvent.setup();
    renderForm("create");

    // Spec 014: seleccionar serie (requerida) antes de submit.
    const seriesSelect = await screen.findByLabelText(/Serie/i);
    await waitFor(() =>
      expect(
        Array.from((seriesSelect as HTMLSelectElement).options).some(
          (o) => o.value === "2",
        ),
      ).toBe(true),
    );
    await user.selectOptions(seriesSelect, "2");

    await user.selectOptions(screen.getByLabelText("Número de válida"), "4");
    await user.type(screen.getByLabelText("Nombre"), "Válida X");
    await user.type(screen.getByLabelText("Fecha"), "2026-05-17");
    await user.click(
      screen.getByRole("button", { name: /Crear competencia/i }),
    );

    expect(
      await screen.findByText(
        /Ya existe una válida con este número en la temporada/i,
      ),
    ).toBeInTheDocument();
  });

  it("?returnTo=/calendar/events/new → navigate a returnTo tras success", async () => {
    mswServer.use(
      http.post("*/api/race-analysis/race-events/", () =>
        HttpResponse.json(makeRaceEventRead({ id: 800 }), { status: 201 }),
      ),
    );
    const user = userEvent.setup();
    renderForm(
      "create",
      "/competitions/new?returnTo=/calendar/events/new",
    );

    // Spec 014: seleccionar serie (requerida) antes de submit.
    const seriesSelect = await screen.findByLabelText(/Serie/i);
    await waitFor(() =>
      expect(
        Array.from((seriesSelect as HTMLSelectElement).options).some(
          (o) => o.value === "2",
        ),
      ).toBe(true),
    );
    await user.selectOptions(seriesSelect, "2");

    await user.selectOptions(screen.getByLabelText("Número de válida"), "4");
    await user.type(screen.getByLabelText("Nombre"), "Vuelve al calendario");
    await user.type(screen.getByLabelText("Fecha"), "2026-05-17");
    await user.click(
      screen.getByRole("button", { name: /Crear competencia/i }),
    );

    await waitFor(() =>
      expect(mockNavigate).toHaveBeenCalledWith("/calendar/events/new"),
    );
  });

  it("0 violaciones a11y en create vacio", async () => {
    const { container } = renderForm("create");
    // Esperamos render completo
    await screen.findByLabelText("Nombre");
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});

describe("CompetitionFormPage — mode=edit", () => {
  it("precarga valores desde useRaceEvent en los inputs", async () => {
    mswServer.use(
      http.get("*/api/race-analysis/race-events/1", () =>
        HttpResponse.json(
          makeRaceEventRead({
            id: 1,
            sequence_number: 4,
            name: "Válida IV · Cali",
            event_date: "2026-05-17",
            location: "Cali",
            status: "scheduled",
          }),
        ),
      ),
    );
    renderForm("edit");
    await waitFor(() =>
      expect(
        (screen.getByLabelText("Nombre") as HTMLInputElement).value,
      ).toBe("Válida IV · Cali"),
    );
    expect(
      (screen.getByLabelText("Fecha") as HTMLInputElement).value,
    ).toBe("2026-05-17");
    expect(
      (screen.getByLabelText("Número de válida") as HTMLSelectElement).value,
    ).toBe("4");
  });

  it("cambiar status a 'Cancelada' muestra banner de advertencia", async () => {
    mswServer.use(
      http.get("*/api/race-analysis/race-events/1", () =>
        HttpResponse.json(
          makeRaceEventRead({ id: 1, status: "scheduled" }),
        ),
      ),
    );
    const user = userEvent.setup();
    renderForm("edit");
    await screen.findByLabelText("Nombre");

    await user.selectOptions(
      screen.getByLabelText(/Estado de la competencia/i),
      "cancelled",
    );

    expect(
      await screen.findByText(
        /permanecerá en el histórico pero no aparecerá como activo/i,
      ),
    ).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Spec 023 (T008) — Nivel de campeonato (Departamental / Nacional)
// ---------------------------------------------------------------------------

describe("CompetitionFormPage spec-023 — nivel de serie de campeonato", () => {
  it("tipo=Campeonato + form de crear serie abierto → select de nivel visible, default Departamental", async () => {
    // Sin series existentes para forzar el flujo de creación inline.
    mswServer.use(raceSeriesEmptyHandler);
    const user = userEvent.setup();
    renderForm("create");

    const kindSelect = await screen.findByLabelText(/Tipo de competencia/i);
    await user.selectOptions(kindSelect, "championship");

    const createLink = await screen.findByRole("button", {
      name: /Crear nueva serie de campeonato/i,
    });
    await user.click(createLink);

    const levelSelect = (await screen.findByLabelText(
      /Nivel de la serie/i,
    )) as HTMLSelectElement;
    expect(levelSelect).toBeInTheDocument();
    expect(levelSelect).toHaveDisplayValue(/Departamental/i);

    const optionValues = Array.from(levelSelect.options).map((o) => o.value);
    expect(optionValues).toContain("departmental");
    expect(optionValues).toContain("national");
  });

  it("tipo=Copa → el select de nivel no existe", async () => {
    renderForm("create");
    await screen.findByLabelText(/Tipo de competencia/i);

    expect(screen.queryByLabelText(/Nivel de la serie/i)).not.toBeInTheDocument();
  });

  it("crear serie con Nacional → el payload de la mutación incluye level:\"national\"", async () => {
    mswServer.use(raceSeriesEmptyHandler);
    let receivedBody: unknown = null;
    mswServer.use(
      http.post("*/api/race-analysis/race-series", async ({ request }) => {
        receivedBody = await request.json();
        return HttpResponse.json(
          {
            id: 42,
            name: "Campeonato Nacional MTB 2026",
            season_year: 2026,
            organizer: null,
            kind: "championship",
            level: "national",
            event_count: 0,
          },
          { status: 201 },
        );
      }),
    );

    const user = userEvent.setup();
    renderForm("create");

    const kindSelect = await screen.findByLabelText(/Tipo de competencia/i);
    await user.selectOptions(kindSelect, "championship");

    const createLink = await screen.findByRole("button", {
      name: /Crear nueva serie de campeonato/i,
    });
    await user.click(createLink);

    await user.type(
      screen.getByLabelText(/Nombre de la nueva serie de campeonato/i),
      "Campeonato Nacional MTB 2026",
    );

    const levelSelect = await screen.findByLabelText(/Nivel de la serie/i);
    await user.selectOptions(levelSelect, "national");

    await user.click(screen.getByRole("button", { name: /Crear serie/i }));

    await waitFor(() => expect(receivedBody).not.toBeNull());
    expect(receivedBody).toMatchObject({ level: "national" });
  });

  it("0 violaciones a11y con el select de nivel visible", async () => {
    mswServer.use(raceSeriesEmptyHandler);
    const user = userEvent.setup();
    const { container } = renderForm("create");

    const kindSelect = await screen.findByLabelText(/Tipo de competencia/i);
    await user.selectOptions(kindSelect, "championship");

    const createLink = await screen.findByRole("button", {
      name: /Crear nueva serie de campeonato/i,
    });
    await user.click(createLink);

    await screen.findByLabelText(/Nivel de la serie/i);

    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
