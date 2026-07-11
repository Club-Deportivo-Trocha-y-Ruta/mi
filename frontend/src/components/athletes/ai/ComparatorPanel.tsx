/**
 * ComparatorPanel v2 — comparador progreso A → B del análisis IA por atleta.
 *
 * Caso de uso MVP:
 *   Coach: "¿Mi atleta mejoró o empeoró entre la Válida X y la Válida Y de
 *   esta temporada?". Padre: vista cualitativa.
 *
 * Layout (consenso UX + head-coach):
 *   ┌─ Header (título + select Temporada) ────────────────────────┐
 *   │ Selector ANTES   [swap ⇄]   Selector DESPUÉS               │
 *   │ Banner tapering (si tipos A vs B difieren)                  │
 *   │ Banner Circa-PHV (si record antropométrico reciente)        │
 *   │ Tabla unificada: Métrica | Antes | Después | Cambio        │
 *   │ Resumen "Mejoró N de M métricas — Confianza X"              │
 *   │ CTA "Ver análisis IA completo →"                            │
 *   └──────────────────────────────────────────────────────────────┘
 *
 * Privacidad:
 *   - Nunca expone nombres de rivales.
 *   - Vista parent: sin tiempos absolutos ni gaps en segundos.
 *
 * Principio coach: NO mostramos gap al ganador ni % del ganador — viola
 * "edad biológica > cronológica" (el P1 puede ser Post-PHV mientras el
 * atleta es Pre-PHV).
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
import { useAnthropometry } from "@/hooks/athletes/useAnthropometry";
import { useAthleteInsightDetail } from "@/hooks/athletes/useAthleteInsightDetail";
import { useAthleteInsights } from "@/hooks/athletes/useAthleteInsights";
import {
  getRaceMeta,
  getRaceTypeBadgeStyle,
  getValidaLabel,
  type RaceMeta,
} from "@/lib/raceCalendar";
import {
  computePercentile,
  evaluateImprovementCount,
  extractMetricsForValida,
  formatDeltaRank,
  formatDeltaTime,
  formatQualitativePodiumProximity,
  formatQualitativeRank,
  formatRaceTime,
  type ExtractedMetrics,
} from "@/lib/raceMetrics";
import { formatDayMonthShort } from "@/lib/datetime";
import { cn } from "@/lib/utils";
import {
  isMetricsSnapshotV1,
  type AthleteInsightDetailOut,
  type AthleteInsightOut,
} from "@/types/athleteRaceAnalysis.types";
import { MaturationStatus } from "@/types/enums";

// ---------------------------------------------------------------------------
// Constantes
// ---------------------------------------------------------------------------

/** Opciones del selector de válida. 0 representa "Sin selección". */
const VALIDA_OPTIONS: Array<{ value: number; label: string }> = [
  { value: 1, label: "Válida I" },
  { value: 2, label: "Válida II" },
  { value: 3, label: "Válida III" },
  { value: 4, label: "Válida IV" },
  { value: 5, label: "Válida V" },
  { value: 6, label: "Válida VI" },
  { value: 7, label: "Válida VII" },
  { value: 99, label: "Cto. Departamental" },
];

/** Tap target mínimo WCAG (44×44 px). */
const TAP_TARGET_CLASSES = "min-h-[44px]";

/** Ventana de "reciente" para considerar el record antropométrico vigente. */
const PHV_FRESHNESS_DAYS = 90;

function getDefaultSeason(): number {
  return new Date().getFullYear();
}

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface ComparatorPanelProps {
  athleteId: number;
  /** "coach" (default) muestra números absolutos; "parent" solo cualitativo. */
  viewMode?: "coach" | "parent";
}

// ---------------------------------------------------------------------------
// Componente principal
// ---------------------------------------------------------------------------

export function ComparatorPanel({
  athleteId,
  viewMode = "coach",
}: ComparatorPanelProps) {
  const [season, setSeason] = useState<number>(getDefaultSeason());

  // Lista global de insights aprobados/activos de la temporada — usada para:
  //   1. Calcular defaults inteligentes (primera y última válida con insight).
  //   2. Detectar empty state global (menos de 2 válidas con insight).
  //   3. Calcular "mejor marca propia" agregando todos los detalles.
  const seasonListQuery = useAthleteInsights(athleteId, {
    season,
    limit: 50,
  });

  const validasConInsight = useMemo(() => {
    const items = seasonListQuery.data?.items ?? [];
    // Solo insights aprobados/activos con válida COMPETITIVA específica.
    // Excluimos valida_num=0 (sentinel del backend para "Resumen de
    // temporada") y números fuera del calendario Copa Valle.
    const knownValidas = new Set([1, 2, 3, 4, 5, 6, 7, 99]);
    const filtered = items.filter(
      (i) =>
        i.coach_approved &&
        i.is_active &&
        i.valida_num !== null &&
        i.valida_num !== undefined &&
        knownValidas.has(i.valida_num),
    );
    // Dedup por valida_num conservando el más reciente.
    const byValida = new Map<number, AthleteInsightOut>();
    for (const i of filtered) {
      const v = i.valida_num as number;
      const prev = byValida.get(v);
      if (
        !prev ||
        new Date(i.generated_at).getTime() > new Date(prev.generated_at).getTime()
      ) {
        byValida.set(v, i);
      }
    }
    // Orden cronológico por fecha de la válida en el calendario (si existe)
    // o por valida_num como fallback.
    return Array.from(byValida.values()).sort((a, b) => {
      const metaA = getRaceMeta(season, a.valida_num);
      const metaB = getRaceMeta(season, b.valida_num);
      if (metaA && metaB) return metaA.date_iso.localeCompare(metaB.date_iso);
      return (a.valida_num ?? 0) - (b.valida_num ?? 0);
    });
  }, [seasonListQuery.data, season]);

  // Defaults: primera y última válida con insight aprobado.
  const [validaA, setValidaA] = useState<number | null>(null);
  const [validaB, setValidaB] = useState<number | null>(null);

  useEffect(() => {
    // Solo seteamos cuando todavía no hay selección o cuando cambia la
    // temporada y los valores actuales ya no aplican.
    if (validasConInsight.length === 0) {
      setValidaA(null);
      setValidaB(null);
      return;
    }
    const first = validasConInsight[0].valida_num as number;
    const last =
      validasConInsight[validasConInsight.length - 1].valida_num as number;
    setValidaA((current) => {
      if (current === null) return first;
      const stillExists = validasConInsight.some((i) => i.valida_num === current);
      return stillExists ? current : first;
    });
    setValidaB((current) => {
      if (current === null) return last !== first ? last : first;
      const stillExists = validasConInsight.some((i) => i.valida_num === current);
      return stillExists ? current : last;
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [validasConInsight.length, season]);

  const handleSwap = () => {
    setValidaA(validaB);
    setValidaB(validaA);
  };

  // Estados derivados
  const hasEnoughValidas = validasConInsight.length >= 2;
  const sameValida = validaA !== null && validaA === validaB;

  return (
    <section
      className={cn("rounded-xl bg-white p-5 space-y-4", "shadow-card")}
      aria-label="Comparador progreso entre válidas"
      data-testid="comparator-panel"
    >
      <Header season={season} onSeasonChange={setSeason} />

      {seasonListQuery.isLoading ? (
        <Skeleton className="h-40 w-full rounded-lg" />
      ) : !hasEnoughValidas ? (
        <EmptyPair count={validasConInsight.length} />
      ) : (
        <>
          <SelectorsRow
            season={season}
            validaA={validaA}
            validaB={validaB}
            onValidaAChange={setValidaA}
            onValidaBChange={setValidaB}
            onSwap={handleSwap}
            availableValidas={validasConInsight
              .map((i) => i.valida_num as number)
              .sort((a, b) => a - b)}
          />

          {sameValida ? (
            <p
              role="status"
              className="rounded-xl bg-amber-50 px-4 py-3 text-sm text-amber-900"
            >
              Selecciona dos válidas distintas para comparar.
            </p>
          ) : (
            <ComparisonBody
              athleteId={athleteId}
              season={season}
              validaA={validaA as number}
              validaB={validaB as number}
              insightA={validasConInsight.find((i) => i.valida_num === validaA)}
              insightB={validasConInsight.find((i) => i.valida_num === validaB)}
              viewMode={viewMode}
            />
          )}
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
          Mide al atleta contra sí mismo entre dos válidas de la temporada.
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
          "rounded-lg bg-white px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary/40",
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
// Selectores A / swap / B + chips de tipo carrera
// ---------------------------------------------------------------------------

function SelectorsRow({
  season,
  validaA,
  validaB,
  onValidaAChange,
  onValidaBChange,
  onSwap,
  availableValidas,
}: {
  season: number;
  validaA: number | null;
  validaB: number | null;
  onValidaAChange: (v: number) => void;
  onValidaBChange: (v: number) => void;
  onSwap: () => void;
  availableValidas: number[];
}) {
  return (
    <div className="grid grid-cols-1 items-start gap-3 md:grid-cols-[1fr_auto_1fr]">
      <SideSelector
        side="A"
        label="ANTES"
        validaNum={validaA}
        onChange={onValidaAChange}
        season={season}
        availableValidas={availableValidas}
      />
      <button
        type="button"
        onClick={onSwap}
        aria-label="Intercambiar antes y después"
        data-testid="comparator-swap"
        className={cn(
          "mx-auto inline-flex items-center justify-center self-center rounded-full bg-light-gray text-charcoal",
          TAP_TARGET_CLASSES,
          "min-w-[44px] transition motion-reduce:transition-none hover:bg-light-gray/70 focus:outline-none focus:ring-2 focus:ring-primary/40",
        )}
      >
        <ArrowLeftRight size={18} aria-hidden="true" />
      </button>
      <SideSelector
        side="B"
        label="DESPUÉS"
        validaNum={validaB}
        onChange={onValidaBChange}
        season={season}
        availableValidas={availableValidas}
      />
    </div>
  );
}

function SideSelector({
  side,
  label,
  validaNum,
  onChange,
  season,
  availableValidas,
}: {
  side: "A" | "B";
  label: string;
  validaNum: number | null;
  onChange: (v: number) => void;
  season: number;
  availableValidas: number[];
}) {
  const meta = getRaceMeta(season, validaNum);
  const badgeStyle = meta ? getRaceTypeBadgeStyle(meta.type) : null;
  const testId = side === "A" ? "comparator-col-a" : "comparator-col-b";
  return (
    <div className="rounded-xl bg-light-gray/30 p-3" data-testid={testId}>
      <div className="text-[10px] font-semibold uppercase tracking-wider text-mid-gray">
        {label}
      </div>
      <select
        value={validaNum ?? ""}
        onChange={(e) => onChange(Number(e.target.value))}
        aria-label={`${side === "A" ? "Válida A" : "Válida B"} — seleccionar válida`}
        className={cn(
          "mt-1 w-full rounded-lg bg-white px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary/40",
          TAP_TARGET_CLASSES,
          "shadow-ring",
        )}
      >
        {VALIDA_OPTIONS.map((o) => (
          <option
            key={o.value}
            value={o.value}
            disabled={!availableValidas.includes(o.value)}
          >
            {o.label}
            {!availableValidas.includes(o.value) ? " (sin análisis)" : ""}
          </option>
        ))}
      </select>
      <div className="mt-2 flex items-center gap-2 text-xs">
        {meta ? (
          <>
            <Badge
              className={cn(badgeStyle?.className)}
              aria-label={`Tipo de carrera: ${badgeStyle?.label}`}
            >
              {badgeStyle?.label}
            </Badge>
            <span className="text-mid-gray">
              {meta.location} · {formatDayMonthShort(`${meta.date_iso}T12:00:00Z`)}
            </span>
          </>
        ) : (
          <span className="text-mid-gray">Sin metadata de calendario</span>
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
        : "Necesitas al menos 2 válidas con análisis aprobado para comparar."}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Cuerpo de la comparación — banners + tabla + resumen + CTA
// ---------------------------------------------------------------------------

function ComparisonBody({
  athleteId,
  season,
  validaA,
  validaB,
  insightA,
  insightB,
  viewMode,
}: {
  athleteId: number;
  season: number;
  validaA: number;
  validaB: number;
  insightA: AthleteInsightOut | undefined;
  insightB: AthleteInsightOut | undefined;
  viewMode: "coach" | "parent";
}) {
  const detailA = useAthleteInsightDetail(athleteId, insightA?.id);
  const detailB = useAthleteInsightDetail(athleteId, insightB?.id);

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

  const metaA = getRaceMeta(season, validaA);
  const metaB = getRaceMeta(season, validaB);
  const taperingMismatch =
    !!metaA && !!metaB && metaA.type !== metaB.type;

  if (detailA.isLoading || detailB.isLoading) {
    return <Skeleton className="h-64 w-full rounded-lg" />;
  }

  return (
    <div className="space-y-3">
      {taperingMismatch ? (
        <TaperingBanner metaA={metaA} metaB={metaB} />
      ) : null}
      {phvBannerVisible ? <PHVBanner /> : null}

      <DiffTable
        season={season}
        validaA={validaA}
        validaB={validaB}
        detailA={detailA.data ?? null}
        detailB={detailB.data ?? null}
        viewMode={viewMode}
      />

      <ImprovementSummary
        detailA={detailA.data ?? null}
        detailB={detailB.data ?? null}
        validaA={validaA}
        validaB={validaB}
      />

      {viewMode === "parent" ? (
        <p className="rounded-lg bg-light-gray/30 px-4 py-3 text-center text-xs italic text-mid-gray">
          Se mide contra sí mismo, no contra el ganador.
        </p>
      ) : null}

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
// Banner: tipos de carrera distintos (warning de tapering)
// ---------------------------------------------------------------------------

function TaperingBanner({
  metaA,
  metaB,
}: {
  metaA: RaceMeta;
  metaB: RaceMeta;
}) {
  return (
    <p
      role="note"
      data-testid="comparator-tapering-banner"
      className="rounded-xl bg-amber-50 px-4 py-3 text-xs text-amber-900"
    >
      <strong>Carreras de distinto tipo</strong> ({metaA.type} vs {metaB.type}).
      Parte de la mejora puede deberse al tapering. Interpreta con cautela.
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
  /** ``true`` ⇒ valor menor es mejor (tiempo, ranking, gap). */
  lowerIsBetter: boolean;
  /** Override para el formateo del delta visible. */
  deltaText: string;
  /** ``true`` si la fila no tiene datos para alguno de los lados. */
  unavailable?: boolean;
  /** Label cualitativo opcional (vista parent). */
  qualitativeLabel?: string;
}

function DiffTable({
  validaA,
  validaB,
  detailA,
  detailB,
  viewMode,
}: {
  season: number;
  validaA: number;
  validaB: number;
  detailA: AthleteInsightDetailOut | null;
  detailB: AthleteInsightDetailOut | null;
  viewMode: "coach" | "parent";
}) {
  const snapA = detailA?.metrics_snapshot;
  const snapB = detailB?.metrics_snapshot;

  // Estrategia: 1) snapshot V1 plano (futuro) o 2) extracción desde
  // progression[] del snapshot legacy real (formato actual del backend).
  const metricsA: ExtractedMetrics | null =
    isMetricsSnapshotV1(snapA)
      ? {
          race_time_ms: snapA.race_time_ms ?? null,
          ranking_in_category: snapA.ranking_in_category ?? null,
          podium_gap_ms: snapA.podium_gap_ms ?? null,
          category_size: snapA.category_size ?? null,
          category_time_min_ms: snapA.category_time_min_ms ?? null,
          category_time_max_ms: snapA.category_time_max_ms ?? null,
        }
      : extractMetricsForValida(snapA, validaA);
  const metricsB: ExtractedMetrics | null =
    isMetricsSnapshotV1(snapB)
      ? {
          race_time_ms: snapB.race_time_ms ?? null,
          ranking_in_category: snapB.ranking_in_category ?? null,
          podium_gap_ms: snapB.podium_gap_ms ?? null,
          category_size: snapB.category_size ?? null,
          category_time_min_ms: snapB.category_time_min_ms ?? null,
          category_time_max_ms: snapB.category_time_max_ms ?? null,
        }
      : extractMetricsForValida(snapB, validaB);

  // Solo marcamos "legacy" si NO pudimos extraer ningún dato.
  const noDataA = detailA !== null && metricsA === null;
  const noDataB = detailB !== null && metricsB === null;
  const anyLegacy = noDataA || noDataB;

  const labelA = getValidaLabel(validaA);
  const labelB = getValidaLabel(validaB);

  const rows: RowSpec[] = useMemo(() => {
    return buildRows({
      metricsA,
      metricsB,
      viewMode,
    });
  }, [metricsA, metricsB, viewMode]);

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
                    aria-label="sin análisis aprobado"
                  >
                    —
                  </span>
                ) : (
                  <DeltaCell row={row} />
                )}
              </td>
            </tr>
          ))}
          {anyLegacy ? (
            <tr className="border-t border-light-gray/60">
              <td
                colSpan={4}
                className="px-3 py-2 text-xs italic text-mid-gray"
              >
                Datos no comparables (snapshot legacy).
              </td>
            </tr>
          ) : null}
        </tbody>
      </table>
    </div>
  );
}

interface BuildRowsInput {
  metricsA: ExtractedMetrics | null;
  metricsB: ExtractedMetrics | null;
  viewMode: "coach" | "parent";
}

function buildRows({
  metricsA,
  metricsB,
  viewMode,
}: BuildRowsInput): RowSpec[] {
  const rankA = metricsA?.ranking_in_category ?? null;
  const rankB = metricsB?.ranking_in_category ?? null;
  const sizeA = metricsA?.category_size ?? null;
  const sizeB = metricsB?.category_size ?? null;
  const gapA = metricsA?.podium_gap_ms ?? null;
  const gapB = metricsB?.podium_gap_ms ?? null;

  // Percentil por TIEMPO (override coach real 2026-05-25).
  const pctA = computePercentile(
    metricsA?.race_time_ms ?? null,
    metricsA?.category_time_min_ms ?? null,
    metricsA?.category_time_max_ms ?? null,
    sizeA,
  );
  const pctB = computePercentile(
    metricsB?.race_time_ms ?? null,
    metricsB?.category_time_min_ms ?? null,
    metricsB?.category_time_max_ms ?? null,
    sizeB,
  );

  const deltaRank =
    rankA !== null && rankB !== null ? rankB - rankA : null;
  const deltaGap = gapA !== null && gapB !== null ? gapB - gapA : null;
  // Delta percentil: B − A. Mayor es mejor (subir percentil = mejorar).
  const deltaPct =
    pctA !== null && pctB !== null ? pctB - pctA : null;

  const rows: RowSpec[] = [];

  // 1. Posición en categoría
  rows.push({
    metric: "Posición categoría",
    beforeText: formatPosition(rankA, sizeA),
    afterText: formatPosition(rankB, sizeB),
    delta: deltaRank,
    lowerIsBetter: true,
    deltaText:
      viewMode === "parent"
        ? formatQualitativeRank(deltaRank)
        : formatDeltaRank(deltaRank),
    qualitativeLabel: formatQualitativeRank(deltaRank),
    unavailable: rankA === null || rankB === null,
  });

  // 2. Gap al podio — métrica relativa, sí comparable entre pistas.
  rows.push({
    metric: "Gap al podio",
    beforeText:
      viewMode === "parent"
        ? formatQualitativePodiumProximity(gapA)
        : formatRaceTime(gapA),
    afterText:
      viewMode === "parent"
        ? formatQualitativePodiumProximity(gapB)
        : formatRaceTime(gapB),
    delta: deltaGap,
    lowerIsBetter: true,
    deltaText:
      viewMode === "parent"
        ? gapA === null || gapB === null
          ? "—"
          : (gapB ?? 0) < (gapA ?? 0)
            ? "Más cerca del podio"
            : (gapB ?? 0) > (gapA ?? 0)
              ? "Manteniendo distancia"
              : "Sin cambio"
        : formatDeltaTime(deltaGap),
    unavailable: gapA === null || gapB === null,
  });

  // 3. Percentil de categoría — basado en TIEMPO (override coach real
  //    2026-05-25). Solo se incluye si AMBAS válidas tienen n ≥
  //    PERCENTILE_MIN_FIELD_SIZE (5). Visible a todos (coach + padre).
  if (pctA !== null && pctB !== null) {
    rows.push({
      metric: "Percentil categoría",
      beforeText: `${pctA}`,
      afterText: `${pctB}`,
      delta: deltaPct,
      // Percentil: mayor = mejor (contrario al resto).
      lowerIsBetter: false,
      deltaText:
        deltaPct === null
          ? "—"
          : `${deltaPct > 0 ? "+" : ""}${deltaPct}pp`,
      unavailable: false,
    });
  }

  // NOTA: "Tiempo total" y "Δ vs mejor propia" eliminados (head-coach-lead
  // 2026-05-25): las pistas Copa Valle varían en distancia y dificultad, así
  // que tiempo absoluto induce conclusiones falsas.

  return rows;
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
  detailA,
  detailB,
  validaA,
  validaB,
}: {
  detailA: AthleteInsightDetailOut | null;
  detailB: AthleteInsightDetailOut | null;
  validaA: number;
  validaB: number;
}) {
  const snapA = detailA?.metrics_snapshot;
  const snapB = detailB?.metrics_snapshot;
  const metricsA: ExtractedMetrics | null = isMetricsSnapshotV1(snapA)
    ? {
        race_time_ms: snapA.race_time_ms ?? null,
        ranking_in_category: snapA.ranking_in_category ?? null,
        podium_gap_ms: snapA.podium_gap_ms ?? null,
        category_size: snapA.category_size ?? null,
        category_time_min_ms: snapA.category_time_min_ms ?? null,
        category_time_max_ms: snapA.category_time_max_ms ?? null,
      }
    : extractMetricsForValida(snapA, validaA);
  const metricsB: ExtractedMetrics | null = isMetricsSnapshotV1(snapB)
    ? {
        race_time_ms: snapB.race_time_ms ?? null,
        ranking_in_category: snapB.ranking_in_category ?? null,
        podium_gap_ms: snapB.podium_gap_ms ?? null,
        category_size: snapB.category_size ?? null,
        category_time_min_ms: snapB.category_time_min_ms ?? null,
        category_time_max_ms: snapB.category_time_max_ms ?? null,
      }
    : extractMetricsForValida(snapB, validaB);

  if (!metricsA || !metricsB) return null;

  const pctA = computePercentile(
    metricsA.race_time_ms,
    metricsA.category_time_min_ms,
    metricsA.category_time_max_ms,
    metricsA.category_size,
  );
  const pctB = computePercentile(
    metricsB.race_time_ms,
    metricsB.category_time_min_ms,
    metricsB.category_time_max_ms,
    metricsB.category_size,
  );

  const deltas = {
    rank:
      metricsA.ranking_in_category !== null &&
      metricsB.ranking_in_category !== null
        ? metricsB.ranking_in_category - metricsA.ranking_in_category
        : null,
    gap:
      metricsA.podium_gap_ms !== null && metricsB.podium_gap_ms !== null
        ? metricsB.podium_gap_ms - metricsA.podium_gap_ms
        : null,
    percentile: pctA !== null && pctB !== null ? pctB - pctA : null,
  };

  const { improved, total } = evaluateImprovementCount(deltas);
  const confidenceLabel =
    detailB?.confidence === "high"
      ? "Alta"
      : detailB?.confidence === "medium"
        ? "Media"
        : "Baja";

  return (
    <p
      data-testid="comparator-improvement-summary"
      className="text-sm font-medium text-charcoal"
    >
      Mejoró {improved} de {total} métricas — Confianza {confidenceLabel} ·{" "}
      {getValidaLabel(validaB)}
    </p>
  );
}
