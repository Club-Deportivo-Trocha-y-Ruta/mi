/**
 * ComparatorPanel — compara el insight aprobado de dos válidas del
 * deportista lado a lado (FE-1).
 *
 * Layout:
 *   - Header con selector de temporada + dos selectores de válida (A vs B).
 *   - Grid 2 columnas (stack en mobile): cada columna muestra el
 *     summary del insight y las métricas clave del snapshot.
 *   - Delta calculado client-side: verde = mejora, rojo = regresión.
 *
 * "Mejora" depende de la métrica:
 *   - tiempo, podium_gap, ranking → menor es mejor.
 *
 * Si una válida no tiene insight aprobado, muestra empty placeholder
 * en esa columna sin romper la otra.
 */
import { useState } from "react";
import { ArrowDown, ArrowUp, Minus, Scale } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { useAthleteInsights } from "@/hooks/athletes/useAthleteInsights";
import { cn } from "@/lib/utils";
import {
  isMetricsSnapshotV1,
  type AthleteInsightOut,
  type MetricsSnapshot,
} from "@/types/athleteRaceAnalysis.types";
import { useAthleteInsightDetail } from "@/hooks/athletes/useAthleteInsightDetail";

const cardShadow =
  "rgba(19, 19, 22, 0.7) 0px 1px 5px -4px, rgba(34, 42, 53, 0.08) 0px 0px 0px 1px, rgba(34, 42, 53, 0.05) 0px 4px 8px 0px";

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

function getDefaultSeason(): number {
  return new Date().getFullYear();
}

function formatTime(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return "—";
  const totalSec = ms / 1000;
  const min = Math.floor(totalSec / 60);
  const sec = (totalSec - min * 60).toFixed(1);
  return `${min}:${sec.padStart(4, "0")}`;
}

function formatDeltaTime(deltaMs: number): string {
  const abs = Math.abs(deltaMs);
  const sec = (abs / 1000).toFixed(1);
  return `${deltaMs >= 0 ? "+" : "−"}${sec}s`;
}

interface ComparatorPanelProps {
  athleteId: number;
}

export function ComparatorPanel({ athleteId }: ComparatorPanelProps) {
  const [season, setSeason] = useState<number>(getDefaultSeason());
  const [validaA, setValidaA] = useState<number>(1);
  const [validaB, setValidaB] = useState<number>(2);

  return (
    <section
      className="rounded-xl bg-white p-5 space-y-4"
      style={{ boxShadow: cardShadow }}
      aria-label="Comparador entre válidas"
      data-testid="comparator-panel"
    >
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3
            className="flex items-center gap-2 text-sm text-charcoal"
            style={{ fontFamily: "'Cal Sans', system-ui, sans-serif", fontWeight: 600, letterSpacing: "0.2px" }}
          >
            <Scale size={16} aria-hidden="true" />
            Comparador
          </h3>
          <p className="mt-0.5 text-xs text-mid-gray">
            Compara dos válidas dentro de la misma temporada.
          </p>
        </div>
        <label className="sr-only" htmlFor="cmp-season">
          Temporada
        </label>
        <select
          id="cmp-season"
          value={season}
          onChange={(e) => setSeason(Number(e.target.value))}
          className="rounded-lg bg-white px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary/40"
          style={{ boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" }}
          data-testid="comparator-season-select"
        >
          {Array.from({ length: getDefaultSeason() - 2023 }, (_, i) => getDefaultSeason() - i).map((y) => (
            <option key={y} value={y}>
              {y}
            </option>
          ))}
        </select>
      </header>

      <div className="grid gap-4 md:grid-cols-2">
        <ComparatorColumn
          athleteId={athleteId}
          season={season}
          validaNum={validaA}
          onValidaChange={setValidaA}
          label="Válida A"
          testId="comparator-col-a"
        />
        <ComparatorColumn
          athleteId={athleteId}
          season={season}
          validaNum={validaB}
          onValidaChange={setValidaB}
          label="Válida B"
          testId="comparator-col-b"
        />
      </div>

      <DeltaBlock
        athleteId={athleteId}
        season={season}
        validaA={validaA}
        validaB={validaB}
      />
    </section>
  );
}

// ---------------------------------------------------------------------------
// Column — un lado del comparador
// ---------------------------------------------------------------------------

interface ComparatorColumnProps {
  athleteId: number;
  season: number;
  validaNum: number;
  onValidaChange: (v: number) => void;
  label: string;
  testId: string;
}

function ComparatorColumn({
  athleteId,
  season,
  validaNum,
  onValidaChange,
  label,
  testId,
}: ComparatorColumnProps) {
  const listQuery = useAthleteInsights(athleteId, {
    season,
    valida_num: validaNum,
    latest_only: true,
    limit: 1,
  });

  const head = listQuery.data?.items[0];
  const detailQuery = useAthleteInsightDetail(athleteId, head?.id);

  return (
    <div
      className="rounded-xl bg-light-gray/30 p-4 space-y-3"
      data-testid={testId}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-medium uppercase tracking-wide text-mid-gray">
          {label}
        </span>
        <select
          value={validaNum}
          onChange={(e) => onValidaChange(Number(e.target.value))}
          className="rounded-md bg-white px-2 py-1 text-xs outline-none focus:ring-2 focus:ring-primary/40"
          style={{ boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" }}
          aria-label={`${label} — seleccionar válida`}
        >
          {VALIDA_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      </div>

      {listQuery.isLoading ? (
        <Skeleton className="h-32 w-full rounded-lg" />
      ) : !head ? (
        <p className="rounded-lg bg-white/60 p-4 text-center text-xs text-mid-gray">
          Sin análisis aprobado para esta válida.
        </p>
      ) : (
        <>
          <ColumnInsightHeader insight={head} />
          {detailQuery.isLoading ? (
            <Skeleton className="h-24 w-full rounded-lg" />
          ) : detailQuery.data ? (
            <ColumnMetrics snapshot={detailQuery.data.metrics_snapshot} />
          ) : null}
          <p className="rounded-lg bg-white/60 px-3 py-2 text-xs leading-relaxed text-charcoal">
            {head.summary_text.length > 200
              ? `${head.summary_text.slice(0, 199)}…`
              : head.summary_text}
          </p>
        </>
      )}
    </div>
  );
}

function ColumnInsightHeader({ insight }: { insight: AthleteInsightOut }) {
  return (
    <div className="flex flex-wrap items-center gap-2 text-xs">
      <Badge
        variant={
          insight.confidence === "high"
            ? "success"
            : insight.confidence === "medium"
            ? "warning"
            : "destructive"
        }
      >
        {insight.confidence === "high"
          ? "Alta"
          : insight.confidence === "medium"
          ? "Media"
          : "Baja"}
      </Badge>
      <span className="text-mid-gray">
        {new Date(insight.generated_at).toLocaleDateString("es-CO", {
          day: "2-digit",
          month: "short",
        })}
      </span>
    </div>
  );
}

function ColumnMetrics({ snapshot }: { snapshot: MetricsSnapshot }) {
  if (!isMetricsSnapshotV1(snapshot)) {
    return null;
  }
  return (
    <dl className="grid grid-cols-3 gap-2 text-xs">
      <MetricCell label="Tiempo" value={formatTime(snapshot.race_time_ms)} />
      <MetricCell
        label="Pos."
        value={
          snapshot.ranking_in_category !== null &&
          snapshot.ranking_in_category !== undefined
            ? `P${snapshot.ranking_in_category}`
            : "—"
        }
      />
      <MetricCell
        label="Δ podio"
        value={formatTime(snapshot.podium_gap_ms)}
      />
    </dl>
  );
}

function MetricCell({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md bg-white/70 px-2 py-1.5">
      <dt className="text-[10px] font-medium uppercase tracking-wide text-mid-gray">
        {label}
      </dt>
      <dd className="text-sm font-semibold text-charcoal">{value}</dd>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Delta — diferencia entre las dos válidas (cliente)
// ---------------------------------------------------------------------------

interface DeltaBlockProps {
  athleteId: number;
  season: number;
  validaA: number;
  validaB: number;
}

function DeltaBlock({
  athleteId,
  season,
  validaA,
  validaB,
}: DeltaBlockProps) {
  // Reutilizamos los queries de las columnas — TanStack los deduplica.
  const listA = useAthleteInsights(athleteId, {
    season,
    valida_num: validaA,
    latest_only: true,
    limit: 1,
  });
  const listB = useAthleteInsights(athleteId, {
    season,
    valida_num: validaB,
    latest_only: true,
    limit: 1,
  });
  const headA = listA.data?.items[0];
  const headB = listB.data?.items[0];
  const detailA = useAthleteInsightDetail(athleteId, headA?.id);
  const detailB = useAthleteInsightDetail(athleteId, headB?.id);

  if (!detailA.data || !detailB.data) return null;
  if (
    !isMetricsSnapshotV1(detailA.data.metrics_snapshot) ||
    !isMetricsSnapshotV1(detailB.data.metrics_snapshot)
  ) {
    return null;
  }
  const snapA = detailA.data.metrics_snapshot;
  const snapB = detailB.data.metrics_snapshot;

  const deltaTime =
    snapA.race_time_ms !== null &&
    snapA.race_time_ms !== undefined &&
    snapB.race_time_ms !== null &&
    snapB.race_time_ms !== undefined
      ? snapB.race_time_ms - snapA.race_time_ms
      : null;

  const deltaRank =
    snapA.ranking_in_category !== null &&
    snapA.ranking_in_category !== undefined &&
    snapB.ranking_in_category !== null &&
    snapB.ranking_in_category !== undefined
      ? snapB.ranking_in_category - snapA.ranking_in_category
      : null;

  const deltaGap =
    snapA.podium_gap_ms !== null &&
    snapA.podium_gap_ms !== undefined &&
    snapB.podium_gap_ms !== null &&
    snapB.podium_gap_ms !== undefined
      ? snapB.podium_gap_ms - snapA.podium_gap_ms
      : null;

  return (
    <div
      className="rounded-xl bg-light-gray/30 p-4"
      aria-label="Diferencias entre las dos válidas"
    >
      <p className="mb-3 text-xs font-medium uppercase tracking-wide text-mid-gray">
        Diferencia B − A
      </p>
      <dl className="grid grid-cols-3 gap-3">
        <DeltaCell
          label="Tiempo"
          value={deltaTime !== null ? formatDeltaTime(deltaTime) : "—"}
          improved={deltaTime !== null ? deltaTime < 0 : null}
        />
        <DeltaCell
          label="Ranking"
          value={
            deltaRank !== null
              ? `${deltaRank > 0 ? "+" : ""}${deltaRank}`
              : "—"
          }
          improved={deltaRank !== null ? deltaRank < 0 : null}
        />
        <DeltaCell
          label="Δ podio"
          value={deltaGap !== null ? formatDeltaTime(deltaGap) : "—"}
          improved={deltaGap !== null ? deltaGap < 0 : null}
        />
      </dl>
    </div>
  );
}

function DeltaCell({
  label,
  value,
  improved,
}: {
  label: string;
  value: string;
  improved: boolean | null;
}) {
  const arrow =
    improved === null ? (
      <Minus size={14} aria-hidden="true" />
    ) : improved ? (
      <ArrowDown size={14} aria-hidden="true" />
    ) : (
      <ArrowUp size={14} aria-hidden="true" />
    );
  const colorCls =
    improved === null
      ? "text-mid-gray"
      : improved
      ? "text-green-700"
      : "text-red-700";
  return (
    <div className="rounded-lg bg-white/70 px-3 py-2 text-center">
      <dt className="text-[10px] font-medium uppercase tracking-wide text-mid-gray">
        {label}
      </dt>
      <dd
        className={cn(
          "mt-1 inline-flex items-center gap-1 text-sm font-semibold",
          colorCls,
        )}
      >
        {arrow}
        {value}
      </dd>
    </div>
  );
}
