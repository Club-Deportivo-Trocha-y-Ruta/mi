/**
 * ComparatorPanel v2 — comparador progreso A → B del análisis IA por atleta.
 *
 * Caso de uso MVP:
 *   Coach: "¿Mi atleta mejoró o empeoró entre la Válida X y la Válida Y de
 *   esta temporada?". Solo coach (vista «Comparar» de «Carreras», feature
 *   045): la familia nunca llega a este panel.
 *
 * Feature 045 (T039) — las cifras salen del MOTOR ÚNICO del servidor: los
 * puntos de `GET .../race-analysis/history` (`useAthleteRaceHistory`), por
 * `event_id`. El panel ya no lee el `metrics_snapshot` del insight ni
 * recalcula percentiles en el cliente (`lib/raceMetrics.ts`, retirado): solo
 * calcula el delta entre los dos puntos.
 *
 * Layout (consenso UX + head-coach):
 *   ┌─ Header (título + select Temporada) ────────────────────────┐
 *   │ Selector ANTES   [swap ⇄]   Selector DESPUÉS               │
 *   │ Banner Circa-PHV (si record antropométrico reciente)        │
 *   │ Tabla unificada: Métrica | Antes | Después | Cambio        │
 *   │ Resumen "Mejoró N de M métricas — Confianza X"              │
 *   │ CTA "Ver análisis IA completo →"                            │
 *   └──────────────────────────────────────────────────────────────┘
 *
 * Privacidad:
 *   - Nunca expone nombres de rivales.
 *   - Las brechas vs. podio son de coach; este panel no se monta para la
 *     familia (el backend tampoco les envía esas claves).
 *
 * Principio coach: la brecha vs. la mediana es la lectura principal; la
 * brecha vs. podio se ofrece como contexto — "edad biológica > cronológica"
 * (el P1 puede ser Post-PHV mientras el atleta es Pre-PHV).
 *
 * Hotfix multicopa (2026-09-16, `plans/multicopa-identidad-valida.md`):
 * antes, las opciones A/B eran una lista fija "Válida I..VII + CD"
 * (`VALIDA_OPTIONS`, retirada) deduplicada por `valida_num` contra un
 * calendario Copa Valle hardcodeado (`lib/raceCalendar.ts`, retirado) — dos
 * copas con la misma Válida IV colapsaban en una sola opción y el badge de
 * "tipo de carrera" (A/B/C) mezclaba temporadas de copas distintas. Ahora
 * las opciones salen de las carreras REALES del atleta
 * (`useAthleteRaces`/`RaceParticipationOption`, por `event_id`) cruzadas
 * con sus insights aprobados, y A/B quedan acotados a la MISMA copa
 * (`series_id`) — comparar entre copas distintas ya no es posible desde
 * este panel.
 *
 * Wave 3: el banner de "tipos de carrera distintos" vuelve, ahora sobre
 * `race_events.priority` real por evento (`RaceParticipationOption`) en vez
 * del antiguo `getRaceMeta().type` Copa-Valle-only — solo se muestra cuando
 * AMBOS lados tienen `priority` no nulo y difieren, copy genérico sin
 * nombrar ninguna copa.
 */
import { useEffect, useMemo, useState } from "react";
import {
  ArrowDown,
  ArrowLeftRight,
  ArrowUp,
  Equal,
  Scale,
  Sparkles,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorState, isColdStartError } from "@/components/shared/ErrorState";
import { useAnthropometry } from "@/hooks/athletes/useAnthropometry";
import { useAthleteInsights } from "@/hooks/athletes/useAthleteInsights";
import { useAthleteRaces } from "@/hooks/athletes/useAthleteRaces";
import { useAthleteRaceHistory } from "@/hooks/race/useAthleteRaceHistory";
import { raceLabelForInsight } from "@/lib/insights";
import { formatGapPct } from "@/lib/raceHistoryFormat";
import { formatDayMonthShort } from "@/lib/datetime";
import { cn } from "@/lib/utils";
import type { AthleteInsightOut } from "@/types/athleteRaceAnalysis.types";
import type { RaceHistoryPoint } from "@/types/raceHistory.types";
import { MaturationStatus } from "@/types/enums";
import type { RaceEventPriority } from "@/types/raceEvents.types";

// ---------------------------------------------------------------------------
// Constantes
// ---------------------------------------------------------------------------

/** Tap target mínimo WCAG (44×44 px). */
// Wave 5 (feature 036, target-size sweep): era `min-h-[44px]` — el floor de
// iOS HIG, no el de este proyecto (48px, `MIN_TARGET_SIZE` en
// `e2e/target-size.spec.ts`). Un solo punto de verdad para las 4 controles
// de este archivo (season select, swap, ambos selects de válida, CTA final)
// — subir este valor los corrige a todos a la vez.
const TAP_TARGET_CLASSES = "min-h-[48px]";

/** Ventana de "reciente" para considerar el record antropométrico vigente. */
const PHV_FRESHNESS_DAYS = 90;

function getDefaultSeason(): number {
  return new Date().getFullYear();
}

// ---------------------------------------------------------------------------
// Opciones A/B — carreras reales del atleta con insight aprobado (hotfix
// multicopa). Reemplaza al antiguo `VALIDA_OPTIONS` fijo.
// ---------------------------------------------------------------------------

interface RaceOption {
  eventId: number;
  insight: AthleteInsightOut;
  /** `null` cuando la carrera todavía no trae identidad de copa (legacy). */
  seriesId: number | null;
  eventDate: string;
  location: string | null;
  /**
   * Wave 3 (hotfix multicopa) — `race_events.priority` real del evento.
   * `null` = UNKNOWN. Única fuente del banner de tapering-mismatch (ver
   * `TaperingBanner`) — reemplaza al antiguo `getRaceMeta().type`
   * (`lib/raceCalendar.ts`, retirado, Copa Valle only).
   */
  priority: RaceEventPriority | null;
}

/**
 * Cruza el listado de insights aprobados/activos de la temporada con las
 * carreras reales del atleta (`useAthleteRaces`) y devuelve las opciones
 * elegibles para el comparador, ordenadas cronológicamente por
 * `event_date`.
 *
 * Reglas:
 *   - Solo insights `coach_approved && is_active`, con `valida_num` de
 *     válida concreta (excluye 0 = resumen de temporada) y `event_id` no
 *     nulo.
 *   - El `event_id` debe existir en las carreras reales del atleta — un
 *     insight cuyo evento no aparece ahí (carrera borrada, o la lista de
 *     carreras todavía no cargó) se excluye en vez de adivinar su fecha o
 *     su copa.
 *   - Dedup por `event_id` (no por `valida_num`, que colisiona entre
 *     copas): conserva el insight más reciente por carrera.
 */
function buildEligibleOptions(
  insights: AthleteInsightOut[],
  races: Array<{
    event_id: number;
    event_date: string;
    location: string | null;
    series_id?: number;
    priority?: RaceEventPriority | null;
  }>,
): RaceOption[] {
  const raceByEventId = new Map(races.map((r) => [r.event_id, r]));
  const approved = insights.filter(
    (i) =>
      i.coach_approved &&
      i.is_active &&
      i.valida_num !== null &&
      i.valida_num !== undefined &&
      i.valida_num !== 0 &&
      i.event_id !== null &&
      i.event_id !== undefined &&
      raceByEventId.has(i.event_id),
  );
  const byEvent = new Map<number, AthleteInsightOut>();
  for (const i of approved) {
    const eventId = i.event_id as number;
    const prev = byEvent.get(eventId);
    if (
      !prev ||
      new Date(i.generated_at).getTime() > new Date(prev.generated_at).getTime()
    ) {
      byEvent.set(eventId, i);
    }
  }
  const options: RaceOption[] = Array.from(byEvent.entries()).map(
    ([eventId, insight]) => {
      const race = raceByEventId.get(eventId)!;
      return {
        eventId,
        insight,
        seriesId: race.series_id ?? null,
        eventDate: race.event_date,
        location: race.location,
        priority: race.priority ?? null,
      };
    },
  );
  return options.sort((a, b) => a.eventDate.localeCompare(b.eventDate));
}

/**
 * Elige el par por defecto A/B: el grupo de MISMA copa (`series_id`) con
 * más carreras elegibles (empate → el primero encontrado), tomando la
 * primera y la última cronológicamente dentro de ese grupo. `null` cuando
 * ninguna copa tiene al menos 2 carreras elegibles — el panel no puede
 * armar un par válido (mismo criterio que bloquea la selección manual
 * cross-copa, ver `SideSelector`).
 */
function pickDefaultPair(
  options: RaceOption[],
): { a: number; b: number } | null {
  const bySeries = new Map<number | null, RaceOption[]>();
  for (const o of options) {
    const arr = bySeries.get(o.seriesId) ?? [];
    arr.push(o);
    bySeries.set(o.seriesId, arr);
  }
  let best: RaceOption[] | null = null;
  for (const group of bySeries.values()) {
    if (group.length < 2) continue;
    if (!best || group.length > best.length) best = group;
  }
  if (!best) return null;
  return { a: best[0].eventId, b: best[best.length - 1].eventId };
}

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface ComparatorPanelProps {
  athleteId: number;
}

// ---------------------------------------------------------------------------
// Componente principal
// ---------------------------------------------------------------------------

export function ComparatorPanel({ athleteId }: ComparatorPanelProps) {
  const [season, setSeason] = useState<number>(getDefaultSeason());

  // Lista global de insights aprobados/activos de la temporada + carreras
  // reales del atleta — el cruce de ambas produce las opciones elegibles
  // (ver `buildEligibleOptions`).
  const seasonListQuery = useAthleteInsights(athleteId, {
    season,
    limit: 50,
  });
  const racesQuery = useAthleteRaces(athleteId, season);

  const eligibleOptions = useMemo(
    () =>
      buildEligibleOptions(
        seasonListQuery.data?.items ?? [],
        racesQuery.data?.items ?? [],
      ),
    [seasonListQuery.data, racesQuery.data],
  );

  const defaultPair = useMemo(
    () => pickDefaultPair(eligibleOptions),
    [eligibleOptions],
  );

  // Defaults: primera y última carrera elegible de la copa con más
  // carreras en la temporada.
  const [eventA, setEventA] = useState<number | null>(null);
  const [eventB, setEventB] = useState<number | null>(null);

  useEffect(() => {
    if (!defaultPair) {
      setEventA(null);
      setEventB(null);
      return;
    }
    setEventA((current) => {
      if (current === null) return defaultPair.a;
      const stillExists = eligibleOptions.some((o) => o.eventId === current);
      return stillExists ? current : defaultPair.a;
    });
    setEventB((current) => {
      if (current === null) return defaultPair.b;
      const stillExists = eligibleOptions.some((o) => o.eventId === current);
      return stillExists ? current : defaultPair.b;
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [defaultPair, season]);

  const handleSwap = () => {
    setEventA(eventB);
    setEventB(eventA);
  };

  const optionA = eligibleOptions.find((o) => o.eventId === eventA);
  const optionB = eligibleOptions.find((o) => o.eventId === eventB);

  // Estados derivados
  const hasEnoughValidas = defaultPair !== null;
  const sameEvent = eventA !== null && eventA === eventB;
  const isLoading = seasonListQuery.isLoading || racesQuery.isLoading;
  const isError = seasonListQuery.isError || racesQuery.isError;
  const coldStart = isColdStartError(seasonListQuery.error ?? racesQuery.error);

  return (
    <section
      className={cn("rounded-card bg-surface-raised p-5 space-y-4", "shadow-card ring-1 ring-hairline")}
      aria-label="Comparador progreso entre válidas"
      data-testid="comparator-panel"
    >
      <Header season={season} onSeasonChange={setSeason} />

      {isLoading ? (
        <Skeleton className="h-40 w-full rounded-lg" />
      ) : isError ? (
        <ErrorState
          message={
            coldStart
              ? undefined
              : "No se pudieron cargar los análisis de la temporada."
          }
          onRetry={() => {
            void seasonListQuery.refetch();
            void racesQuery.refetch();
          }}
          isColdStart={coldStart}
        />
      ) : !hasEnoughValidas ? (
        <EmptyPair count={eligibleOptions.length} />
      ) : (
        <>
          <SelectorsRow
            options={eligibleOptions}
            eventA={eventA}
            eventB={eventB}
            onEventAChange={setEventA}
            onEventBChange={setEventB}
            onSwap={handleSwap}
          />

          {sameEvent ? (
            <p
              role="status"
              className="rounded-xl bg-amber-50 px-4 py-3 text-sm text-amber-900"
            >
              Selecciona dos válidas distintas para comparar.
            </p>
          ) : optionA && optionB ? (
            <ComparisonBody
              athleteId={athleteId}
              optionA={optionA}
              optionB={optionB}
            />
          ) : null}
        </>
      )}
    </section>
  );
}

// ---------------------------------------------------------------------------
// Header — título + selector de temporada
// ---------------------------------------------------------------------------

function Header({
  season,
  onSeasonChange,
}: {
  season: number;
  onSeasonChange: (s: number) => void;
}) {
  return (
    <header className="flex flex-wrap items-center justify-between gap-3">
      <div>
        <h3
          className="font-display flex items-center gap-2 text-sm text-charcoal"
          style={{ letterSpacing: "0.2px" }}
        >
          <Scale size={16} aria-hidden="true" />
          Comparador progreso
        </h3>
        <p className="mt-0.5 text-xs text-mid-gray">
          Mide al atleta contra sí mismo entre dos válidas de la misma copa.
        </p>
      </div>
      <label className="sr-only" htmlFor="cmp-season">
        Temporada
      </label>
      <select
        id="cmp-season"
        value={season}
        onChange={(e) => onSeasonChange(Number(e.target.value))}
        className={cn(
          "rounded-lg bg-surface-raised px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary/40",
          TAP_TARGET_CLASSES,
          "shadow-ring",
        )}
        data-testid="comparator-season-select"
      >
        {Array.from(
          { length: getDefaultSeason() - 2023 },
          (_, i) => getDefaultSeason() - i,
        ).map((y) => (
          <option key={y} value={y}>
            {y}
          </option>
        ))}
      </select>
    </header>
  );
}

// ---------------------------------------------------------------------------
// Selectores A / swap / B + bloqueo cross-copa
// ---------------------------------------------------------------------------

function SelectorsRow({
  options,
  eventA,
  eventB,
  onEventAChange,
  onEventBChange,
  onSwap,
}: {
  options: RaceOption[];
  eventA: number | null;
  eventB: number | null;
  onEventAChange: (v: number) => void;
  onEventBChange: (v: number) => void;
  onSwap: () => void;
}) {
  const seriesIdOfA = options.find((o) => o.eventId === eventA)?.seriesId ?? null;
  const seriesIdOfB = options.find((o) => o.eventId === eventB)?.seriesId ?? null;
  // Más de una copa entre las opciones elegibles → el bloqueo cross-copa
  // aplica y vale la pena mostrar la explicación accesible.
  const hasMultipleCups =
    new Set(options.map((o) => o.seriesId)).size > 1;

  return (
    <div className="grid grid-cols-1 items-start gap-3 md:grid-cols-[1fr_auto_1fr]">
      <SideSelector
        side="A"
        label="ANTES"
        selectedEventId={eventA}
        onChange={onEventAChange}
        options={options}
        constrainToSeriesId={seriesIdOfB}
        showCupHint={hasMultipleCups}
      />
      <button
        type="button"
        onClick={onSwap}
        aria-label="Intercambiar antes y después"
        data-testid="comparator-swap"
        className={cn(
          "mx-auto inline-flex items-center justify-center self-center rounded-full bg-light-gray text-charcoal",
          TAP_TARGET_CLASSES,
          "min-w-[48px] transition motion-reduce:transition-none hover:bg-light-gray/70 focus:outline-none focus:ring-2 focus:ring-primary/40",
        )}
      >
        <ArrowLeftRight size={18} aria-hidden="true" />
      </button>
      <SideSelector
        side="B"
        label="DESPUÉS"
        selectedEventId={eventB}
        onChange={onEventBChange}
        options={options}
        constrainToSeriesId={seriesIdOfA}
        showCupHint={hasMultipleCups}
      />
    </div>
  );
}

function SideSelector({
  side,
  label,
  selectedEventId,
  onChange,
  options,
  constrainToSeriesId,
  showCupHint,
}: {
  side: "A" | "B";
  label: string;
  selectedEventId: number | null;
  onChange: (v: number) => void;
  options: RaceOption[];
  /** `series_id` del OTRO lado ya seleccionado — las opciones de una copa
   * distinta quedan deshabilitadas. `null` = sin restricción todavía. */
  constrainToSeriesId: number | null;
  showCupHint: boolean;
}) {
  const selected = options.find((o) => o.eventId === selectedEventId);
  const testId = side === "A" ? "comparator-col-a" : "comparator-col-b";
  const hintId = `cmp-cup-hint-${side.toLowerCase()}`;
  return (
    <div className="rounded-xl bg-light-gray/30 p-3" data-testid={testId}>
      <div className="text-[10px] font-semibold uppercase tracking-wider text-mid-gray">
        {label}
      </div>
      <select
        value={selectedEventId ?? ""}
        onChange={(e) => onChange(Number(e.target.value))}
        aria-label={`${side === "A" ? "Válida A" : "Válida B"} — seleccionar válida`}
        aria-describedby={showCupHint ? hintId : undefined}
        className={cn(
          "mt-1 w-full rounded-lg bg-surface-raised px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary/40",
          TAP_TARGET_CLASSES,
          "shadow-ring",
        )}
      >
        {options.map((o) => {
          // Nunca deshabilitamos la opción ya seleccionada — solo bloquea
          // ELEGIR una carrera de otra copa hacia adelante.
          const isCurrentlySelected = o.eventId === selectedEventId;
          const isOtherCup =
            constrainToSeriesId !== null &&
            o.seriesId !== null &&
            o.seriesId !== constrainToSeriesId;
          const disabled = !isCurrentlySelected && isOtherCup;
          return (
            <option key={o.eventId} value={o.eventId} disabled={disabled}>
              {raceLabelForInsight(o.insight, "chip")} —{" "}
              {formatDayMonthShort(`${o.eventDate}T12:00:00Z`)}
              {disabled ? " (otra copa)" : ""}
            </option>
          );
        })}
      </select>
      {showCupHint && (
        <p id={hintId} className="mt-1 text-[11px] text-mid-gray">
          Solo se pueden comparar válidas de la misma copa.
        </p>
      )}
      <div className="mt-2 flex items-center gap-2 text-xs">
        {selected ? (
          <>
            <Badge aria-label={`Copa: ${raceLabelForInsight(selected.insight, "chip")}`}>
              {raceLabelForInsight(selected.insight, "chip")}
            </Badge>
            <span className="text-mid-gray">
              {selected.location ?? "—"} ·{" "}
              {formatDayMonthShort(`${selected.eventDate}T12:00:00Z`)}
            </span>
          </>
        ) : (
          <span className="text-mid-gray">Sin selección</span>
        )}
      </div>
    </div>
  );
}


// ---------------------------------------------------------------------------
// Empty state global
// ---------------------------------------------------------------------------

function EmptyPair({ count }: { count: number }) {
  return (
    <div
      role="status"
      data-testid="comparator-empty-pair"
      className="rounded-xl bg-light-gray/40 px-4 py-6 text-center text-sm text-mid-gray"
    >
      {count === 0
        ? "Aún no hay análisis aprobados en esta temporada."
        : "Necesitas al menos 2 válidas de la misma copa con análisis aprobado para comparar."}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Cuerpo de la comparación — banners + tabla + resumen + CTA
// ---------------------------------------------------------------------------

/** Punto del historial (motor único del servidor) de un evento. */
function findHistoryPoint(
  points: RaceHistoryPoint[] | undefined,
  eventId: number,
): RaceHistoryPoint | null {
  return points?.find((p) => p.event_id === eventId) ?? null;
}

function ComparisonBody({
  athleteId,
  optionA,
  optionB,
}: {
  athleteId: number;
  optionA: RaceOption;
  optionB: RaceOption;
}) {
  // Feature 045 (T039): una sola consulta al motor del servidor — el panel
  // ya no pide el detalle de cada insight para leer su snapshot.
  const historyQuery = useAthleteRaceHistory(athleteId, "all");
  const pointA = findHistoryPoint(historyQuery.data?.points, optionA.eventId);
  const pointB = findHistoryPoint(historyQuery.data?.points, optionB.eventId);

  // Banner tapering-mismatch (Wave 3, hotfix multicopa): solo cuando AMBOS
  // lados tienen `priority` real (no `null`/UNKNOWN) y difieren — nunca se
  // adivina a partir de uno solo o de un calendario. Copy genérico (A/B/C),
  // sin nombrar ninguna copa — la comparación ya está acotada a la misma
  // copa (`series_id`), esto solo avisa que el TIPO de carrera cambió.
  const taperingMismatch =
    optionA.priority !== null &&
    optionB.priority !== null &&
    optionA.priority !== optionB.priority
      ? { a: optionA.priority, b: optionB.priority }
      : null;

  // Anthropometry para el banner Circa-PHV (solo si hay record reciente).
  const anthropometryQuery = useAnthropometry(athleteId);
  const phvBannerVisible = useMemo(() => {
    const records = anthropometryQuery.data ?? [];
    const today = new Date();
    return records.some((r) => {
      if (r.maturation_status !== MaturationStatus.CircaPHV) return false;
      const d = new Date(`${r.evaluation_date}T12:00:00Z`);
      const ageDays = (today.getTime() - d.getTime()) / 86_400_000;
      return ageDays >= 0 && ageDays <= PHV_FRESHNESS_DAYS;
    });
  }, [anthropometryQuery.data]);

  const rows = useMemo(() => buildRows(pointA, pointB), [pointA, pointB]);

  if (historyQuery.isLoading) {
    return <Skeleton className="h-64 w-full rounded-lg" />;
  }

  if (historyQuery.isError) {
    const historyColdStart = isColdStartError(historyQuery.error);
    return (
      <ErrorState
        message={
          historyColdStart
            ? undefined
            : "No se pudieron cargar las métricas de las carreras."
        }
        onRetry={() => {
          void historyQuery.refetch();
        }}
        isColdStart={historyColdStart}
      />
    );
  }

  return (
    <div className="space-y-3">
      {taperingMismatch ? (
        <TaperingBanner priorityA={taperingMismatch.a} priorityB={taperingMismatch.b} />
      ) : null}
      {phvBannerVisible ? <PHVBanner /> : null}

      <DiffTable
        labelA={raceLabelForInsight(optionA.insight, "chip")}
        labelB={raceLabelForInsight(optionB.insight, "chip")}
        rows={rows}
        missingData={pointA === null || pointB === null}
      />

      <ImprovementSummary
        rows={rows}
        confidence={optionB.insight.confidence}
        labelB={raceLabelForInsight(optionB.insight, "chip")}
      />

      <button
        type="button"
        onClick={() => {
          /* Placeholder: navegación al análisis completo se enlaza en futura iteración. */
        }}
        aria-label="Ver análisis IA completo"
        className={cn(
          "inline-flex items-center gap-2 rounded-lg bg-primary/10 px-4 py-2 text-sm font-medium text-primary transition hover:bg-primary/15 focus:outline-none focus:ring-2 focus:ring-primary/40",
          TAP_TARGET_CLASSES,
        )}
      >
        <Sparkles size={14} aria-hidden="true" />
        Ver análisis IA completo →
      </button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Banner: tipos de carrera distintos (aviso de tapering)
// ---------------------------------------------------------------------------

function TaperingBanner({
  priorityA,
  priorityB,
}: {
  priorityA: RaceEventPriority;
  priorityB: RaceEventPriority;
}) {
  return (
    <p
      role="note"
      data-testid="comparator-tapering-banner"
      className="rounded-xl bg-amber-50 px-4 py-3 text-xs text-amber-900"
    >
      <strong>Carreras de distinto tipo</strong> ({priorityA} vs {priorityB}
      ). Parte de la mejora puede deberse al tapering. Interpreta con cautela.
    </p>
  );
}

// ---------------------------------------------------------------------------
// Banner: atleta en Circa-PHV (estirón) reciente
// ---------------------------------------------------------------------------

function PHVBanner() {
  return (
    <p
      role="note"
      data-testid="comparator-phv-banner"
      className="rounded-xl bg-blue-50 px-4 py-3 text-xs text-blue-900"
    >
      <strong>Atleta en estirón (Circa-PHV).</strong> Variaciones normales:
      prioriza progreso técnico sobre cifras absolutas.
    </p>
  );
}

// ---------------------------------------------------------------------------
// Tabla de diferencias
// ---------------------------------------------------------------------------

interface RowSpec {
  metric: string;
  beforeText: string;
  afterText: string;
  delta: number | null;
  /** ``true`` ⇒ valor menor es mejor (posición, brechas). */
  lowerIsBetter: boolean;
  /** Override para el formateo del delta visible. */
  deltaText: string;
  /** ``true`` si la fila no tiene datos para alguno de los lados. */
  unavailable?: boolean;
}

function DiffTable({
  labelA,
  labelB,
  rows,
  missingData,
}: {
  labelA: string;
  labelB: string;
  rows: RowSpec[];
  /** ``true`` si alguna de las dos carreras no aparece en el historial. */
  missingData: boolean;
}) {
  return (
    <div className="overflow-x-auto rounded-xl bg-light-gray/30 p-2">
      <table
        className="min-w-full table-auto text-left text-sm"
        data-testid="comparator-diff-table"
      >
        <caption className="sr-only">
          Comparación entre {labelA} y {labelB}
        </caption>
        <thead>
          <tr className="text-[10px] font-semibold uppercase tracking-wider text-mid-gray">
            <th scope="col" className="px-3 py-2">
              Métrica
            </th>
            <th scope="col" className="px-3 py-2">
              {labelA}
            </th>
            <th scope="col" className="px-3 py-2">
              {labelB}
            </th>
            <th scope="col" className="px-3 py-2">
              Cambio
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.metric} className="border-t border-light-gray/60">
              <th
                scope="row"
                className="px-3 py-2 text-xs font-medium text-charcoal"
              >
                {row.metric}
              </th>
              <td className="px-3 py-2 text-sm text-charcoal">
                {row.beforeText}
              </td>
              <td className="px-3 py-2 text-sm text-charcoal">
                {row.afterText}
              </td>
              <td className="px-3 py-2">
                {row.unavailable ? (
                  <span
                    className="text-xs text-mid-gray"
                    aria-label="sin datos para comparar"
                  >
                    —
                  </span>
                ) : (
                  <DeltaCell row={row} />
                )}
              </td>
            </tr>
          ))}
          {missingData ? (
            <tr className="border-t border-light-gray/60">
              <td
                colSpan={4}
                className="px-3 py-2 text-xs italic text-mid-gray"
              >
                Alguna de las dos carreras aún no tiene resultados en el historial.
              </td>
            </tr>
          ) : null}
        </tbody>
      </table>
    </div>
  );
}

/** Δ de posición (B − A): menor es mejor — «−3 puestos» = subió 3. */
function formatDeltaRank(deltaRank: number | null): string {
  if (deltaRank === null) return "—";
  if (deltaRank === 0) return "Mantuvo";
  const abs = Math.abs(deltaRank);
  const noun = abs === 1 ? "puesto" : "puestos";
  return `${deltaRank > 0 ? "+" : "−"}${abs} ${noun}`;
}

/** Δ en puntos porcentuales (B − A), con signo explícito y 1 decimal. */
function formatDeltaPp(delta: number | null): string {
  if (delta === null) return "—";
  const rounded = Math.round(delta * 10) / 10;
  if (rounded === 0) return "0.0 pp";
  return `${rounded > 0 ? "+" : "−"}${Math.abs(rounded).toFixed(1)} pp`;
}

/** Valor de una métrica del motor en un punto (`null` = sin dato). */
function metricOf(
  point: RaceHistoryPoint | null,
  key: "position" | "percentile" | "gap_to_median_pct" | "gap_to_podium_pct",
): number | null {
  if (point === null || !(key in point)) return null;
  return (point as Record<typeof key, number | null>)[key] ?? null;
}

function delta(a: number | null, b: number | null): number | null {
  return a !== null && b !== null ? b - a : null;
}

/**
 * Filas de la tabla A → B. Todas las cifras vienen del motor del servidor
 * (`RaceHistoryPoint`); aquí solo se restan. «Percentil» y las brechas son
 * `null` con menos de 5 cronometrados (regla del motor) → fila «sin datos».
 * «Brecha vs. podio» es de coach — este panel solo se monta para coach.
 */
function buildRows(
  pointA: RaceHistoryPoint | null,
  pointB: RaceHistoryPoint | null,
): RowSpec[] {
  const rankA = metricOf(pointA, "position");
  const rankB = metricOf(pointB, "position");
  const pctA = metricOf(pointA, "percentile");
  const pctB = metricOf(pointB, "percentile");
  const medA = metricOf(pointA, "gap_to_median_pct");
  const medB = metricOf(pointB, "gap_to_median_pct");
  const podA = metricOf(pointA, "gap_to_podium_pct");
  const podB = metricOf(pointB, "gap_to_podium_pct");

  const deltaRank = delta(rankA, rankB);
  const deltaPct = delta(pctA, pctB);
  const deltaMed = delta(medA, medB);
  const deltaPod = delta(podA, podB);

  return [
    {
      metric: "Posición",
      beforeText: formatPosition(rankA, pointA?.field_size),
      afterText: formatPosition(rankB, pointB?.field_size),
      delta: deltaRank,
      lowerIsBetter: true,
      deltaText: formatDeltaRank(deltaRank),
      unavailable: deltaRank === null,
    },
    {
      metric: "Brecha vs. mediana",
      beforeText: formatGapPct(medA),
      afterText: formatGapPct(medB),
      delta: deltaMed,
      lowerIsBetter: true,
      deltaText: formatDeltaPp(deltaMed),
      unavailable: deltaMed === null,
    },
    {
      metric: "Brecha vs. podio",
      beforeText: formatGapPct(podA),
      afterText: formatGapPct(podB),
      delta: deltaPod,
      lowerIsBetter: true,
      deltaText: formatDeltaPp(deltaPod),
      unavailable: deltaPod === null,
    },
    {
      metric: "Percentil",
      beforeText: pctA === null ? "sin dato" : String(Math.round(pctA)),
      afterText: pctB === null ? "sin dato" : String(Math.round(pctB)),
      delta: deltaPct,
      // Percentil: mayor = mejor (contrario al resto).
      lowerIsBetter: false,
      deltaText: formatDeltaPp(deltaPct),
      unavailable: deltaPct === null,
    },
  ];
}

function formatPosition(
  rank: number | null | undefined,
  size: number | null | undefined,
): string {
  if (rank === null || rank === undefined) return "—";
  if (size !== null && size !== undefined && size > 0) {
    return `P${rank} de ${size}`;
  }
  return `P${rank}`;
}

// ---------------------------------------------------------------------------
// Celda Δ con triple canal (icono + color + texto)
// ---------------------------------------------------------------------------

function DeltaCell({ row }: { row: RowSpec }) {
  // "Mejora" se determina relativa a la dirección de la métrica.
  const improved = row.delta === null ? null : row.lowerIsBetter ? row.delta < 0 : row.delta > 0;

  // Convención visual: el icono representa la PROGRESIÓN del atleta,
  // no el signo numérico del delta. Mejora siempre apunta arriba.
  let Icon = Equal;
  let colorCls = "text-mid-gray";
  let stateLabel = "sin cambio";
  if (improved === true) {
    Icon = ArrowUp;
    colorCls = "text-green-800";
    stateLabel = "mejoró";
  } else if (improved === false) {
    Icon = ArrowDown;
    colorCls = "text-red-800";
    stateLabel = "empeoró";
  }

  const ariaLabel = `${row.metric}: ${stateLabel}, ${row.deltaText}`;

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 text-sm font-semibold",
        colorCls,
      )}
      aria-label={ariaLabel}
    >
      <Icon size={14} aria-hidden="true" />
      {row.deltaText}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Resumen "Mejoró N de M métricas — Confianza X"
// ---------------------------------------------------------------------------

function ImprovementSummary({
  rows,
  confidence,
  labelB,
}: {
  rows: RowSpec[];
  confidence: string | null | undefined;
  labelB: string;
}) {
  // Solo cuentan las métricas con delta numérico (ambos lados con dato).
  const comparable = rows.filter((r) => !r.unavailable && r.delta !== null);
  if (comparable.length === 0) return null;
  const improved = comparable.filter((r) =>
    r.lowerIsBetter ? (r.delta as number) < 0 : (r.delta as number) > 0,
  ).length;
  const confidenceLabel =
    confidence === "high" ? "Alta" : confidence === "medium" ? "Media" : "Baja";

  return (
    <p
      data-testid="comparator-improvement-summary"
      className="text-sm font-medium text-charcoal"
    >
      Mejoró {improved} de {comparable.length} métricas — Confianza {confidenceLabel} ·{" "}
      {labelB}
    </p>
  );
}
