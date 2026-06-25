/**
 * Tests para SkillProgressBoard (US4 / T041):
 *   - Estado de carga → skeleton con role=status + aria-busy.
 *   - Estado error genérico → role=alert + botón "Reintentar".
 *   - Estado error 404 (atleta sin registros) → mensaje graceful SIN botón "Reintentar".
 *   - Estado exitoso → muestra estado actual por habilidad Y historial del atleta.
 *   - Estado vacío (current=[]) → "Sin habilidades registradas todavía".
 *   - Historial oculto cuando history=[].
 *   - Historial visible cuando history.length > 0.
 *   - Expand/collapse cuando history.length > 5.
 *   - Badge de estado: "Introducido", "En progreso", "Dominado".
 *   - Nota del entrenador visible en la tabla de estado actual.
 *   - AUSENCIA total de elementos de clasificación / comparación / ranking /
 *     otros atletas (FR-017, SC-005).
 *   - Solo aparece UN atleta (athlete_id del fixture) — ningún otro id en DOM.
 *   - a11y: jest-axe sin violaciones en estado cargando, error y exitoso.
 *
 * Estrategia de red: MSW + server del setup global.
 * Los handlers se inyectan por test con mswServer.use() para controlar
 * exactamente el escenario de cada caso.
 *
 * Datos ficticios: "Carlos Ficticio" (id=42) — nunca datos reales de atletas TyR.
 */
import { describe, it, expect } from "vitest";
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { axe, toHaveNoViolations } from "jest-axe";

import { SkillProgressBoard } from "../SkillProgressBoard";
import { renderWithProviders } from "@/test/helpers/renderWithProviders";
import { mswServer } from "@/test/setup";
import type {
  AthleteProgress,
  CurrentSkillProgress,
  SkillProgressEvent,
  SkillRead,
} from "@/types/technique.types";

expect.extend(toHaveNoViolations);

// ---------------------------------------------------------------------------
// Fixtures — datos deterministas y ficticios
// ---------------------------------------------------------------------------

const ATHLETE_ID = 42; // "Carlos Ficticio" — id ficticio

const SKILL_EQUILIBRIO: SkillRead = {
  code: "SKILL-001",
  slug: "equilibrio",
  name: "Equilibrio",
  order: 1,
};

const SKILL_FRENADA: SkillRead = {
  code: "SKILL-002",
  slug: "frenada",
  name: "Frenada",
  order: 2,
};

const SKILL_VIRAJE: SkillRead = {
  code: "SKILL-003",
  slug: "viraje",
  name: "Viraje",
  order: 3,
};

/** Entrada de estado actual para Equilibrio (dominado). */
const CURRENT_EQUILIBRIO: CurrentSkillProgress = {
  skill: { code: SKILL_EQUILIBRIO.code, slug: SKILL_EQUILIBRIO.slug, name: SKILL_EQUILIBRIO.name },
  status: "dominado",
  recorded_at: "2026-05-10T10:00:00Z",
  coach_note: "Excelente dominio en terreno plano.",
};

/** Entrada de estado actual para Frenada (en progreso). */
const CURRENT_FRENADA: CurrentSkillProgress = {
  skill: { code: SKILL_FRENADA.code, slug: SKILL_FRENADA.slug, name: SKILL_FRENADA.name },
  status: "en_progreso",
  recorded_at: "2026-05-17T10:00:00Z",
  coach_note: null,
};

/** Entrada de estado actual para Viraje (introducido, sin nota). */
const CURRENT_VIRAJE: CurrentSkillProgress = {
  skill: { code: SKILL_VIRAJE.code, slug: SKILL_VIRAJE.slug, name: SKILL_VIRAJE.name },
  status: "introducido",
  recorded_at: "2026-06-01T10:00:00Z",
  coach_note: null,
};

/** Evento de historial para Equilibrio (primer registro). */
const HISTORY_EQUILIBRIO_1: SkillProgressEvent = {
  id: 1,
  skill: { code: SKILL_EQUILIBRIO.code, slug: SKILL_EQUILIBRIO.slug, name: SKILL_EQUILIBRIO.name },
  status: "introducido",
  coach_note: "Primera sesión — observado con dificultad.",
  season: 2026,
  recorded_at: "2026-03-15T10:00:00Z",
};

/** Evento de historial para Equilibrio (segunda entrada). */
const HISTORY_EQUILIBRIO_2: SkillProgressEvent = {
  id: 2,
  skill: { code: SKILL_EQUILIBRIO.code, slug: SKILL_EQUILIBRIO.slug, name: SKILL_EQUILIBRIO.name },
  status: "dominado",
  coach_note: "Progresó rápido en terreno plano.",
  season: 2026,
  recorded_at: "2026-05-10T10:00:00Z",
};

/** Respuesta con datos completos: 3 habilidades actuales, 2 eventos históricos. */
const PROGRESS_WITH_DATA: AthleteProgress = {
  athlete_id: ATHLETE_ID,
  current: [CURRENT_EQUILIBRIO, CURRENT_FRENADA, CURRENT_VIRAJE],
  history: [HISTORY_EQUILIBRIO_1, HISTORY_EQUILIBRIO_2],
};

/** Respuesta completamente vacía: 0 registros. */
const PROGRESS_ALL_EMPTY: AthleteProgress = {
  athlete_id: ATHLETE_ID,
  current: [],
  history: [],
};

/** 6 eventos históricos — dispara el botón expand/collapse. */
const HISTORY_6_EVENTS: SkillProgressEvent[] = Array.from(
  { length: 6 },
  (_, i) => ({
    id: 10 + i,
    skill: { code: SKILL_EQUILIBRIO.code, slug: SKILL_EQUILIBRIO.slug, name: SKILL_EQUILIBRIO.name },
    status: "en_progreso" as const,
    coach_note: `Sesión ${i + 1} — nota ficticia.`,
    season: 2026,
    recorded_at: new Date(2026, 2 + i, 1).toISOString(),
  }),
);

const PROGRESS_MANY_HISTORY: AthleteProgress = {
  athlete_id: ATHLETE_ID,
  current: [CURRENT_EQUILIBRIO],
  history: HISTORY_6_EVENTS,
};

// ---------------------------------------------------------------------------
// MSW helper handlers
// ---------------------------------------------------------------------------

/** Skills endpoint para que AddProgressForm no bloquee con un spinner infinito. */
const skillsHandler = http.get("*/api/technique/skills", () =>
  HttpResponse.json([SKILL_EQUILIBRIO, SKILL_FRENADA, SKILL_VIRAJE]),
);

function progressHandler(body: AthleteProgress, status = 200) {
  return http.get(`*/api/technique/athletes/${ATHLETE_ID}/progress`, () =>
    status === 200
      ? HttpResponse.json(body)
      : new HttpResponse(null, { status }),
  );
}

function progressErrorHandler(status: number) {
  return http.get(`*/api/technique/athletes/${ATHLETE_ID}/progress`, () =>
    new HttpResponse(null, { status }),
  );
}

function progressNetworkErrorHandler() {
  return http.get(`*/api/technique/athletes/${ATHLETE_ID}/progress`, () =>
    HttpResponse.error(),
  );
}

// ---------------------------------------------------------------------------
// Render helper
// ---------------------------------------------------------------------------

function renderBoard(athleteId = ATHLETE_ID) {
  return renderWithProviders(<SkillProgressBoard athleteId={athleteId} />);
}

// ---------------------------------------------------------------------------
// Loading state
// ---------------------------------------------------------------------------

describe("SkillProgressBoard — estado de carga", () => {
  it("muestra skeleton con role=status y aria-busy=true", async () => {
    // Use a handler that delays indefinitely — the loading state is synchronous
    // on first render before the query resolves.
    mswServer.use(
      http.get(`*/api/technique/athletes/${ATHLETE_ID}/progress`, async () => {
        await new Promise(() => {}); // never resolves — keeps isLoading=true
      }),
      skillsHandler,
    );

    renderBoard();

    const status = screen.getByRole("status");
    expect(status).toHaveAttribute("aria-busy", "true");
    expect(status).toHaveAttribute("aria-label", "Cargando progreso de habilidades…");
  });

  it("no muestra la tabla de habilidades durante la carga", async () => {
    mswServer.use(
      http.get(`*/api/technique/athletes/${ATHLETE_ID}/progress`, async () => {
        await new Promise(() => {});
      }),
      skillsHandler,
    );

    renderBoard();

    expect(
      screen.queryByRole("table", { name: "Estado actual de habilidades técnicas" }),
    ).not.toBeInTheDocument();
  });

  it("no tiene violaciones de accesibilidad en estado de carga", async () => {
    mswServer.use(
      http.get(`*/api/technique/athletes/${ATHLETE_ID}/progress`, async () => {
        await new Promise(() => {});
      }),
      skillsHandler,
    );

    const { container } = renderBoard();
    expect(await axe(container)).toHaveNoViolations();
  });
});

// ---------------------------------------------------------------------------
// Error state — generic (non-404)
// ---------------------------------------------------------------------------

describe("SkillProgressBoard — estado de error genérico", () => {
  it("muestra role=alert con mensaje de error cuando la API falla", async () => {
    mswServer.use(progressErrorHandler(500), skillsHandler);

    renderBoard();

    const alert = await screen.findByRole("alert");
    expect(alert).toBeInTheDocument();
    expect(alert).toHaveTextContent("Ocurrió un error inesperado.");
  });

  it("muestra botón 'Reintentar' cuando el error NO es 404", async () => {
    mswServer.use(progressErrorHandler(500), skillsHandler);

    renderBoard();

    await screen.findByRole("alert");
    expect(
      screen.getByRole("button", { name: /Reintentar/i }),
    ).toBeInTheDocument();
  });

  it("muestra role=alert en error de red (cold-start)", async () => {
    mswServer.use(progressNetworkErrorHandler(), skillsHandler);

    renderBoard();

    const alert = await screen.findByRole("alert");
    expect(alert).toBeInTheDocument();
  });

  it("no tiene violaciones de accesibilidad en estado de error", async () => {
    mswServer.use(progressErrorHandler(500), skillsHandler);

    const { container } = renderBoard();
    await screen.findByRole("alert");
    expect(await axe(container)).toHaveNoViolations();
  });
});

// ---------------------------------------------------------------------------
// Error state — 404 graceful (atleta sin registros — FR-018)
// ---------------------------------------------------------------------------

describe("SkillProgressBoard — error 404 graceful", () => {
  it("muestra mensaje de que el atleta no tiene habilidades cuando recibe 404", async () => {
    mswServer.use(progressErrorHandler(404), skillsHandler);

    renderBoard();

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(
      "Este atleta no tiene habilidades registradas todavía.",
    );
  });

  it("NO muestra el botón 'Reintentar' cuando el error es 404", async () => {
    mswServer.use(progressErrorHandler(404), skillsHandler);

    renderBoard();

    await screen.findByRole("alert");
    expect(
      screen.queryByRole("button", { name: /Reintentar/i }),
    ).not.toBeInTheDocument();
  });

  it("no tiene violaciones de accesibilidad en el estado de error 404", async () => {
    mswServer.use(progressErrorHandler(404), skillsHandler);

    const { container } = renderBoard();
    await screen.findByRole("alert");
    expect(await axe(container)).toHaveNoViolations();
  });
});

// ---------------------------------------------------------------------------
// Success state — estado actual por habilidad
// ---------------------------------------------------------------------------

describe("SkillProgressBoard — estado exitoso: tabla de estado actual", () => {
  it("muestra la tabla de estado actual con aria-label correcto", async () => {
    mswServer.use(progressHandler(PROGRESS_WITH_DATA), skillsHandler);

    renderBoard();

    expect(
      await screen.findByRole("table", { name: "Estado actual de habilidades técnicas" }),
    ).toBeInTheDocument();
  });

  it("muestra cada habilidad registrada en la tabla", async () => {
    mswServer.use(progressHandler(PROGRESS_WITH_DATA), skillsHandler);

    renderBoard();

    const table = await screen.findByRole("table", { name: "Estado actual de habilidades técnicas" });

    // Equilibrio appears in both the table and history; use within(table) to scope
    expect(within(table).getAllByText("Equilibrio").length).toBeGreaterThanOrEqual(1);
    expect(within(table).getByText("Frenada")).toBeInTheDocument();
    expect(within(table).getByText("Viraje")).toBeInTheDocument();
  });

  it("muestra el badge de estado 'Dominado' para la habilidad correspondiente", async () => {
    mswServer.use(progressHandler(PROGRESS_WITH_DATA), skillsHandler);

    renderBoard();

    const table = await screen.findByRole("table", { name: "Estado actual de habilidades técnicas" });

    // Scope to the table to avoid matching "Equilibrio" in the history timeline
    const equilibrioRow = within(table).getAllByText("Equilibrio")[0].closest("tr") as HTMLElement;
    expect(within(equilibrioRow).getByText("Dominado")).toBeInTheDocument();
  });

  it("muestra el badge de estado 'En progreso' para la habilidad correspondiente", async () => {
    mswServer.use(progressHandler(PROGRESS_WITH_DATA), skillsHandler);

    renderBoard();

    await screen.findByRole("table", { name: "Estado actual de habilidades técnicas" });

    const frenadaRow = screen.getByText("Frenada").closest("tr") as HTMLElement;
    expect(within(frenadaRow).getByText("En progreso")).toBeInTheDocument();
  });

  it("muestra el badge de estado 'Introducido' para la habilidad correspondiente", async () => {
    mswServer.use(progressHandler(PROGRESS_WITH_DATA), skillsHandler);

    renderBoard();

    await screen.findByRole("table", { name: "Estado actual de habilidades técnicas" });

    const virajeRow = screen.getByText("Viraje").closest("tr") as HTMLElement;
    expect(within(virajeRow).getByText("Introducido")).toBeInTheDocument();
  });

  it("muestra la nota del entrenador cuando existe", async () => {
    mswServer.use(progressHandler(PROGRESS_WITH_DATA), skillsHandler);

    renderBoard();

    await screen.findByRole("table", { name: "Estado actual de habilidades técnicas" });

    expect(
      screen.getByText("Excelente dominio en terreno plano."),
    ).toBeInTheDocument();
  });

  it("muestra el código de habilidad en la tabla", async () => {
    mswServer.use(progressHandler(PROGRESS_WITH_DATA), skillsHandler);

    renderBoard();

    await screen.findByRole("table", { name: "Estado actual de habilidades técnicas" });

    expect(screen.getByText("SKILL-001")).toBeInTheDocument();
  });

  it("muestra el mensaje 'Sin habilidades registradas todavía' cuando current=[]", async () => {
    mswServer.use(progressHandler(PROGRESS_ALL_EMPTY), skillsHandler);

    renderBoard();

    // Wait for load to finish (table heading or empty state message)
    expect(
      await screen.findByText("Sin habilidades registradas todavía"),
    ).toBeInTheDocument();
  });

  it("muestra el aviso de primer registro cuando current=[]", async () => {
    mswServer.use(progressHandler(PROGRESS_ALL_EMPTY), skillsHandler);

    renderBoard();

    expect(
      await screen.findByText("Usa el formulario de abajo para registrar el primer progreso."),
    ).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Success state — historial de la temporada
// ---------------------------------------------------------------------------

describe("SkillProgressBoard — estado exitoso: historial de la temporada", () => {
  it("muestra la sección 'Evolución en la temporada' cuando hay historial", async () => {
    mswServer.use(progressHandler(PROGRESS_WITH_DATA), skillsHandler);

    renderBoard();

    expect(
      await screen.findByText("Evolución en la temporada"),
    ).toBeInTheDocument();
  });

  it("la lista de historial tiene aria-label correcto", async () => {
    mswServer.use(progressHandler(PROGRESS_WITH_DATA), skillsHandler);

    renderBoard();

    await screen.findByText("Evolución en la temporada");

    expect(
      screen.getByRole("list", { name: "Historial de progreso de la temporada" }),
    ).toBeInTheDocument();
  });

  it("cada evento del historial aparece en la lista", async () => {
    mswServer.use(progressHandler(PROGRESS_WITH_DATA), skillsHandler);

    renderBoard();

    await screen.findByText("Evolución en la temporada");

    const list = screen.getByRole("list", { name: "Historial de progreso de la temporada" });
    // Both history events reference Equilibrio
    const items = within(list).getAllByRole("listitem");
    expect(items).toHaveLength(2);
  });

  it("muestra la nota del evento histórico en el historial", async () => {
    mswServer.use(progressHandler(PROGRESS_WITH_DATA), skillsHandler);

    renderBoard();

    await screen.findByText("Evolución en la temporada");

    // HISTORY_EQUILIBRIO_1 has a note
    expect(
      screen.getByText("Primera sesión — observado con dificultad."),
    ).toBeInTheDocument();
  });

  it("muestra la temporada (T2026) en cada item del historial", async () => {
    mswServer.use(progressHandler(PROGRESS_WITH_DATA), skillsHandler);

    renderBoard();

    await screen.findByText("Evolución en la temporada");

    const seasonLabels = screen.getAllByText("T2026");
    expect(seasonLabels.length).toBeGreaterThanOrEqual(1);
  });

  it("NO muestra la sección de historial cuando history=[]", async () => {
    mswServer.use(progressHandler(PROGRESS_ALL_EMPTY), skillsHandler);

    renderBoard();

    // Wait for empty state to appear (confirms load complete)
    await screen.findByText("Sin habilidades registradas todavía");

    expect(
      screen.queryByText("Evolución en la temporada"),
    ).not.toBeInTheDocument();
  });

  it("muestra solo los primeros 5 eventos cuando history.length > 5 (collapsed)", async () => {
    mswServer.use(progressHandler(PROGRESS_MANY_HISTORY), skillsHandler);

    renderBoard();

    await screen.findByText("Evolución en la temporada");

    const list = screen.getByRole("list", { name: "Historial de progreso de la temporada" });
    // Initially only 5 items visible (PREVIEW_COUNT = 5)
    const visibleItems = within(list).getAllByRole("listitem");
    expect(visibleItems).toHaveLength(5);
  });

  it("el botón 'Ver X registros anteriores' aparece cuando history.length > 5", async () => {
    mswServer.use(progressHandler(PROGRESS_MANY_HISTORY), skillsHandler);

    renderBoard();

    await screen.findByText("Evolución en la temporada");

    // 6 total − 5 preview = 1 hidden → "Ver 1 registro anterior"
    expect(
      screen.getByRole("button", { name: /Ver 1 registro anterior/ }),
    ).toBeInTheDocument();
  });

  it("el botón expand tiene aria-expanded=false antes de expandir", async () => {
    mswServer.use(progressHandler(PROGRESS_MANY_HISTORY), skillsHandler);

    renderBoard();

    await screen.findByText("Evolución en la temporada");

    const expandBtn = screen.getByRole("button", { name: /Ver 1 registro anterior/ });
    expect(expandBtn).toHaveAttribute("aria-expanded", "false");
  });

  it("al clicar 'Ver registros anteriores' se muestran todos los eventos", async () => {
    const user = userEvent.setup();
    mswServer.use(progressHandler(PROGRESS_MANY_HISTORY), skillsHandler);

    renderBoard();

    await screen.findByText("Evolución en la temporada");

    const expandBtn = screen.getByRole("button", { name: /Ver 1 registro anterior/ });
    await user.click(expandBtn);

    const list = screen.getByRole("list", { name: "Historial de progreso de la temporada" });
    const allItems = within(list).getAllByRole("listitem");
    expect(allItems).toHaveLength(6);
  });

  it("el botón dice 'Ver menos' y aria-expanded=true después de expandir", async () => {
    const user = userEvent.setup();
    mswServer.use(progressHandler(PROGRESS_MANY_HISTORY), skillsHandler);

    renderBoard();

    await screen.findByText("Evolución en la temporada");

    await user.click(screen.getByRole("button", { name: /Ver 1 registro anterior/ }));

    const collapseBtn = screen.getByRole("button", { name: /Ver menos/ });
    expect(collapseBtn).toHaveAttribute("aria-expanded", "true");
  });
});

// ---------------------------------------------------------------------------
// Formulario de registro de progreso
// ---------------------------------------------------------------------------

describe("SkillProgressBoard — formulario 'Registrar progreso'", () => {
  it("muestra la sección 'Registrar progreso' en estado exitoso", async () => {
    mswServer.use(progressHandler(PROGRESS_WITH_DATA), skillsHandler);

    renderBoard();

    await screen.findByRole("table", { name: "Estado actual de habilidades técnicas" });

    // "Registrar progreso" appears as both a CardTitle and a button — getAllByText is correct
    const matches = screen.getAllByText("Registrar progreso");
    expect(matches.length).toBeGreaterThanOrEqual(1);
  });

  it("el formulario de registro tiene aria-label correcto", async () => {
    mswServer.use(progressHandler(PROGRESS_WITH_DATA), skillsHandler);

    renderBoard();

    await screen.findByRole("table", { name: "Estado actual de habilidades técnicas" });

    expect(
      screen.getByRole("form", { name: "Registrar progreso de habilidad" }),
    ).toBeInTheDocument();
  });

  it("el botón de submit dice 'Registrar progreso' y tiene min-h-12 (48px touch target)", async () => {
    mswServer.use(progressHandler(PROGRESS_WITH_DATA), skillsHandler);

    renderBoard();

    await screen.findByRole("table", { name: "Estado actual de habilidades técnicas" });

    const btn = screen.getByRole("button", { name: "Registrar progreso" });
    expect(btn).toBeInTheDocument();
    // Touch-target class is present (WCAG 2.1 AA)
    expect(btn).toHaveClass("min-h-12");
  });
});

// ---------------------------------------------------------------------------
// AUSENCIA de clasificación / comparación / otros atletas (FR-017, SC-005)
// ---------------------------------------------------------------------------

describe("SkillProgressBoard — ausencia de clasificación y comparación (FR-017, SC-005)", () => {
  it("no contiene ningún elemento con texto 'ranking'", async () => {
    mswServer.use(progressHandler(PROGRESS_WITH_DATA), skillsHandler);

    renderBoard();

    await screen.findByRole("table", { name: "Estado actual de habilidades técnicas" });

    expect(screen.queryByText(/ranking/i)).not.toBeInTheDocument();
  });

  it("no contiene ningún elemento con texto 'clasificación'", async () => {
    mswServer.use(progressHandler(PROGRESS_WITH_DATA), skillsHandler);

    renderBoard();

    await screen.findByRole("table", { name: "Estado actual de habilidades técnicas" });

    expect(screen.queryByText(/clasificaci[oó]n/i)).not.toBeInTheDocument();
  });

  it("no contiene tabla ni sección titulada 'Comparación' o 'Comparar atletas'", async () => {
    // The component subtitle explicitly says "no se compara con otros atletas",
    // which is the privacy disclaimer — that text is intentional and correct.
    // What must NOT exist is any comparison *widget* or heading offering cross-athlete views.
    mswServer.use(progressHandler(PROGRESS_WITH_DATA), skillsHandler);

    renderBoard();

    await screen.findByRole("table", { name: "Estado actual de habilidades técnicas" });

    // No heading titled "Comparación" or similar
    expect(screen.queryByRole("heading", { name: /compar/i })).not.toBeInTheDocument();
    // No table comparing athletes
    expect(
      screen.queryByRole("table", { name: /compar/i }),
    ).not.toBeInTheDocument();
  });

  it("no contiene ningún elemento con texto 'leaderboard'", async () => {
    mswServer.use(progressHandler(PROGRESS_WITH_DATA), skillsHandler);

    renderBoard();

    await screen.findByRole("table", { name: "Estado actual de habilidades técnicas" });

    expect(screen.queryByText(/leaderboard/i)).not.toBeInTheDocument();
  });

  it("no contiene ningún elemento con texto 'puesto' (posición relativa entre atletas)", async () => {
    mswServer.use(progressHandler(PROGRESS_WITH_DATA), skillsHandler);

    renderBoard();

    await screen.findByRole("table", { name: "Estado actual de habilidades técnicas" });

    // "puesto" as in "ranking position" — should never appear
    expect(screen.queryByText(/\bpuesto\b/i)).not.toBeInTheDocument();
  });

  it("no contiene ningún elemento con texto 'mejor que' (comparación directa)", async () => {
    mswServer.use(progressHandler(PROGRESS_WITH_DATA), skillsHandler);

    renderBoard();

    await screen.findByRole("table", { name: "Estado actual de habilidades técnicas" });

    expect(screen.queryByText(/mejor que/i)).not.toBeInTheDocument();
  });

  it("solo aparece el athlete_id del fixture en los datos renderizados (no hay otros atletas)", async () => {
    // The component receives athleteId=42. The response contains athlete_id=42.
    // No other athlete id should appear as a visible label or accessible name.
    mswServer.use(progressHandler(PROGRESS_WITH_DATA), skillsHandler);

    const { container } = renderBoard();

    await screen.findByRole("table", { name: "Estado actual de habilidades técnicas" });

    // Verify that no element exposes a different athlete_id (e.g., 1, 2, 99, 100)
    // as text content or aria label referencing another athlete.
    // We check there's no text "Atleta 1", "Atleta 99", etc.
    const ALIEN_IDS = [1, 2, 99, 100, 200];
    for (const id of ALIEN_IDS) {
      expect(container.textContent).not.toMatch(new RegExp(`\\bAtleta\\s+${id}\\b`, "i"));
    }
  });

  it("el aviso de contexto personal menciona 'maduración biológica' sin referencias a otros", async () => {
    mswServer.use(progressHandler(PROGRESS_WITH_DATA), skillsHandler);

    renderBoard();

    // The component has a subtitle: "Avance personal anclado a la etapa de maduración biológica
    // del deportista — no se compara con otros atletas."
    expect(
      await screen.findByText(
        /Avance personal anclado a la etapa de maduración biológica/i,
      ),
    ).toBeInTheDocument();
  });

  it("el aviso de contexto personal dice explícitamente 'no se compara con otros atletas'", async () => {
    mswServer.use(progressHandler(PROGRESS_WITH_DATA), skillsHandler);

    renderBoard();

    expect(
      await screen.findByText(/no se compara con otros atletas/i),
    ).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Accesibilidad — jest-axe
// ---------------------------------------------------------------------------

describe("SkillProgressBoard — accesibilidad (jest-axe)", () => {
  it("no tiene violaciones en estado exitoso con habilidades y historial", async () => {
    mswServer.use(progressHandler(PROGRESS_WITH_DATA), skillsHandler);

    const { container } = renderBoard();

    // Wait for data to render
    await screen.findByRole("table", { name: "Estado actual de habilidades técnicas" });

    expect(await axe(container)).toHaveNoViolations();
  });

  it("no tiene violaciones en estado vacío (current=[], history=[])", async () => {
    mswServer.use(progressHandler(PROGRESS_ALL_EMPTY), skillsHandler);

    const { container } = renderBoard();

    await screen.findByText("Sin habilidades registradas todavía");

    expect(await axe(container)).toHaveNoViolations();
  });

  it("no tiene violaciones en estado error 404", async () => {
    mswServer.use(progressErrorHandler(404), skillsHandler);

    const { container } = renderBoard();

    await screen.findByRole("alert");

    expect(await axe(container)).toHaveNoViolations();
  });

  it("no tiene violaciones en estado error genérico (500)", async () => {
    mswServer.use(progressErrorHandler(500), skillsHandler);

    const { container } = renderBoard();

    await screen.findByRole("alert");

    expect(await axe(container)).toHaveNoViolations();
  });

  it("no tiene violaciones con historial expandido", async () => {
    const user = userEvent.setup();
    mswServer.use(progressHandler(PROGRESS_MANY_HISTORY), skillsHandler);

    const { container } = renderBoard();

    await screen.findByText("Evolución en la temporada");

    await user.click(screen.getByRole("button", { name: /Ver 1 registro anterior/ }));

    expect(await axe(container)).toHaveNoViolations();
  });
});
