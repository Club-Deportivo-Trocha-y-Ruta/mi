/**
 * Línea de tiempo de insights aprobados del atleta (FE-1).
 *
 * Sprint 2 (BB1 + BB4):
 *   - Agrupación por mes-año con header sticky y badge de carrera tier.
 *   - Shape diferenciado por tipo: resumen-temporada (borde primary + Trophy),
 *     Cto. Departamental (borde amber + Medal), válida normal (compacto).
 *   - Checkbox multi-select solo para coach (BB4).
 *   - Click en card abre Sheet (mobile) o Dialog (md+) con detalle completo.
 *
 * Privacidad: el backend ya filtra el listado según el rol. El checkbox de
 * multi-select NUNCA se renderiza para mode="parent".
 *
 * Accesibilidad:
 *   - Cada card es un ``<button>`` con ``aria-label`` legible.
 *   - El detalle abre como modal con foco trapado (Radix lo da).
 *   - El estado de loading expone ``role="status" aria-busy``.
 */
import React, { useEffect, useMemo, useState } from "react";
import { AlertCircle, ChevronRight, History, Loader2, Medal, RefreshCw, Sparkles, Trophy, TrendingDown, TrendingUp, Minus, GitBranch } from "lucide-react";

import { MarkdownReportViewer } from "@/components/ai/MarkdownReportViewer";
import { ErrorState, isColdStartError } from "@/components/shared/ErrorState";
import { useGenerateSeasonSummary } from "@/hooks/athletes/useGenerateSeasonSummary";
import { useLaunchAthleteAnalysis } from "@/hooks/athletes/useLaunchAthleteAnalysis";
import { InsightN1Banner } from "./InsightN1Banner";
import { CoachAnswerForm } from "./CoachAnswerForm";
import { InsightV3Card } from "./v3/InsightV3Card";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Sheet,
  SheetBody,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { useAthleteInsightDetail } from "@/hooks/athletes/useAthleteInsightDetail";
import { useAthleteInsights } from "@/hooks/athletes/useAthleteInsights";
import { extractErrorDetail } from "@/lib/apiError";
import { formatDateTimeCompact } from "@/lib/datetime";
import {
  confidenceLabel,
  confidenceVariant,
  extractSection,
  extractSeasonContext,
  getCarreraTier,
  getV2Preview,
  progressionLabel,
  PROMPT_VERSION_V2,
  validaLabel,
} from "@/lib/insights";
import { cn } from "@/lib/utils";
import type {
  AthleteInsightDetailOut,
  AthleteInsightOut,
  InsightLink,
  InsightParsedSections,
} from "@/types/athleteRaceAnalysis.types";
import type { ProgressionAssessment } from "@/types/raceAnalysis.types";

// ---------------------------------------------------------------------------
// Helpers locales — parsing v2 (parseV2Sections usa extractSection de lib)
// ---------------------------------------------------------------------------

function parseV2Sections(summaryText: string): InsightParsedSections {
  return {
    what_happened: extractSection(summaryText, "Qué pasó") || undefined,
    journey_so_far:
      extractSection(summaryText, "Recorrido hasta") || undefined,
    looking_ahead: extractSection(summaryText, "Hacia dónde va") || undefined,
    season_summary:
      extractSection(summaryText, "Resumen de temporada") || undefined,
    season_context: extractSeasonContext(summaryText) || undefined,
  };
}

// ---------------------------------------------------------------------------
// Progression assessment helpers
// ---------------------------------------------------------------------------

const VALID_PROGRESSION_ASSESSMENTS: ReadonlySet<string> = new Set<ProgressionAssessment>([
  "improving",
  "stable",
  "declining",
  "mixed",
  "first_reference",
]);

/**
 * Extrae ``progression_assessment`` del campo ``metrics_snapshot`` del detalle
 * del insight. Devuelve null cuando el campo no existe (insights legacy) para
 * garantizar compatibilidad hacia atrás.
 */
function extractProgressionAssessment(
  insight: AthleteInsightDetailOut,
): ProgressionAssessment | null {
  const snapshot = insight.metrics_snapshot;
  if (!snapshot || typeof snapshot !== "object") return null;
  const val = (snapshot as Record<string, unknown>)["progression_assessment"];
  if (typeof val === "string" && VALID_PROGRESSION_ASSESSMENTS.has(val)) {
    return val as ProgressionAssessment;
  }
  return null;
}

/** Icono + variante de Badge para cada assessment. */
const PROGRESSION_CONFIG: Record<
  ProgressionAssessment,
  { variant: "success" | "warning" | "destructive" | "secondary" | "outline"; Icon: React.ElementType }
> = {
  improving: { variant: "success", Icon: TrendingUp },
  stable: { variant: "secondary", Icon: Minus },
  declining: { variant: "destructive", Icon: TrendingDown },
  mixed: { variant: "warning", Icon: GitBranch },
  first_reference: { variant: "outline", Icon: Sparkles },
};

function ProgressionBadge({ assessment }: { assessment: ProgressionAssessment }) {
  const { variant, Icon } = PROGRESSION_CONFIG[assessment];
  return (
    <Badge
      variant={variant}
      className="gap-1"
      data-testid="progression-badge"
      aria-label={`Progresión: ${progressionLabel(assessment)}`}
    >
      <Icon size={11} aria-hidden="true" />
      {progressionLabel(assessment)}
    </Badge>
  );
}

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface InsightsTimelineProps {
  athleteId: number;
  mode: "coach" | "parent";
  /** Controlado desde el padre para abrir el drawer via PanoramaView. */
  selectedInsightId?: number | null;
  /** Callback para levantar el estado al padre cuando cambia la selección. */
  onSelectInsight?: (id: number | null) => void;
  /** IDs actualmente seleccionados para boletín (BB4). Solo coach. */
  newsletterSelection?: Set<number>;
  /** Toggle del checkbox de boletín (BB4). Solo coach. */
  onToggleSelection?: (id: number) => void;
}

// ---------------------------------------------------------------------------
// Utilidad: matchMedia hook
// ---------------------------------------------------------------------------

function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState<boolean>(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
      return false;
    }
    return window.matchMedia(query).matches;
  });

  useEffect(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
      return;
    }
    const mql = window.matchMedia(query);
    const handler = (e: MediaQueryListEvent) => setMatches(e.matches);
    if (typeof mql.addEventListener === "function") {
      mql.addEventListener("change", handler);
      return () => mql.removeEventListener("change", handler);
    }
    mql.addListener(handler);
    return () => mql.removeListener(handler);
  }, [query]);

  return matches;
}

// ---------------------------------------------------------------------------
// Helpers de UI por tipo de insight
// ---------------------------------------------------------------------------

type InsightShape = "season-summary" | "departamental" | "normal";

/**
 * Resuelve el shape visual (borde + ícono) de una card del histórico.
 *
 * La distinción "departamental" usa `series_kind` (features 014/016), igual
 * que `validaLabel` (`lib/insights.ts`) — no la convención retirada
 * `valida_num === 99` (feature 036, T030): un campeonato moderno puede tener
 * su propio `valida_num` de secuencia (no literalmente 99) y aun así ser
 * departamental. El chequeo numérico sobrevive solo como fallback para
 * insights legacy sin `series_kind`.
 */
function resolveShape(
  insight: Pick<AthleteInsightOut, "valida_num" | "series_kind">,
): InsightShape {
  if (insight.valida_num === 0) return "season-summary";
  const isChampionship =
    insight.series_kind != null
      ? insight.series_kind === "championship"
      : insight.valida_num === 99;
  return isChampionship ? "departamental" : "normal";
}

/**
 * Formatea un ``event_date`` (columna DATE sin componente horario, ej.
 * "2026-05-17") como "17 may 2026".
 *
 * OJO: no reusa los formatters de `lib/datetime.ts` (`formatDateMedium` y
 * hermanos) — están pensados para timestamps y proyectan a
 * `CLUB_TIMEZONE` (America/Bogotá, UTC-5), lo cual es correcto para una
 * hora real pero rompe una fecha pura: `new Date("2026-05-17")` la
 * interpreta como medianoche UTC, y proyectar eso a UTC-5 la corre un día
 * atrás ("16 may" para una carrera del 17). Verificado en consola antes de
 * escribir esto. Mismo patrón ya usado para `event_date` en
 * `competitions/tabs/InfoTab.tsx` y `routes/competitions/
 * CompetitionDetailPage.tsx`: parsear año/mes/día del string y construir el
 * `Date` con el constructor local (sin paso por UTC), evitando el corrimiento.
 */
function formatRaceDate(isoDate: string): string {
  const [year, month, day] = isoDate.split("-");
  if (!year || !month || !day) return isoDate;
  const date = new Date(Number(year), Number(month) - 1, Number(day));
  return date.toLocaleDateString("es-CO", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

/**
 * Etiqueta de válida/campeonato + fecha de carrera embebida (feature 036,
 * T033) — mismo patrón "CD · 12 jun" que el picker de lanzamiento
 * (`LaunchAnalysisForm.tsx`, T031) usa para desambiguar carreras del mismo
 * tipo, pero con año: a diferencia del picker, este histórico no está
 * acotado a una sola temporada, así que dos "Cto. Departamental" de años
 * distintos no deben leerse igual. También es lo que ancla la fecha visible
 * de cada fila al mismo dato (`event_date`) que ya ordena el listado en el
 * servidor (`insights_history.list_athlete_insights`), en vez de mostrar
 * `generated_at` como si fuera la fecha de la carrera.
 *
 * Sin `event_date` (resumen de temporada, filas legacy sin evento
 * vinculado) devuelve solo la etiqueta de `validaLabel` — no inventamos
 * una fecha de carrera que no existe.
 */
function validaLabelWithDate(
  insight: Pick<AthleteInsightOut, "valida_num" | "series_kind" | "event_date">,
): string {
  const label = validaLabel({
    valida_num: insight.valida_num,
    series_kind: insight.series_kind,
  });
  return insight.event_date
    ? `${label} · ${formatRaceDate(insight.event_date)}`
    : label;
}

/**
 * Clases del ramp ordinal A/B/C (feature 033, `contracts/chart-style.md`
 * §"A/B/C ordinal scale") — un solo matiz (accent teal de la marca),
 * lightness monótono. El Campeonato Departamental ("CD") ya no es un 4º
 * valor: `getCarreraTier` lo resuelve a tier `A` (ver `lib/insights.ts`).
 */
const TIER_RAMP_CLASSES: Record<"A" | "B" | "C", string> = {
  A: "border-[--color-tier-a]/40 bg-[--color-tier-a]/10 text-[--color-tier-a]",
  B: "border-[--color-tier-b]/40 bg-[--color-tier-b]/10 text-[--color-tier-b]",
  C: "border-[--color-tier-c]/40 bg-[--color-tier-c]/10 text-[--color-tier-c]",
};

/**
 * Badge del tier de carrera Copa Valle (A / B / C — ordinal, nunca color de
 * estado). La letra siempre se renderiza como texto visible ("Carrera A"),
 * nunca como un punto de color aislado (Constitution III, FR-002).
 */
function CarreraTierBadge({ tier }: { tier: "A" | "B" | "C" }) {
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center rounded-full border px-2 py-0.5 text-[10px] font-medium",
        TIER_RAMP_CLASSES[tier],
      )}
      aria-label={`Tipo de carrera: ${tier}`}
    >
      Carrera {tier}
    </span>
  );
}

/**
 * T095 (feature 036, US6): antes este sub-tab solo tenía un `aria-label` en
 * el `div` que envuelve la lista agrupada — un `div` con `aria-label` no
 * expone ningún nombre a lectores de pantalla (un `div` es `role="generic"`,
 * que no calcula nombre accesible), así que la navegación por encabezados
 * (tecla "H") saltaba de la Panorama al resto sin pasar por "Histórico".
 * Las otras 3 sub-vistas (`EvolutionChart`, `DistributionChart`,
 * `LaunchAnalysisForm`) ya usan un `<h3>` real bajo el `<h2>` de
 * `AthleteAIAnalysisTab.tsx` — este heading iguala ese patrón.
 *
 * Se renderiza en los 4 branches de `InsightsTimeline` (loading/error/
 * empty/lista) para que el heading exista sin importar el estado de carga,
 * igual que el `<h3>` de las otras sub-vistas (siempre dentro de su
 * `<section>`, nunca condicionado a que la query ya haya resuelto).
 *
 * El `aria-label` existente del `div` de la lista NO se retira: varios
 * tests (`InsightsTimeline.test.tsx`) usan
 * `getByLabelText(/histórico de análisis del deportista/i)` para acotar la
 * búsqueda al contenedor — tener heading + aria-label a la vez es válido.
 */
function HistoryHeading() {
  return (
    <h3
      className="font-display mb-3 flex items-center gap-2 text-sm text-charcoal"
      style={{ letterSpacing: "0.2px" }}
    >
      <History size={16} aria-hidden="true" />
      Histórico
    </h3>
  );
}

// ---------------------------------------------------------------------------
// Componente principal
// ---------------------------------------------------------------------------

export function InsightsTimeline({
  athleteId,
  mode,
  selectedInsightId: controlledInsightId,
  onSelectInsight,
  newsletterSelection,
  onToggleSelection,
}: InsightsTimelineProps) {
  const insightsQuery = useAthleteInsights(athleteId, {
    latest_only: true,
    limit: 50,
  });

  const [localInsightId, setLocalInsightId] = useState<number | null>(null);
  const selectedInsightId = controlledInsightId ?? localInsightId;
  const setSelectedInsightId = (id: number | null) => {
    setLocalInsightId(id);
    onSelectInsight?.(id);
  };
  const isDesktop = useMediaQuery("(min-width: 768px)");

  const items: AthleteInsightOut[] = insightsQuery.data?.items ?? [];

  // ---- Agrupación por mes-año (BB1) ----------------------------------------
  const grouped = useMemo(() => {
    const map = new Map<string, AthleteInsightOut[]>();
    items.forEach((i) => {
      const d = new Date(i.generated_at);
      const key = new Intl.DateTimeFormat("es-CO", {
        month: "long",
        year: "numeric",
      }).format(d);
      const arr = map.get(key) ?? [];
      arr.push(i);
      map.set(key, arr);
    });
    return Array.from(map.entries());
  }, [items]);

  // ---- Loading state -------------------------------------------------------
  if (insightsQuery.isLoading) {
    return (
      <>
        <HistoryHeading />
        <div
          role="status"
          aria-busy="true"
          aria-label="Cargando histórico de análisis"
          className="space-y-3"
        >
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-28 w-full rounded-xl" />
          ))}
        </div>
      </>
    );
  }

  // ---- Error state ---------------------------------------------------------
  // T039 (feature 036): adopta el bloque compartido ErrorState — trae la
  // variante "cold start" (Render Free ~50s) y el botón "Reintentar" que el
  // párrafo rojo ad hoc de antes no tenía.
  if (insightsQuery.isError) {
    const coldStart = isColdStartError(insightsQuery.error);
    return (
      <>
        <HistoryHeading />
        <ErrorState
          message={
            coldStart ? undefined : "No pudimos cargar el histórico de análisis."
          }
          onRetry={() => void insightsQuery.refetch()}
          isColdStart={coldStart}
        />
      </>
    );
  }

  // ---- Empty state ---------------------------------------------------------
  if (items.length === 0) {
    return (
      <>
        <HistoryHeading />
        <div
          className={cn("rounded-xl bg-white p-8 text-center", "shadow-card")}
        >
          <Sparkles
            size={28}
            className="mx-auto text-mid-gray"
            aria-hidden="true"
          />
          <p className="mt-3 text-sm font-medium text-charcoal">
            Aún no hay análisis aprobados para este deportista.
          </p>
          <p className="mt-1 text-xs text-mid-gray">
            {mode === "coach"
              ? 'Lanza un análisis desde la pestaña "Analizar con IA" para crear el primero.'
              : "Cuando tu entrenador apruebe un análisis, lo verás aquí."}
          </p>
        </div>
      </>
    );
  }

  // ---- Lista agrupada (BB1) ------------------------------------------------
  return (
    <>
      <HistoryHeading />
      <div
        className="space-y-0 overflow-hidden rounded-xl"
        aria-label="Histórico de análisis del deportista"
      >
        {grouped.map(([monthKey, groupItems]) => {
          // Tier de carrera basado en la fecha del primer item del grupo.
          // Solo se muestra si NINGUNO de los items es resumen-temporada
          // (valida_num === 0).
          const hasSeasonSummary = groupItems.some((i) => i.valida_num === 0);
          const firstDate = groupItems[0]?.generated_at;
          const tier =
            !hasSeasonSummary && firstDate
              ? getCarreraTier(firstDate)
              : null;

          return (
            <section key={monthKey} className="space-y-2 pb-4">
              {/* Header sticky del grupo */}
              <div className="sticky top-0 z-10 flex items-center gap-2 bg-white/95 px-3 py-2 backdrop-blur-sm">
                <span className="text-xs font-semibold uppercase tracking-wide text-mid-gray">
                  {monthKey}
                </span>
                {tier && <CarreraTierBadge tier={tier} />}
              </div>

              {/* Cards del grupo */}
              <ul className="space-y-2 px-1">
                {groupItems.map((insight) => {
                  const shape = resolveShape(insight);
                  const isSelected =
                    newsletterSelection?.has(insight.id) ?? false;

                  return (
                    <li key={insight.id}>
                      <InsightCard
                        athleteId={athleteId}
                        insight={insight}
                        shape={shape}
                        mode={mode}
                        isSelected={isSelected}
                        onOpen={() => setSelectedInsightId(insight.id)}
                        onToggleSelection={
                          mode === "coach" ? onToggleSelection : undefined
                        }
                      />
                    </li>
                  );
                })}
              </ul>
            </section>
          );
        })}
      </div>

      <InsightDetailDrawer
        athleteId={athleteId}
        insightId={selectedInsightId}
        onClose={() => setSelectedInsightId(null)}
        useDialog={isDesktop}
        mode={mode}
      />
    </>
  );
}

// ---------------------------------------------------------------------------
// InsightCard — card individual con shape por tipo + checkbox multi-select
// ---------------------------------------------------------------------------

const REGENERATE_ERROR_FALLBACK = "No se pudo regenerar. Intenta de nuevo.";
const RETRY_ERROR_FALLBACK = "No se pudo reintentar. Intenta de nuevo.";

/**
 * Alerta de fallo de una acción de fila (Regenerar / Reintentar).
 *
 * Antes esto era un `<p>` de 10px encajado en la columna del botón
 * (`max-w-28 text-right`), dimensionado para la copy genérica de 5 palabras.
 * Los `detail` reales del backend (`athlete_race_analysis.py`: run activo,
 * válida ambigua) rondan los 140 caracteres y ahí quedaban ilegibles, así que
 * la alerta salió de esa columna y ocupa el ancho completo de la fila, debajo
 * del card — el botón conserva su piso táctil de 48×48px (`min-h-12
 * min-w-12`) y la fila no se deforma por el largo del mensaje.
 *
 * Mismo shape que la alerta de `NewsletterNarrativeEditor.tsx` (ícono +
 * texto sobre `border-red-200 bg-red-50`); `text-red-800` sobre `bg-red-50`
 * mantiene el contraste muy por encima de 4.5:1 aun a 12px.
 */
function RowActionAlert({
  message,
  testId,
}: {
  message: string;
  testId: string;
}) {
  return (
    <div
      role="alert"
      data-testid={testId}
      className="mt-2 flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2"
    >
      <AlertCircle
        size={14}
        className="mt-0.5 shrink-0 text-red-600"
        aria-hidden="true"
      />
      <p className="text-xs leading-relaxed text-red-800">{message}</p>
    </div>
  );
}

interface InsightCardProps {
  athleteId: number;
  insight: AthleteInsightOut;
  shape: InsightShape;
  mode: "coach" | "parent";
  isSelected: boolean;
  onOpen: () => void;
  onToggleSelection?: (id: number) => void;
}

function InsightCard({
  athleteId,
  insight,
  shape,
  mode,
  isSelected,
  onOpen,
  onToggleSelection,
}: InsightCardProps) {
  // Fallback (US4, feature 036): la fila fue persistida por el camino de
  // FALLA de `deterministic_fallback` — el summary_text es el placeholder
  // fijo, no un análisis real. Nunca es seleccionable para el boletín y usa
  // "Reintentar" en vez de "Regenerar" (ver abajo).
  const isFallback = insight.is_fallback === true;
  const showCheckbox = mode === "coach" && !!onToggleSelection && !isFallback;
  // Regenerar (feature 011, US6): solo coach, solo válidas concretas (no el
  // resumen de temporada, valida_num=0) y solo sobre análisis reales — una
  // fila fallback usa "Reintentar" en su lugar. Re-lanza el análisis de ESA
  // válida; el backend deprecca el insight viejo al aprobar el nuevo
  // (reemplazo en 1 acción).
  const canRegenerate =
    mode === "coach" &&
    !isFallback &&
    insight.valida_num !== null &&
    insight.valida_num !== 0;
  const regenerate = useLaunchAthleteAnalysis(athleteId);
  const handleRegenerate = () => {
    if (insight.valida_num === null) return;
    regenerate.mutate({
      season: insight.season,
      valida_nums: [insight.valida_num],
      event_id: insight.event_id,
      explain_mode: false,
    });
  };

  // Reintentar (US4, feature 036): solo coach, solo filas fallback — el
  // análisis anterior FALLÓ, no es un análisis real que el coach quiera
  // repetir. Reusa el mismo lanzador por válida; el resumen de temporada
  // (valida_num=0) usa su propio endpoint on-demand.
  const canRetry = mode === "coach" && isFallback;
  const isSeasonSummaryRow = insight.valida_num === 0;
  const seasonRetry = useGenerateSeasonSummary(athleteId);
  const handleRetry = () => {
    if (isSeasonSummaryRow) {
      seasonRetry.mutate();
      return;
    }
    if (insight.valida_num === null) return;
    regenerate.mutate({
      season: insight.season,
      valida_nums: [insight.valida_num],
      event_id: insight.event_id,
      explain_mode: false,
    });
  };
  const retryPending = isSeasonSummaryRow
    ? seasonRetry.isPending
    : regenerate.isPending;
  const retryFailed = isSeasonSummaryRow
    ? seasonRetry.isError
    : regenerate.isError;

  // Borde izquierdo y ícono según tipo. Una fila fallback siempre usa el
  // mismo tratamiento neutro, sin importar el shape del insight que no
  // llegó a generarse.
  const borderCls = isFallback
    ? "border-l-4 border-dashed border-mid-gray/60 bg-light-gray/20"
    : shape === "season-summary"
      ? "border-l-4 border-primary"
      : shape === "departamental"
        ? "border-l-4 border-amber-400"
        : "";

  return (
    <div className="relative">
      <div className="flex items-start gap-2">
        {/* Checkbox multi-select (solo coach) — BB4. T091 (feature 036, US6):
            el tamaño se fija en el propio <input> (antes h-4 w-4, 16px), no en
            un wrapper con padding — el sweep e2e de target-size.spec.ts mide
            el boundingBox() real del elemento `input`, así que un wrapper más
            grande no bastaría. Mismo patrón ya probado en feature 032
            (`TechniqueAttachPicker.tsx`'s checkbox seleccionable, también
            h-12 w-12 directo en el input) para alcanzar el piso de 48×48px. */}
        {showCheckbox && (
          <div className="flex shrink-0 items-center pt-4 pl-1">
            <input
              type="checkbox"
              id={`insight-checkbox-${insight.id}`}
              data-testid={`insight-checkbox-${insight.id}`}
              checked={isSelected}
              onChange={() => onToggleSelection?.(insight.id)}
              aria-label={`Seleccionar análisis ${validaLabelWithDate(insight)} para boletín`}
              className="h-12 w-12 cursor-pointer rounded border-mid-gray accent-primary"
            />
          </div>
        )}

        {/* Superficie de la card. Antes el blanco + sombra vivían en el
            <button> del contenido, así que "Regenerar" quedaba flotando
            sobre el fondo de la página, sin relación visual con la fila que
            regenera. Ahora la card envuelve contenido + acción + alerta, y
            el botón se separa con un divisor en vez de con aire. */}
        <div
          data-testid={`insight-surface-${insight.id}`}
          className={cn(
            "flex min-w-0 flex-1 flex-col overflow-hidden rounded-xl bg-white shadow-card",
            borderCls,
          )}
        >
          <div className="flex items-stretch">
        <button
          type="button"
          onClick={onOpen}
          data-testid={`insight-card-${insight.id}`}
          aria-label={`Ver análisis del ${formatDateTimeCompact(insight.generated_at)}, ${validaLabelWithDate(insight)}${isFallback ? ", análisis no disponible" : ""}`}
          className={cn(
            "group flex min-w-0 flex-1 items-start gap-3 p-4 text-left transition-colors",
            "hover:bg-light-gray/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary/50",
          )}
        >
          {/* Ícono según tipo — el marcador de fallback (US4) reemplaza a
              Trophy/Medal porque el análisis de esta fila no llegó a generarse. */}
          {isFallback ? (
            <AlertCircle
              size={16}
              className="mt-0.5 shrink-0 text-mid-gray"
              aria-hidden="true"
            />
          ) : (
            <>
              {shape === "season-summary" && (
                <Trophy
                  size={16}
                  className="mt-0.5 shrink-0 text-primary"
                  aria-hidden="true"
                />
              )}
              {shape === "departamental" && (
                <Medal
                  size={16}
                  className="mt-0.5 shrink-0 text-amber-500"
                  aria-hidden="true"
                />
              )}
            </>
          )}

          <div className="flex-1 min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-xs font-medium uppercase tracking-wide text-mid-gray">
                {formatDateTimeCompact(insight.generated_at)}
              </span>
              <Badge variant="secondary">{validaLabelWithDate(insight)}</Badge>
              {!insight.is_active && (
                <Badge variant="outline">Histórico</Badge>
              )}
              {isFallback && (
                <Badge
                  variant="outline"
                  className="gap-1 border-dashed"
                  data-testid={`insight-fallback-badge-${insight.id}`}
                >
                  <AlertCircle size={11} aria-hidden="true" />
                  Análisis no disponible
                </Badge>
              )}
            </div>
            {/* `max-w-[75ch]`: en pantalla ancha el resumen corría el ancho
                completo de la card (~1500px), muy por encima del rango
                legible de 45–75 caracteres por línea. El clamp de 2 líneas
                se mantiene; lo que cambia es cuánto texto entra en cada una. */}
            <p
              className={cn(
                "mt-2 line-clamp-2 max-w-[75ch] text-sm leading-relaxed",
                isFallback ? "italic text-mid-gray" : "text-charcoal",
              )}
            >
              {/* T301 (feature 037): un headline v3 ya viene redactado como
                  preview de una línea — no hace falta el parsing de v2 ni
                  el fallback al markdown crudo. `headline` es opcional
                  (insights v1/v2 no lo traen), así que el resto de la
                  lógica se conserva intacta como fallback. */}
              {insight.headline
                ? insight.headline
                : insight.prompt_version === PROMPT_VERSION_V2
                  ? getV2Preview(insight.summary_text)
                  : insight.summary_text}
            </p>
          </div>
          <ChevronRight
            size={18}
            className="mt-1 shrink-0 text-mid-gray transition-transform group-hover:translate-x-0.5"
            aria-hidden="true"
          />
        </button>

        {/* Regenerar (solo coach) — re-lanza el análisis de esta válida (US6). */}
        {canRegenerate && (
          <div className="flex shrink-0 items-center border-l border-light-gray px-1">
            <button
              type="button"
              onClick={handleRegenerate}
              disabled={regenerate.isPending}
              data-testid={`insight-regenerate-${insight.id}`}
              aria-label={`Regenerar análisis ${validaLabelWithDate(insight)}`}
              className={cn(
                "flex min-h-12 min-w-12 items-center justify-center gap-1.5 rounded-xl px-3 text-xs font-medium",
                "text-primary transition-colors hover:bg-light-gray/50",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50",
                "disabled:cursor-not-allowed disabled:opacity-60",
              )}
            >
              {regenerate.isPending ? (
                <Loader2 size={16} className="animate-spin" aria-hidden="true" />
              ) : (
                <RefreshCw size={16} aria-hidden="true" />
              )}
              <span className="hidden sm:inline">Regenerar</span>
            </button>
          </div>
        )}

        {/* Reintentar (solo coach, solo filas fallback) — US4/T025. El
            análisis anterior falló; este botón vuelve a lanzarlo (misma
            válida, o el resumen de temporada cuando valida_num=0). */}
        {canRetry && (
          <div className="flex shrink-0 items-center border-l border-light-gray px-1">
            <button
              type="button"
              onClick={handleRetry}
              disabled={retryPending}
              data-testid={`insight-retry-${insight.id}`}
              aria-label={`Reintentar análisis ${validaLabelWithDate(insight)}`}
              className={cn(
                "flex min-h-12 min-w-12 items-center justify-center gap-1.5 rounded-xl px-3 text-xs font-medium",
                "text-primary transition-colors hover:bg-light-gray/50",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50",
                "disabled:cursor-not-allowed disabled:opacity-60",
              )}
            >
              {retryPending ? (
                <Loader2 size={16} className="animate-spin" aria-hidden="true" />
              ) : (
                <RefreshCw size={16} aria-hidden="true" />
              )}
              <span className="hidden sm:inline">Reintentar</span>
            </button>
          </div>
        )}
          </div>

          {/* Fallo de la acción de fila, DENTRO de la card: el error pertenece
              a esta fila, no a la lista. El mensaje real del backend manda —
              un 409 de "ya hay un análisis en curso" o de válida ambigua le
              dice al coach qué hacer, mientras que la copy genérica le pedía
              justo lo que no funciona ("Intenta de nuevo"). Misma convención
              que `LaunchAnalysisForm.tsx` y `SeasonSummaryButton.tsx` en este
              mismo tab: `extractErrorDetail(err, <copy de respaldo>)`. */}
          {canRegenerate && regenerate.isError && (
            <div className="px-4 pb-3">
              <RowActionAlert
                testId={`insight-regenerate-error-${insight.id}`}
                message={extractErrorDetail(
                  regenerate.error,
                  REGENERATE_ERROR_FALLBACK,
                )}
              />
            </div>
          )}
          {canRetry && retryFailed && (
            <div className="px-4 pb-3">
              <RowActionAlert
                testId={`insight-retry-error-${insight.id}`}
                message={extractErrorDetail(
                  isSeasonSummaryRow ? seasonRetry.error : regenerate.error,
                  RETRY_ERROR_FALLBACK,
                )}
              />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Detail drawer — Sheet (mobile) o Dialog (desktop)
// ---------------------------------------------------------------------------

interface InsightDetailDrawerProps {
  athleteId: number;
  insightId: number | null;
  onClose: () => void;
  useDialog: boolean;
  mode: "coach" | "parent";
}

function InsightDetailDrawer({
  athleteId,
  insightId,
  onClose,
  useDialog,
  mode,
}: InsightDetailDrawerProps) {
  const isOpen = insightId !== null;
  const detailQuery = useAthleteInsightDetail(athleteId, insightId);

  const handleOpenChange = (open: boolean) => {
    if (!open) onClose();
  };

  const body = (() => {
    if (detailQuery.isLoading) {
      return (
        <div
          role="status"
          aria-busy="true"
          aria-label="Cargando detalle del análisis"
          className="space-y-3"
        >
          <Skeleton className="h-8 w-1/2" />
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-5/6" />
          <Skeleton className="h-4 w-2/3" />
          <Skeleton className="h-32 w-full" />
        </div>
      );
    }
    if (detailQuery.isError || !detailQuery.data) {
      const coldStart = isColdStartError(detailQuery.error);
      return (
        <ErrorState
          message={
            coldStart ? undefined : "No pudimos cargar el detalle del análisis."
          }
          onRetry={() => void detailQuery.refetch()}
          isColdStart={coldStart}
        />
      );
    }
    const insight = detailQuery.data;
    const isV2 = insight.prompt_version === PROMPT_VERSION_V2;
    const sections = isV2 ? parseV2Sections(insight.summary_text) : null;
    const progression = extractProgressionAssessment(insight);
    const isFallback = insight.is_fallback === true;

    return (
      <div className="space-y-4">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="secondary">{validaLabelWithDate(insight)}</Badge>
          {mode === "coach" && (
            <>
              <Badge variant={confidenceVariant(insight.confidence)}>
                {confidenceLabel(insight.confidence)}
              </Badge>
              <Badge variant="outline">v{insight.prompt_version}</Badge>
            </>
          )}
          {progression !== null && (
            <ProgressionBadge assessment={progression} />
          )}
          {isFallback && (
            <Badge variant="outline" className="gap-1 border-dashed">
              <AlertCircle size={11} aria-hidden="true" />
              Análisis no disponible
            </Badge>
          )}
        </div>

        {insight.is_first_in_season === true && <InsightN1Banner mode={mode} />}

        {isFallback ? (
          <div
            role="status"
            data-testid="insight-fallback-notice"
            className="rounded-xl border border-dashed border-mid-gray/60 bg-light-gray/20 p-4 text-sm text-charcoal"
          >
            <p className="flex items-center gap-2 font-medium">
              <AlertCircle
                size={14}
                className="shrink-0 text-mid-gray"
                aria-hidden="true"
              />
              Análisis no disponible
            </p>
            <p className="mt-1 text-xs text-mid-gray">
              {mode === "coach"
                ? 'No fue posible generar este análisis. Puedes revisar los datos oficiales en la sección de Resultados, o cerrar esta ventana y usar "Reintentar" en el histórico para volver a intentarlo.'
                : "No fue posible generar este análisis en este momento. Puedes revisar los datos oficiales en la sección de Resultados; tu entrenador podrá volver a intentarlo."}
            </p>
          </div>
        ) : insight.structured ? (
          <InsightV3Card
            structured={insight.structured}
            mode={mode}
            footer={
              mode === "coach" ? (
                <CoachAnswerForm
                  athleteId={athleteId}
                  insightId={insight.id}
                  initialAnswer={insight.coach_answer_text}
                  initialRating={insight.coach_rating}
                />
              ) : undefined
            }
          />
        ) : isV2 && sections ? (
          <InsightV2Sections sections={sections} mode={mode} />
        ) : (
          <MarkdownReportViewer markdown={insight.summary_text} />
        )}

        {insight.recommendations.length > 0 && (
          <section
            aria-label="Recomendaciones"
            className="rounded-xl bg-white p-4 ring-1 ring-light-gray space-y-2"
          >
            <h3
              className="font-display text-sm text-charcoal"
            >
              Recomendaciones
            </h3>
            <ul className="space-y-2 text-sm text-charcoal">
              {insight.recommendations.map((rec, idx) => {
                const text =
                  typeof rec === "object" && rec !== null && "text" in rec
                    ? String((rec as { text: unknown }).text ?? "")
                    : JSON.stringify(rec);
                return (
                  <li key={idx} className="rounded-lg bg-light-gray/30 px-3 py-2">
                    {text}
                  </li>
                );
              })}
            </ul>
          </section>
        )}

        {insight.supersedes.length > 0 && (
          <SupersedesSection chain={insight.supersedes} />
        )}
      </div>
    );
  })();

  if (useDialog) {
    return (
      <Dialog open={isOpen} onOpenChange={handleOpenChange}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>Detalle del análisis</DialogTitle>
            <DialogDescription>
              Informe generado y aprobado por el entrenador.
            </DialogDescription>
          </DialogHeader>
          <DialogBody className="max-h-[70vh] overflow-y-auto">{body}</DialogBody>
        </DialogContent>
      </Dialog>
    );
  }
  return (
    <Sheet open={isOpen} onOpenChange={handleOpenChange}>
      <SheetContent side="right" className="sm:max-w-lg w-full">
        <SheetHeader>
          <SheetTitle>Detalle del análisis</SheetTitle>
          <SheetDescription>
            Informe generado y aprobado por el entrenador.
          </SheetDescription>
        </SheetHeader>
        <SheetBody>{body}</SheetBody>
      </SheetContent>
    </Sheet>
  );
}

// ---------------------------------------------------------------------------
// Secciones v2
// ---------------------------------------------------------------------------

const SECTION_LABELS: Record<
  keyof InsightParsedSections,
  { coach: string; parent: string }
> = {
  what_happened: { coach: "Qué pasó", parent: "Qué pasó" },
  journey_so_far: { coach: "Recorrido hasta aquí", parent: "Recorrido" },
  looking_ahead: { coach: "Hacia dónde va", parent: "Hacia dónde va" },
  season_summary: { coach: "Resumen de temporada", parent: "Resumen temporada" },
  season_context: { coach: "Contexto de temporada", parent: "Contexto de temporada" },
};

const SECTION_ORDER: Array<keyof InsightParsedSections> = [
  "what_happened",
  "journey_so_far",
  "looking_ahead",
  "season_summary",
  "season_context",
];

interface InsightV2SectionsProps {
  sections: InsightParsedSections;
  mode: "coach" | "parent";
}

function InsightV2Sections({ sections, mode }: InsightV2SectionsProps) {
  const visibleSections = SECTION_ORDER.filter((key) => !!sections[key]);

  if (visibleSections.length === 0) {
    return (
      <p className="text-sm text-mid-gray">
        No se encontraron secciones en este análisis.
      </p>
    );
  }

  return (
    <div className="space-y-2" data-testid="insight-v2-sections">
      {visibleSections.map((key, index) => {
        const label =
          mode === "parent"
            ? SECTION_LABELS[key].parent
            : SECTION_LABELS[key].coach;
        const content = sections[key] ?? "";
        const isOpen = index === 0;
        return (
          <details
            key={key}
            open={isOpen}
            className="rounded-xl bg-white ring-1 ring-light-gray"
            data-testid={`insight-v2-section-${key}`}
          >
            <summary
              className={cn(
                "font-display flex cursor-pointer items-center gap-2 px-4 py-3 text-sm font-medium text-charcoal",
                "hover:bg-light-gray/30 rounded-xl transition-colors select-none",
              )}
            >
              {label}
            </summary>
            <div className="px-4 pb-4 pt-1">
              <p className="text-sm leading-relaxed text-charcoal whitespace-pre-wrap">
                {content}
              </p>
            </div>
          </details>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Versiones anteriores
// ---------------------------------------------------------------------------

function SupersedesSection({ chain }: { chain: InsightLink[] }) {
  return (
    <details
      className="rounded-xl bg-white p-4 ring-1 ring-light-gray"
      data-testid="insight-supersedes"
    >
      <summary className="flex cursor-pointer items-center gap-2 text-sm font-medium text-charcoal">
        <History size={14} aria-hidden="true" />
        Versiones anteriores ({chain.length})
      </summary>
      <ul className="mt-3 space-y-1.5 text-xs text-mid-gray">
        {chain.map((link) => (
          <li
            key={link.id}
            className="flex items-center justify-between gap-2 rounded-md bg-light-gray/30 px-2.5 py-1.5"
          >
            <span>{formatDateTimeCompact(link.generated_at)}</span>
            <span className="font-mono">#{link.id}</span>
            {link.coach_approved ? (
              <Badge variant="success">Aprobado</Badge>
            ) : (
              <Badge variant="outline">Borrador</Badge>
            )}
          </li>
        ))}
      </ul>
    </details>
  );
}
