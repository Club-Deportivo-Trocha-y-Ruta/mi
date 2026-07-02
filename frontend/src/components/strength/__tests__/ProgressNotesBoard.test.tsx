/**
 * Tests para ProgressNotesBoard (US4 / T037-T038):
 *   - Registrar un progreso persiste en el servidor (MSW stateful) y, al
 *     recargar/reabrir el tablero, el registro sigue presente.
 *   - Un segundo registro del MISMO ejercicio no crea una fila duplicada: el
 *     tablero siempre muestra el ÚLTIMO estado por ejercicio ("latest status
 *     wins"), tanto inmediatamente después de guardar como al reabrir.
 *   - AUSENCIA total de UI de comparación entre atletas en cualquier parte
 *     del árbol del componente (FR-015): sin ranking, sin clasificación, sin
 *     leaderboard, sin tabla/sección "Comparación", sin ids de otros atletas.
 *
 * Mirror de `components/technique/__tests__/SkillProgressBoard.test.tsx`
 * (feature 018), adaptado al modelo "último registro por ejercicio" de
 * fuerza (sin `history` separado — cada registro nuevo sustituye la fila
 * mostrada para ese `exercise_id`).
 *
 * Estrategia de red: MSW con handlers con estado en memoria
 * (`createStatefulProgressHandlers`) para simular persistencia real entre
 * el registro y el "reopen" (remount) del tablero.
 *
 * Datos ficticios: atleta id=77 — nunca datos reales de deportistas TyR.
 */
import { describe, it, expect } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { ProgressNotesBoard } from "../ProgressNotesBoard";
import { renderWithProviders } from "@/test/helpers/renderWithProviders";
import { mswServer } from "@/test/setup";
import {
  createStatefulProgressHandlers,
  makeCatalogList,
  makeExerciseListItem,
} from "@/test/msw/strengthHandlers";
import { http, HttpResponse } from "msw";

const ATHLETE_ID = 77; // atleta ficticio

const TABLE_LABEL =
  "Estado actual de ejercicios de fuerza — solo este deportista";

/** Catálogo con un único ejercicio (id=1) — evita ambigüedad en el selector. */
const catalogHandler = http.get("*/api/strength/exercises", () =>
  HttpResponse.json(
    makeCatalogList([
      makeExerciseListItem({ id: 1, name: "Sentadilla con peso corporal" }),
    ]),
  ),
);

function renderBoard() {
  return renderWithProviders(<ProgressNotesBoard athleteId={ATHLETE_ID} />);
}

async function registerProgress(
  user: ReturnType<typeof userEvent.setup>,
  status: "introducido" | "en_progreso" | "dominado",
) {
  const form = await screen.findByRole("form", {
    name: "Registrar progreso de ejercicio de fuerza",
  });

  await user.selectOptions(
    within(form).getByLabelText("Ejercicio"),
    "1",
  );
  await user.selectOptions(within(form).getByLabelText("Estado"), status);

  const submitBtn = within(form).getByRole("button", {
    name: "Registrar progreso",
  });
  await user.click(submitBtn);
}

// ---------------------------------------------------------------------------
// Persistencia: el registro sobrevive al reabrir el tablero
// ---------------------------------------------------------------------------

describe("ProgressNotesBoard — persistencia de notas (reopen)", () => {
  it("un registro nuevo aparece en la tabla tras guardar", async () => {
    const user = userEvent.setup();
    mswServer.use(
      ...createStatefulProgressHandlers(ATHLETE_ID, []),
      catalogHandler,
    );

    renderBoard();

    // Estado vacío inicial
    await screen.findByText("Sin ejercicios registrados todavía");

    await registerProgress(user, "en_progreso");

    const table = await screen.findByRole("table", { name: TABLE_LABEL });
    expect(within(table).getByText("En progreso")).toBeInTheDocument();
    expect(
      within(table).getByText("Sentadilla con peso corporal"),
    ).toBeInTheDocument();
  });

  it("el registro persiste al reabrir (remount) el tablero", async () => {
    const user = userEvent.setup();
    const handlers = createStatefulProgressHandlers(ATHLETE_ID, []);
    mswServer.use(...handlers, catalogHandler);

    const { unmount } = renderBoard();

    await screen.findByText("Sin ejercicios registrados todavía");
    await registerProgress(user, "en_progreso");

    const table = await screen.findByRole("table", { name: TABLE_LABEL });
    expect(within(table).getByText("En progreso")).toBeInTheDocument();

    // Simula "reabrir": desmonta y vuelve a montar el tablero (nuevo fetch
    // contra el mismo servidor MSW con estado en memoria — no cache de
    // React Query previo, ya que renderBoard() crea un QueryClient fresco).
    unmount();
    mswServer.use(...handlers, catalogHandler);
    renderBoard();

    const reopenedTable = await screen.findByRole("table", {
      name: TABLE_LABEL,
    });
    expect(within(reopenedTable).getByText("En progreso")).toBeInTheDocument();
    expect(
      within(reopenedTable).getByText("Sentadilla con peso corporal"),
    ).toBeInTheDocument();
  });

  it("un segundo registro del mismo ejercicio actualiza (no duplica) la fila — latest status wins", async () => {
    const user = userEvent.setup();
    const handlers = createStatefulProgressHandlers(ATHLETE_ID, []);
    mswServer.use(...handlers, catalogHandler);

    renderBoard();

    await screen.findByText("Sin ejercicios registrados todavía");
    await registerProgress(user, "introducido");

    let table = await screen.findByRole("table", { name: TABLE_LABEL });
    expect(within(table).getByText("Introducido")).toBeInTheDocument();
    expect(within(table).getAllByRole("row")).toHaveLength(2); // header + 1 dato

    await registerProgress(user, "dominado");

    table = await screen.findByRole("table", { name: TABLE_LABEL });
    await waitFor(() => {
      expect(within(table).getByText("Dominado")).toBeInTheDocument();
    });
    expect(within(table).queryByText("Introducido")).not.toBeInTheDocument();
    // Sigue habiendo una sola fila de datos — no se duplicó por ejercicio.
    expect(within(table).getAllByRole("row")).toHaveLength(2);
  });

  it("el estado más reciente ('dominado') sigue siendo el único visible al reabrir", async () => {
    const user = userEvent.setup();
    const handlers = createStatefulProgressHandlers(ATHLETE_ID, []);
    mswServer.use(...handlers, catalogHandler);

    const { unmount } = renderBoard();

    await screen.findByText("Sin ejercicios registrados todavía");
    await registerProgress(user, "introducido");
    await screen.findByRole("table", { name: TABLE_LABEL });
    await registerProgress(user, "dominado");
    await waitFor(async () => {
      const table = await screen.findByRole("table", { name: TABLE_LABEL });
      expect(within(table).getByText("Dominado")).toBeInTheDocument();
    });

    unmount();
    mswServer.use(...handlers, catalogHandler);
    renderBoard();

    const reopenedTable = await screen.findByRole("table", {
      name: TABLE_LABEL,
    });
    expect(within(reopenedTable).getByText("Dominado")).toBeInTheDocument();
    expect(
      within(reopenedTable).queryByText("Introducido"),
    ).not.toBeInTheDocument();
    expect(within(reopenedTable).getAllByRole("row")).toHaveLength(2);
  });
});

// ---------------------------------------------------------------------------
// AUSENCIA de comparación entre atletas (FR-015)
// ---------------------------------------------------------------------------

describe("ProgressNotesBoard — ausencia de comparación entre atletas (FR-015)", () => {
  it("no contiene ningún elemento con texto 'ranking'", async () => {
    mswServer.use(
      ...createStatefulProgressHandlers(ATHLETE_ID, []),
      catalogHandler,
    );

    renderBoard();

    await screen.findByText("Sin ejercicios registrados todavía");
    expect(screen.queryByText(/ranking/i)).not.toBeInTheDocument();
  });

  it("no contiene ningún elemento con texto 'clasificación'", async () => {
    mswServer.use(
      ...createStatefulProgressHandlers(ATHLETE_ID, []),
      catalogHandler,
    );

    renderBoard();

    await screen.findByText("Sin ejercicios registrados todavía");
    expect(screen.queryByText(/clasificaci[oó]n/i)).not.toBeInTheDocument();
  });

  it("no contiene ningún elemento con texto 'leaderboard'", async () => {
    mswServer.use(
      ...createStatefulProgressHandlers(ATHLETE_ID, []),
      catalogHandler,
    );

    renderBoard();

    await screen.findByText("Sin ejercicios registrados todavía");
    expect(screen.queryByText(/leaderboard/i)).not.toBeInTheDocument();
  });

  it("no contiene ningún elemento con texto 'puesto' (posición relativa entre atletas)", async () => {
    mswServer.use(
      ...createStatefulProgressHandlers(ATHLETE_ID, []),
      catalogHandler,
    );

    renderBoard();

    await screen.findByText("Sin ejercicios registrados todavía");
    expect(screen.queryByText(/\bpuesto\b/i)).not.toBeInTheDocument();
  });

  it("no contiene ningún elemento con texto 'mejor que' (comparación directa)", async () => {
    mswServer.use(
      ...createStatefulProgressHandlers(ATHLETE_ID, []),
      catalogHandler,
    );

    renderBoard();

    await screen.findByText("Sin ejercicios registrados todavía");
    expect(screen.queryByText(/mejor que/i)).not.toBeInTheDocument();
  });

  it("no contiene ninguna tabla ni sección titulada 'Comparación'/'Comparar atletas'", async () => {
    const user = userEvent.setup();
    mswServer.use(
      ...createStatefulProgressHandlers(ATHLETE_ID, []),
      catalogHandler,
    );

    renderBoard();

    await screen.findByText("Sin ejercicios registrados todavía");
    await registerProgress(user, "en_progreso");
    await screen.findByRole("table", { name: TABLE_LABEL });

    expect(
      screen.queryByRole("heading", { name: /compar/i }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("table", { name: /compar/i }),
    ).not.toBeInTheDocument();
  });

  it("solo existe UNA tabla en todo el árbol (no hay tabla comparativa adicional)", async () => {
    const user = userEvent.setup();
    mswServer.use(
      ...createStatefulProgressHandlers(ATHLETE_ID, []),
      catalogHandler,
    );

    const { container } = renderBoard();

    await screen.findByText("Sin ejercicios registrados todavía");
    await registerProgress(user, "en_progreso");
    await screen.findByRole("table", { name: TABLE_LABEL });

    expect(screen.getAllByRole("table")).toHaveLength(1);
    // Ningún otro id de atleta ficticio expuesto como texto visible.
    const ALIEN_IDS = [1, 2, 78, 99, 100];
    for (const id of ALIEN_IDS) {
      expect(container.textContent).not.toMatch(
        new RegExp(`\\bAtleta\\s+${id}\\b`, "i"),
      );
    }
  });

  it("el aviso de contexto personal dice explícitamente que no se compara con otros atletas", async () => {
    mswServer.use(
      ...createStatefulProgressHandlers(ATHLETE_ID, []),
      catalogHandler,
    );

    renderBoard();

    expect(
      await screen.findByText(/no se compara con otros deportistas/i),
    ).toBeInTheDocument();
  });
});
