/**
 * MSW handlers para el módulo Fuerza y Acondicionamiento (feature 021).
 * Fixtures deterministas; sin datos reales de atletas.
 *
 * Mirror de `test/msw/techniqueHandlers.ts` (feature 018).
 */
import { http, HttpResponse } from "msw";

import type {
  StrengthAthleteProgress,
  StrengthAttachOut,
  StrengthBlockList,
  StrengthBlockOut,
  StrengthCatalogList,
  StrengthEntryOut,
  StrengthExerciseDetail,
  StrengthExerciseListItem,
  StrengthProgressInput,
  StrengthProgressOut,
} from "@/schemas/strength.schemas";

// ---------------------------------------------------------------------------
// Fixture factories
// ---------------------------------------------------------------------------

export function makeExerciseListItem(
  overrides?: Partial<StrengthExerciseListItem>,
): StrengthExerciseListItem {
  return {
    id: 1,
    slug: "sentadilla-peso-corporal",
    name: "Sentadilla con peso corporal",
    summary: "Ejercicio de fuerza para tren inferior sin equipo.",
    equipment: "sin_equipo",
    equipment_detail: null,
    movement_category: "inferior_bilateral",
    age_bands: ["10-12"],
    suggested_duration_min: 10,
    suggested_reps: "3x10",
    is_seeded: true,
    is_hidden: false,
    ...overrides,
  };
}

export function makeExerciseDetail(
  overrides?: Partial<StrengthExerciseDetail>,
): StrengthExerciseDetail {
  return {
    ...makeExerciseListItem(),
    how_to: "Baja controladamente flexionando cadera y rodillas, mantén el pecho erguido y regresa a la posición inicial.",
    common_errors: "Rodillas colapsando hacia adentro; talones se despegan del piso.",
    illustration_ascii: "  O\n /|\\\n / \\",
    illustration_alt: "Figura de una persona realizando una sentadilla con peso corporal.",
    ...overrides,
  };
}

export function makeCatalogList(
  items: StrengthExerciseListItem[] = [makeExerciseListItem()],
): StrengthCatalogList {
  return { items, total: items.length };
}

/** Entrada de bloque (mirror de `strengthEntryOutSchema`). */
export function makeEntryOut(
  overrides?: Partial<StrengthEntryOut>,
): StrengthEntryOut {
  return {
    id: 1,
    position: 0,
    duration_min: 10,
    reps: "3x10",
    is_age_override: false,
    override_note: null,
    exercise: makeExerciseListItem(),
    ...overrides,
  };
}

/** Bloque de fuerza (mirror de `strengthBlockOutSchema`). */
export function makeBlockOut(
  overrides?: Partial<StrengthBlockOut>,
): StrengthBlockOut {
  const entries = overrides?.entries ?? [makeEntryOut()];
  return {
    id: 1,
    name: "Bloque de fuerza — tren inferior",
    target_age_band: "10-12",
    duration_target_min: 30,
    total_duration_min: entries.reduce((sum, e) => sum + e.duration_min, 0),
    is_archived: false,
    entries,
    created_at: "2026-06-01T00:00:00Z",
    ...overrides,
  };
}

export function makeBlockList(
  items: StrengthBlockOut[] = [makeBlockOut()],
): StrengthBlockList {
  return { items, total: items.length };
}

/** Adjunto bloque↔sesión (mirror de `strengthAttachOutSchema`). */
export function makeAttachOut(
  overrides?: Partial<StrengthAttachOut>,
): StrengthAttachOut {
  return {
    id: 1,
    training_session_id: 1,
    block_id: 1,
    position: 0,
    attached_at: "2026-06-01T00:00:00Z",
    ...overrides,
  };
}

/** Registro de progreso por ejercicio (mirror de `strengthProgressOutSchema`). */
export function makeProgressOut(
  overrides?: Partial<StrengthProgressOut>,
): StrengthProgressOut {
  return {
    exercise_id: 1,
    exercise_name: "Sentadilla con peso corporal",
    status: "introducido",
    coach_note: null,
    season: 2026,
    recorded_at: "2026-06-01T00:00:00Z",
    ...overrides,
  };
}

/** Progreso de un atleta — lista de últimos registros por ejercicio. */
export function makeAthleteProgress(
  items: StrengthProgressOut[] = [makeProgressOut()],
): StrengthAthleteProgress {
  return { items };
}

// ---------------------------------------------------------------------------
// MSW handlers — happy path
// ---------------------------------------------------------------------------

export const strengthHandlers = [
  // GET /api/strength/exercises — catálogo con filtros opcionales
  http.get("*/api/strength/exercises", () => {
    return HttpResponse.json(
      makeCatalogList([
        makeExerciseListItem({ id: 1 }),
        makeExerciseListItem({
          id: 2,
          slug: "press-banca-mancuernas",
          name: "Press de banca con mancuernas",
          summary: "Ejercicio de empuje superior con equipo de gimnasio.",
          equipment: "equipo_gym",
          equipment_detail: "Mancuernas ligeras",
          movement_category: "empuje_superior",
          age_bands: ["13-15"],
        }),
      ]),
    );
  }),

  // GET /api/strength/exercises/:id — detalle
  http.get("*/api/strength/exercises/:id", ({ params }) => {
    const id = Number(params.id) || 1;
    return HttpResponse.json(makeExerciseDetail({ id }));
  }),

  // POST /api/strength/blocks — crea un bloque de fuerza
  http.post("*/api/strength/blocks", async ({ request }) => {
    const body = (await request.json()) as {
      name?: string;
      target_age_band?: StrengthBlockOut["target_age_band"];
      duration_target_min?: number;
      entries?: Array<{
        exercise_id: number;
        position: number;
        duration_min: number;
        reps?: string;
      }>;
    };
    const entries = (body.entries ?? []).map((entry, idx) =>
      makeEntryOut({
        id: idx + 1,
        position: entry.position,
        duration_min: entry.duration_min,
        reps: entry.reps ?? null,
        exercise: makeExerciseListItem({ id: entry.exercise_id }),
      }),
    );
    return HttpResponse.json(
      makeBlockOut({
        id: 1,
        name: body.name ?? "Bloque de fuerza",
        target_age_band: body.target_age_band ?? "10-12",
        duration_target_min: body.duration_target_min ?? 30,
        entries,
      }),
      { status: 201 },
    );
  }),

  // PUT /api/strength/blocks/:id — reemplazo completo de un bloque
  http.put("*/api/strength/blocks/:id", async ({ params, request }) => {
    const id = Number(params.id) || 1;
    const body = (await request.json()) as {
      name?: string;
      target_age_band?: StrengthBlockOut["target_age_band"];
      duration_target_min?: number;
      entries?: Array<{
        exercise_id: number;
        position: number;
        duration_min: number;
        reps?: string;
      }>;
    };
    const entries = (body.entries ?? []).map((entry, idx) =>
      makeEntryOut({
        id: idx + 1,
        position: entry.position,
        duration_min: entry.duration_min,
        reps: entry.reps ?? null,
        exercise: makeExerciseListItem({ id: entry.exercise_id }),
      }),
    );
    return HttpResponse.json(
      makeBlockOut({
        id,
        name: body.name ?? "Bloque de fuerza",
        target_age_band: body.target_age_band ?? "10-12",
        duration_target_min: body.duration_target_min ?? 30,
        entries,
      }),
    );
  }),

  // GET /api/strength/blocks — lista de bloques del club
  http.get("*/api/strength/blocks", () => {
    return HttpResponse.json(makeBlockList());
  }),

  // GET /api/strength/blocks/:id — detalle de un bloque
  http.get("*/api/strength/blocks/:id", ({ params }) => {
    const id = Number(params.id) || 1;
    return HttpResponse.json(makeBlockOut({ id }));
  }),

  // PATCH /api/strength/blocks/:id/archive — archiva/desarchiva un bloque
  http.patch("*/api/strength/blocks/:id/archive", async ({ params, request }) => {
    const id = Number(params.id) || 1;
    const body = (await request.json()) as { is_archived?: boolean };
    return HttpResponse.json(
      makeBlockOut({ id, is_archived: body.is_archived ?? true }),
    );
  }),

  // POST /api/strength/blocks/:id/attach — adjunta un bloque a una sesión
  http.post("*/api/strength/blocks/:id/attach", async ({ params, request }) => {
    const blockId = Number(params.id) || 1;
    const body = (await request.json()) as { training_session_id?: number };
    return HttpResponse.json(
      makeAttachOut({
        block_id: blockId,
        training_session_id: body.training_session_id ?? 1,
      }),
      { status: 201 },
    );
  }),

  // DELETE /api/strength/blocks/:id/attach/:sessionId — desadjunta un bloque
  http.delete("*/api/strength/blocks/:id/attach/:sessionId", () => {
    return new HttpResponse(null, { status: 204 });
  }),

  // GET /api/strength/sessions/:id/blocks — bloques adjuntos a una sesión
  http.get("*/api/strength/sessions/:id/blocks", () => {
    return HttpResponse.json({ items: [makeBlockOut()] });
  }),

  // GET /api/strength/athletes/:athleteId/progress — último registro por ejercicio
  http.get("*/api/strength/athletes/:athleteId/progress", () => {
    return HttpResponse.json(makeAthleteProgress([]));
  }),

  // POST /api/strength/athletes/:athleteId/progress — registra progreso (append-only)
  http.post("*/api/strength/athletes/:athleteId/progress", async ({ request }) => {
    const body = (await request.json()) as StrengthProgressInput;
    return HttpResponse.json(
      makeProgressOut({
        exercise_id: body.exercise_id,
        status: body.status,
        coach_note: body.coach_note ?? null,
        season: body.season,
        recorded_at: new Date().toISOString(),
      }),
      { status: 201 },
    );
  }),
];

// ---------------------------------------------------------------------------
// Stateful progress handlers — persisten notas entre GET/POST dentro del
// mismo test (mirror del patrón in-memory usado en otros módulos para
// simular "reopen" tras registrar progreso). El último registro por
// `exercise_id` gana (latest status wins), igual que el backend real
// (`GET .../progress` devuelve el último por ejercicio).
// ---------------------------------------------------------------------------

/** Nombres por defecto, alineados con `makeExerciseListItem`/el catálogo happy-path de este archivo. */
const DEFAULT_EXERCISE_NAMES: Record<number, string> = {
  1: "Sentadilla con peso corporal",
  2: "Press de banca con mancuernas",
};

/**
 * Crea un par de handlers GET/POST con estado en memoria para
 * `/api/strength/athletes/:athleteId/progress`. Útil para tests que
 * necesitan verificar que un registro nuevo persiste y sustituye el estado
 * mostrado al recargar (reopen) el tablero.
 *
 * `exerciseNames` permite resolver `exercise_name` a partir del
 * `exercise_id` enviado en el POST (el body real de `StrengthProgressInput`
 * no incluye el nombre — lo resuelve el backend real). Por defecto usa
 * `DEFAULT_EXERCISE_NAMES`, que coincide con el catálogo happy-path de este
 * mismo archivo (ids 1 y 2).
 */
export function createStatefulProgressHandlers(
  athleteId: number,
  initialItems: StrengthProgressOut[] = [],
  exerciseNames: Record<number, string> = DEFAULT_EXERCISE_NAMES,
) {
  // Estado en memoria por exercise_id — simula "último registro por ejercicio".
  const store = new Map<number, StrengthProgressOut>(
    initialItems.map((item) => [item.exercise_id, item]),
  );

  const getHandler = http.get(
    `*/api/strength/athletes/${athleteId}/progress`,
    () => {
      return HttpResponse.json(makeAthleteProgress(Array.from(store.values())));
    },
  );

  const postHandler = http.post(
    `*/api/strength/athletes/${athleteId}/progress`,
    async ({ request }) => {
      const body = (await request.json()) as StrengthProgressInput;
      const existing = store.get(body.exercise_id);
      const entry = makeProgressOut({
        exercise_id: body.exercise_id,
        exercise_name:
          existing?.exercise_name ??
          exerciseNames[body.exercise_id] ??
          `Ejercicio ${body.exercise_id}`,
        status: body.status,
        coach_note: body.coach_note ?? null,
        season: body.season,
        recorded_at: new Date().toISOString(),
      });
      store.set(body.exercise_id, entry);
      return HttpResponse.json(entry, { status: 201 });
    },
  );

  return [getHandler, postHandler];
}

// ---------------------------------------------------------------------------
// Handler variants for specific test scenarios
// ---------------------------------------------------------------------------

/** Catálogo vacío (sin ejercicios). */
export const strengthEmptyCatalogHandler = http.get(
  "*/api/strength/exercises",
  () => HttpResponse.json(makeCatalogList([])),
);

/** Error de red — simula servidor iniciando (cold-start). */
export const strengthColdStartHandler = http.get(
  "*/api/strength/exercises",
  () => HttpResponse.error(),
);

/** Error 503 del servidor. */
export const strength503Handler = http.get(
  "*/api/strength/exercises",
  () => new HttpResponse(null, { status: 503 }),
);

/** 404 — ejercicio no encontrado. */
export const strengthExercise404Handler = http.get(
  "*/api/strength/exercises/:id",
  () => new HttpResponse(JSON.stringify({ detail: "No encontrado" }), { status: 404 }),
);

/** 404 — bloque no encontrado (modo edición). */
export const strengthBlock404Handler = http.get(
  "*/api/strength/blocks/:id",
  () => new HttpResponse(JSON.stringify({ detail: "No encontrado" }), { status: 404 }),
);

/** 422 — error de validación al guardar (crear) un bloque. */
export const strengthSaveBlockValidationErrorHandler = http.post(
  "*/api/strength/blocks",
  () =>
    new HttpResponse(JSON.stringify({ detail: "Datos inválidos" }), {
      status: 422,
    }),
);

/** 500 — error inesperado al adjuntar un bloque a una sesión. */
export const strengthAttachErrorHandler = http.post(
  "*/api/strength/blocks/:id/attach",
  () =>
    new HttpResponse(JSON.stringify({ detail: "Error inesperado" }), {
      status: 500,
    }),
);

/** 404 — atleta sin progreso de fuerza registrado todavía. */
export const strengthProgress404Handler = http.get(
  "*/api/strength/athletes/:athleteId/progress",
  () => new HttpResponse(JSON.stringify({ detail: "No encontrado" }), { status: 404 }),
);

/** 500 — error inesperado al cargar el progreso de un atleta. */
export const strengthProgress500Handler = http.get(
  "*/api/strength/athletes/:athleteId/progress",
  () =>
    new HttpResponse(JSON.stringify({ detail: "Error inesperado" }), {
      status: 500,
    }),
);

/** 422 — error de validación al registrar progreso. */
export const strengthAddProgressValidationErrorHandler = http.post(
  "*/api/strength/athletes/:athleteId/progress",
  () =>
    new HttpResponse(JSON.stringify({ detail: "Datos inválidos" }), {
      status: 422,
    }),
);
