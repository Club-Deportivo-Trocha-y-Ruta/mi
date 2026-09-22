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
import type {
  AnalysisConfidence,
  InsightConfidence,
} from "@/types/athleteRaceAnalysis.types";
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

/** Roman numerals for válidas 1..12 (2025 had eight) — misma tabla que `MiniSparkline.tsx`. */
const VALIDA_ROMAN_NUMERALS: Record<number, string> = {
  1: "I",
  2: "II",
  3: "III",
  4: "IV",
  5: "V",
  6: "VI",
  7: "VII",
  8: "VIII",
  9: "IX",
  10: "X",
  11: "XI",
  12: "XII",
};

// ---------------------------------------------------------------------------
// raceLabel — hotfix multicopa (2026-09-16)
// ---------------------------------------------------------------------------

export interface RaceLabelInput {
  /** Nombre completo de la copa/serie, ej. "Copa Let's GO". `null` en
   * insights legacy (sin columna) o carreras sin serie vinculada. */
  seriesName?: string | null;
  /** Abreviación para chip, ej. "Let's GO". */
  seriesShortName?: string | null;
  /** 0 = agregado de temporada. 1..N = válida regular. `null` = no aplica. */
  validaNum?: number | null;
  /** `true` para Cto. Departamental/Nacional — nunca lleva nombre de copa. */
  isChampionship?: boolean | null;
  /** Nivel del campeonato (`"departmental"` | `"national"`). Ignorado para
   * copas. `null`/`undefined` → default "departamental" (mismo criterio
   * histórico de `validaLabel`). */
  seriesLevel?: string | null;
  /** Sede de la carrera — se agrega solo en el form "long", cuando llega. */
  location?: string | null;
}

export interface RaceLabelOptions {
  form: "long" | "chip";
}

/**
 * Etiqueta de válida/campeonato/agregado de temporada que SIEMPRE nombra la
 * copa cuando el dato está disponible — reemplaza `validaLabel` como fuente
 * única de verdad (hotfix multicopa, `plans/multicopa-identidad-valida.md`):
 * `validaLabel` nunca mostraba a qué copa pertenecía una válida ("Válida
 * IV" a secas), lo que dejaba a la UI indistinguible entre la Válida IV de
 * dos copas distintas de la misma temporada — el mismo colapso de
 * identidad que produjo el bug de análisis IA cruzado entre copas.
 *
 * Formas:
 *   - `"long"`:  "Copa Let's GO · Válida IV — Alcalá" (nombre completo +
 *     válida en romano + sede si se pasó `location`).
 *   - `"chip"`:  "Let's GO · V4" (abreviación + válida arábiga compacta).
 *
 * Los campeonatos NUNCA llevan nombre de copa — conservan el mismo texto
 * fijo de siempre ("Cto. Departamental"/"Cto. Nacional", `seriesLevel`),
 * por decisión de producto (no reabrir, ver plan del hotfix).
 *
 * `seriesName`/`seriesShortName` ausentes o `null` (insights previos a la
 * columna, o carrera sin serie vinculada) caen al rótulo histórico sin
 * copa — NUNCA se inventa un nombre de copa.
 */
export function raceLabel(
  input: RaceLabelInput,
  options: RaceLabelOptions,
): string {
  const {
    seriesName,
    seriesShortName,
    validaNum,
    isChampionship,
    seriesLevel,
    location,
  } = input;

  if (validaNum === null || validaNum === undefined) return "—";
  if (validaNum === 0) return "Resumen de temporada";

  if (isChampionship) {
    const champLabel =
      seriesLevel === "national" ? "Cto. Nacional" : "Cto. Departamental";
    return options.form === "long" && location
      ? `${champLabel} — ${location}`
      : champLabel;
  }

  const validaRoman = VALIDA_ROMAN_NUMERALS[validaNum] ?? String(validaNum);
  const cupName =
    options.form === "chip"
      ? (seriesShortName ?? seriesName ?? null)
      : (seriesName ?? seriesShortName ?? null);

  if (options.form === "chip") {
    return cupName ? `${cupName} · V${validaNum}` : `Válida ${validaRoman}`;
  }

  const base = cupName
    ? `${cupName} · Válida ${validaRoman}`
    : `Válida ${validaRoman}`;
  return location ? `${base} — ${location}` : base;
}

/**
 * Adaptador de `raceLabel` para un insight (`AthleteInsightOut` o
 * `ClubInsightByRaceItem`) — evita repetir en cada call site la misma
 * derivación de `isChampionship` que ya usaba `validaLabel`
 * (`series_kind` cuando está presente; si no, el fallback retirado
 * `valida_num === 99` para filas/tipos legacy sin `series_kind`, ej.
 * `ClubInsightByRaceItem`).
 */
export function raceLabelForInsight(
  insight: {
    valida_num?: number | null;
    series_kind?: "cup" | "championship" | null;
    series_level?: string | null;
    series_name?: string | null;
    series_short_name?: string | null;
  },
  form: "long" | "chip",
): string {
  const isChampionship =
    insight.series_kind != null
      ? insight.series_kind === "championship"
      : insight.valida_num === 99;
  return raceLabel(
    {
      validaNum: insight.valida_num,
      isChampionship,
      seriesLevel: insight.series_level,
      seriesName: insight.series_name,
      seriesShortName: insight.series_short_name,
    },
    { form },
  );
}

/**
 * Umbrales de confianza estadística sobre un conjunto de puntos —
 * réplica en cliente de `analytics_charts.py::_confidence_from_n`
 * (feature 039, F-2): `n<3` → `"low"`, `n>=8` → `"high"`, resto
 * `"medium"`. Cuenta solo puntos con `value` no-nulo (DNF/DNS no cuentan
 * como muestra útil), igual que el backend.
 *
 * Usado por `EvolutionChart` para derivar el aviso de confianza sobre el
 * grupo efectivamente mostrado (`displaySeries`) cuando la respuesta del
 * backend todavía no viene filtrada por `series_id` — en ese caso
 * `EvolutionResponse.confidence` está calculado sobre TODA la temporada,
 * no sobre el grupo por defecto que el cliente ya está mostrando
 * (`contracts/evolution-api.md` FR-009).
 */
export function confidenceForPoints(
  points: Array<{ value: number | null }>,
): AnalysisConfidence {
  const n = points.filter((p) => p.value !== null).length;
  if (n < 3) return "low";
  if (n >= 8) return "high";
  return "medium";
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
 * misma tabla mientras `HeroLastInsightCard.tsx`, `InsightsTimeline.tsx`
 * e `InsightsTab.tsx` siguen consumiendo `<Badge
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
// Guía de tapering por tier de carrera — tile "Próxima carrera" (Inicio coach)
// ---------------------------------------------------------------------------

/**
 * Guía de tapering asociada a un tier de carrera.
 *
 * `taperDays` es la ventana de tapering completa en días (`[min, max]`),
 * `null` cuando el tier no tiene tapering (diagnóstica). `warningAt`/`dangerAt`
 * son los umbrales de `daysUntil` (días restantes hasta la carrera) que
 * disparan cada estado de urgencia en la tile ("upcoming"/"in_window");
 * ambos `null` cuando el tier nunca escala urgencia (tier C).
 *
 * Wave 3 (hotfix multicopa, 2026-09-16): el tier ya NO se deriva de un
 * calendario Copa Valle hardcodeado por mes (`getCarreraTier`/
 * `CARRERA_TIER`, retirados) — viene de `race_events.priority` ('A'|'B'|
 * 'C'|'CD', `RaceEventPriority`), real por evento y válido para cualquier
 * copa. `CD` (campeonato) se sigue leyendo como tier `A` en los call sites
 * (`NextRaceTile.tsx`, `InsightsTimeline.tsx`) — misma intensidad de
 * tapering completo, sin entrada propia acá; la distinción de campeonato
 * la sigue llevando su propio badge/ícono, no esta escala.
 */
export interface TaperGuidance {
  label: string;
  taperDays: [number, number] | null;
  warningAt: number | null;
  dangerAt: number | null;
}

/**
 * Mapa tier → guía de tapering.
 *
 * Copia exacta de las etiquetas de categoría ya usadas en el wizard de
 * calendario (`EventForm.tsx:71-75`, `COMPETITION_CATEGORIES`) para A/B/C.
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
