/**
 * Utilidades compartidas del módulo "Análisis IA" del atleta.
 *
 * Centraliza helpers de parsing de insights v2, etiquetas de enums
 * y calendario Copa Valle para que sean reutilizables desde
 * InsightsTimeline, HeroLastInsightCard y cualquier componente futuro
 * sin duplicación.
 *
 * Privacidad: ninguna de estas funciones maneja datos PII directamente;
 * el control de visibilidad (modo coach vs parent) se hace en los
 * componentes que consumen estas utilidades.
 */
import type { InsightConfidence } from "@/types/athleteRaceAnalysis.types";
import type { ProgressionAssessment } from "@/types/raceAnalysis.types";
import type {
  ActionCategory,
  EvidenceDomain,
  Horizon,
  Priority,
} from "@/types/insightV3.types";

export const PROMPT_VERSION_V2 = "race_analyst_v2";

// ---------------------------------------------------------------------------
// Parsing markdown v2
// ---------------------------------------------------------------------------

/** Normaliza acentos y casing para comparar headers tolerando variantes. */
function normalizeHeader(s: string): string {
  return s
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .trim();
}

/**
 * Extrae el contenido de una sección markdown delimitada por un header ##.
 * Devuelve el texto entre el header encontrado y el siguiente header ## (o
 * fin de string).
 *
 * Usa `startsWith` sobre el header normalizado para tolerar variantes del
 * backend (ej: "## Qué pasó en esta válida" matchea con headerText "Qué pasó").
 */
export function extractSection(markdown: string, headerText: string): string {
  const lines = markdown.split("\n");
  const needle = normalizeHeader(headerText);
  let inside = false;
  const collected: string[] = [];
  for (const line of lines) {
    if (/^##\s/.test(line)) {
      if (inside) break;
      const headerInLine = normalizeHeader(line.replace(/^##\s+/, ""));
      if (headerInLine.startsWith(needle)) {
        inside = true;
        continue;
      }
    } else if (inside) {
      collected.push(line);
    }
  }
  return collected.join("\n").trim();
}

/**
 * Extrae el contenido de la sección "## Contexto de temporada" cuando está
 * presente en el summary_text (insights v2 generados a partir de US-2 / FR-007).
 * Devuelve null cuando la sección no existe — así los insights legacy no se ven
 * afectados.
 */
export function extractSeasonContext(summaryText: string): string | null {
  const content = extractSection(summaryText, "Contexto de temporada");
  return content.length > 0 ? content : null;
}

/**
 * Mapa de ProgressionAssessment a etiquetas en español colombiano (es-CO).
 * Usado en la insignia de progresión del detalle del insight.
 */
export function progressionLabel(assessment: ProgressionAssessment): string {
  switch (assessment) {
    case "improving":
      return "Mejorando";
    case "stable":
      return "Estable";
    case "declining":
      return "En descenso";
    case "mixed":
      return "Mixto";
    case "first_reference":
      return "Primera referencia de la temporada";
  }
}

/**
 * Para la preview de la card, extrae la primera línea no vacía del bloque
 * "Qué pasó" en insights v2. Si no hay sección, devuelve el texto completo.
 */
export function getV2Preview(summaryText: string): string {
  const section = extractSection(summaryText, "Qué pasó");
  if (!section) return summaryText;
  const firstLine = section
    .split("\n")
    .map((l) => l.trim())
    .find((l) => l.length > 0);
  return firstLine ?? summaryText;
}

// ---------------------------------------------------------------------------
// Etiquetas de enums — reutilizables en lista y hero card
// ---------------------------------------------------------------------------

/** Roman numerals for válidas 1..7 — misma tabla que `MiniSparkline.tsx`. */
const VALIDA_ROMAN_NUMERALS: Record<number, string> = {
  1: "I",
  2: "II",
  3: "III",
  4: "IV",
  5: "V",
  6: "VI",
  7: "VII",
};

export interface ValidaLabelInput {
  /**
   * 0 = agregado de temporada. 1..7 = válida regular. 99 = Cto.
   * Departamental bajo la convención retirada (usado solo como fallback,
   * ver `seriesKind`). `null`/`undefined` = no aplica.
   */
  valida_num?: number | null;
  /**
   * Identidad autoritativa (features 014/016): cuando está presente decide
   * "Válida N" vs "Cto. Departamental" en lugar de la convención retirada
   * `valida_num === 99`. `null`/`undefined` → cae al fallback numérico,
   * para llamadores legacy que aún no exponen este campo (ej.
   * `ClubInsightByRaceItem`, feature 036 T030).
   */
  series_kind?: string | null;
  /**
   * No afecta el texto devuelto — aceptados para que los llamadores puedan
   * pasar el insight/ítem del contrato tal cual, sin desestructurar. Ambos
   * pueden ser `null` (insight sin evento vinculado).
   */
  event_id?: number | null;
  event_date?: string | null;
}

/**
 * Etiqueta legible y única para una válida/campeonato/agregado de temporada:
 * "Válida III", "Cto. Departamental", "Resumen de temporada" o "—".
 *
 * Fuente única de verdad para este dato en toda la app (feature 036, T032)
 * — reemplaza los antiguos `validaLabel` (arábigo, este mismo módulo) y
 * `getValidaLabel` (romano, `lib/raceCalendar.ts`), que producían texto
 * distinto para el mismo insight. Formato romano adoptado de
 * `MiniSparkline.tsx`.
 *
 * La distinción "Cto. Departamental" vs válida regular usa `series_kind`
 * (feature 014/016) en vez de la convención retirada `valida_num === 99`
 * (T030) — ese chequeo numérico sobrevive únicamente como fallback para
 * llamadores que todavía no exponen `series_kind`.
 *
 * Acepta un número plano (atajo retrocompatible, ej. selectores que solo
 * conocen el número de válida) o el objeto `ValidaLabelInput` con el
 * contrato completo.
 */
export function validaLabel(
  input: number | null | undefined | ValidaLabelInput,
): string {
  const { valida_num: num, series_kind: seriesKind } =
    typeof input === "object" && input !== null ? input : { valida_num: input, series_kind: undefined };

  if (num === null || num === undefined) return "—";
  if (num === 0) return "Resumen de temporada";

  const isChampionship = seriesKind != null ? seriesKind === "championship" : num === 99;
  if (isChampionship) return "Cto. Departamental";

  return `Válida ${VALIDA_ROMAN_NUMERALS[num] ?? num}`;
}

/**
 * Adaptador canónico de confianza de insight → `StatusBadge`
 * (`contracts/status-vocabulary-sweep.md` §4). Reemplaza el par
 * `confidenceVariant`/`confidenceLabel` de abajo como la única fuente de
 * verdad para "alta/media/baja" en toda la app.
 */
export function confidenceStatus(
  confidence: InsightConfidence,
): { status: "success" | "warning" | "danger"; label: string } {
  if (confidence === "high") return { status: "success", label: "Confianza alta" };
  if (confidence === "medium") return { status: "warning", label: "Confianza media" };
  return { status: "danger", label: "Confianza baja" };
}

/**
 * @deprecated Usa `confidenceStatus()` — mantenido en términos de la
 * misma tabla mientras `HeroLastInsightCard.tsx`, `InsightsTimeline.tsx`,
 * `AthletesTab.tsx` e `InsightsTab.tsx` siguen consumiendo `<Badge
 * variant>` en lugar de `<StatusBadge>`. Su migración a `StatusBadge` no
 * está cubierta por ninguna tarea de `tasks.md` en este feature (solo
 * `AthleteAIAnalysisTab.tsx`'s duplicate lo está, vía T019) — se deja
 * aquí para no romper esos call sites.
 */
export function confidenceVariant(
  confidence: InsightConfidence,
): "success" | "warning" | "destructive" {
  if (confidence === "high") return "success";
  if (confidence === "medium") return "warning";
  return "destructive";
}

/** @deprecated Usa `confidenceStatus()` — ver nota en `confidenceVariant`. */
export function confidenceLabel(confidence: InsightConfidence): string {
  if (confidence === "high") return "Confianza alta";
  if (confidence === "medium") return "Confianza media";
  return "Confianza baja";
}

// ---------------------------------------------------------------------------
// Calendario Copa Valle 2026 — tier por mes-año
// ---------------------------------------------------------------------------

/**
 * Mapa mes-año → tier ordinal (intensidad de tapering) de la carrera Copa
 * Valle 2026. Clave: "YYYY-MM" (ISO). Valores tomados del CLAUDE.md §
 * Calendario Copa Valle 2026.
 *
 * `CD` (Campeonato Departamental) NO es un 4º tier: por
 * `contracts/chart-style.md` §"A/B/C ordinal scale" / `data-model.md` §2,
 * su intensidad de tapering real es **A** (tapering completo, 7 días) —
 * la distinción de campeonato es un hecho ortogonal, ya representado por
 * separado en el badge "CD" con ícono `Trophy`
 * (`CompetitionDetailPage.tsx:452-460`), no fusionado en esta escala.
 *
 *   I   31-ene (2026-01)  → C  (sin tapering)
 *   II  28-feb (2026-02)  → C
 *   III 19-abr (2026-04)  → C  (diagnóstica)
 *   IV  17-may (2026-05)  → A  (tapering completo)
 *   CD  12-jun (2026-06)  → A  (Campeonato Departamental, mismo tapering que A)
 *   V   01-ago (2026-08)  → B  (mini-tapering)
 *   VI  12-sep (2026-09)  → A
 *   VII 18-oct (2026-10)  → B
 */
const CARRERA_TIER: Record<string, "A" | "B" | "C"> = {
  "2026-01": "C",
  "2026-02": "C",
  "2026-04": "C",
  "2026-05": "A",
  "2026-06": "A",
  "2026-08": "B",
  "2026-09": "A",
  "2026-10": "B",
};

/**
 * Dado un insight (o su fecha ``generated_at``), devuelve el tier ordinal
 * (A/B/C) de la carrera Copa Valle correspondiente al mes-año de la fecha.
 * Devuelve ``null`` si la fecha no coincide con ninguna válida del calendario.
 *
 * @param date - ISO date string o Date object (``generated_at`` del insight).
 */
export function getCarreraTier(
  date: Date | string,
): "A" | "B" | "C" | null {
  const d = typeof date === "string" ? new Date(date) : date;
  if (!Number.isFinite(d.getTime())) return null;
  // getMonth() es 0-based — añadimos 1 y pad con "0".
  const month = String(d.getMonth() + 1).padStart(2, "0");
  const year = String(d.getFullYear());
  const key = `${year}-${month}`;
  return CARRERA_TIER[key] ?? null;
}

// ---------------------------------------------------------------------------
// Guía de tapering por tier de carrera — tile "Próxima carrera" (Inicio coach)
// ---------------------------------------------------------------------------

/**
 * Guía de tapering asociada a un tier de carrera Copa Valle.
 *
 * `taperDays` es la ventana de tapering completa en días (`[min, max]`),
 * `null` cuando el tier no tiene tapering (diagnóstica). `warningAt`/`dangerAt`
 * son los umbrales de `daysUntil` (días restantes hasta la carrera) que
 * disparan cada estado de urgencia en la tile ("upcoming"/"in_window");
 * ambos `null` cuando el tier nunca escala urgencia (tier C).
 */
export interface TaperGuidance {
  label: string;
  taperDays: [number, number] | null;
  warningAt: number | null;
  dangerAt: number | null;
}

/**
 * Mapa tier → guía de tapering, clave según `getCarreraTier`.
 *
 * Copia exacta de las etiquetas de categoría ya usadas en el wizard de
 * calendario (`EventForm.tsx:71-75`, `COMPETITION_CATEGORIES`) para A/B/C.
 * El Campeonato Departamental (junio) resuelve a tier `A` desde
 * `CARRERA_TIER` — no tiene entrada propia aquí (ver nota en
 * `CARRERA_TIER`); su distinción de campeonato la sigue llevando el badge
 * "CD" independiente en `CompetitionDetailPage.tsx`.
 *
 * Umbrales de urgencia (`warningAt`/`dangerAt`) per
 * `specs/031-coach-home-mission-control/contracts/home-tiles.md`:
 * A → warning en `daysUntil <= 10`, in_window en `daysUntil <= 7`;
 * B → warning en `daysUntil <= 6`, in_window en `daysUntil <= 4`;
 * C → siempre neutral (no existe ventana de tapering para una diagnóstica).
 */
export const TAPER_GUIDANCE: Record<"A" | "B" | "C", TaperGuidance> = {
  A: {
    label: "A — Tapering completo",
    taperDays: [5, 7],
    warningAt: 10,
    dangerAt: 7,
  },
  B: {
    label: "B — Mini-tapering",
    taperDays: [3, 4],
    warningAt: 6,
    dangerAt: 4,
  },
  C: {
    label: "C — Diagnóstica",
    taperDays: null,
    warningAt: null,
    dangerAt: null,
  },
};

// ---------------------------------------------------------------------------
// InsightV3 — etiquetas de enums en español (feature 037, T301)
// ---------------------------------------------------------------------------

/** Etiqueta es-CO del dominio de evidencia de una observación v3. */
export function evidenceDomainLabel(domain: EvidenceDomain): string {
  switch (domain) {
    case "race":
      return "Carrera";
    case "field":
      return "Pista";
    case "training":
      return "Entrenamiento";
    case "maturation":
      return "Maduración";
    case "conditions":
      return "Condiciones";
    case "history":
      return "Histórico";
  }
}

/** Etiqueta es-CO de la categoría de una acción v3. */
export function actionCategoryLabel(category: ActionCategory): string {
  switch (category) {
    case "technique":
      return "Técnica";
    case "volume":
      return "Volumen";
    case "recovery":
      return "Recuperación";
    case "nutrition":
      return "Nutrición";
    case "psychology":
      return "Psicología";
    case "tactics":
      return "Táctica";
  }
}

/** Etiqueta es-CO de prioridad de una acción v3. */
export function priorityLabel(priority: Priority): string {
  switch (priority) {
    case "high":
      return "Prioridad alta";
    case "med":
      return "Prioridad media";
    case "low":
      return "Prioridad baja";
  }
}

/** Variante de `Badge` para la prioridad de una acción v3. */
export function priorityVariant(
  priority: Priority,
): "destructive" | "warning" | "secondary" {
  if (priority === "high") return "destructive";
  if (priority === "med") return "warning";
  return "secondary";
}

/** Etiqueta es-CO del horizonte temporal de una acción v3. */
export function horizonLabel(horizon: Horizon): string {
  switch (horizon) {
    case "next_week":
      return "Próxima semana";
    case "next_race":
      return "Próxima carrera";
    case "season":
      return "Temporada";
  }
}
