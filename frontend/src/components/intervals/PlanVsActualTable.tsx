/**
 * PlanVsActualTable — tabla de comparación plan-vs-real del módulo
 * Entrenamiento por Intervalos (feature 026, US2 / FR-017).
 *
 * Componente presentacional puro (sin data-fetching): recibe los bloques
 * aplanados ya emparejados con sus vueltas, las vueltas extra y el resumen
 * agregado, y renderiza:
 *   - una fila por bloque planeado ↔ vuelta real, con badge de cumplimiento
 *     (verde = cumplido, ámbar = fuera de tolerancia, gris = sin dato);
 *   - filas informativas por cada vuelta extra registrada por el dispositivo
 *     que no corresponde a ningún bloque (nunca es un error, es información);
 *   - una tira de resumen con los conteos por estado.
 *
 * Privacidad (Ley 1581, D4): las vueltas solo exponen duración / FC media /
 * velocidad media. Este componente NUNCA recibe ni muestra GPS, polyline,
 * mapa, cadencia real ni potencia — esas dimensiones no existen en el payload.
 */

import { Badge, type BadgeProps } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type {
  BlockMatchStatus,
  IntervalBlockType,
  MatchBlock,
  MatchExtraLap,
  MatchSummary,
} from "@/types/intervals.types";

// ---------------------------------------------------------------------------
// Etiquetas y helpers de presentación (español neutro)
// ---------------------------------------------------------------------------

const BLOCK_TYPE_LABEL: Record<IntervalBlockType, string> = {
  warmup: "Calentamiento",
  work: "Trabajo",
  recovery: "Recuperación",
  cooldown: "Enfriamiento",
};

const STATUS_META: Record<
  BlockMatchStatus,
  { label: string; variant: BadgeProps["variant"] }
> = {
  cumplido: { label: "Cumplido", variant: "success" },
  fuera_tolerancia: { label: "Fuera de tolerancia", variant: "warning" },
  sin_dato: { label: "Sin dato", variant: "secondary" },
};

/** Segundos → "m:ss" (ej. 312 → "5:12"). Retorna "—" si es null/undefined. */
function formatSeconds(value: number | null | undefined): string {
  if (value == null) return "—";
  const total = Math.round(value);
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

/** FC media → "128 bpm" (0 decimales). "—" si no hay dato. */
function formatHeartRate(value: number | null | undefined): string {
  if (value == null) return "—";
  return `${Math.round(value)} bpm`;
}

/** Velocidad media m/s → "14,8 km/h". "—" si no hay dato. Nunca expone GPS. */
function formatSpeed(value: number | null | undefined): string {
  if (value == null) return "—";
  const kmh = value * 3.6;
  return `${kmh.toFixed(1).replace(".", ",")} km/h`;
}

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface PlanVsActualTableProps {
  /** Bloques aplanados emparejados con su vuelta (o sin ella → `sin_dato`). */
  blocks: MatchBlock[];
  /** Vueltas del dispositivo sin bloque planeado — filas informativas. */
  extraLaps?: MatchExtraLap[];
  /** Conteos agregados por estado (encabezado de resumen). */
  summary?: MatchSummary | null;
  /** Umbral de tolerancia de duración aplicado (ej. 30 → ±30 %). */
  tolerancePct?: number | null;
}

// ---------------------------------------------------------------------------
// Componente
// ---------------------------------------------------------------------------

export function PlanVsActualTable({
  blocks,
  extraLaps = [],
  summary,
  tolerancePct,
}: PlanVsActualTableProps) {
  return (
    <div className="space-y-4" data-testid="plan-vs-actual">
      {summary && (
        <div
          className="flex flex-wrap items-center gap-2"
          data-testid="plan-vs-actual-summary"
        >
          <Badge variant="success">{summary.cumplido} cumplidos</Badge>
          <Badge variant="warning">
            {summary.fuera_tolerancia} fuera de tolerancia
          </Badge>
          <Badge variant="secondary">{summary.sin_dato} sin dato</Badge>
          {summary.extra > 0 && (
            <Badge variant="info">{summary.extra} vueltas extra</Badge>
          )}
        </div>
      )}

      <Table>
        <caption className="sr-only">
          Comparación entre los bloques planeados y las vueltas registradas por
          el dispositivo.
        </caption>
        <TableHeader>
          <TableRow>
            <TableHead scope="col">Bloque</TableHead>
            <TableHead scope="col">Duración planeada</TableHead>
            <TableHead scope="col">Zona FC</TableHead>
            <TableHead scope="col">Cadencia obj.</TableHead>
            <TableHead scope="col">Vuelta</TableHead>
            <TableHead scope="col">Duración real</TableHead>
            <TableHead scope="col">FC media</TableHead>
            <TableHead scope="col">Vel. media</TableHead>
            <TableHead scope="col">Estado</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {blocks.map((block) => {
            const meta = STATUS_META[block.status];
            return (
              <TableRow key={`block-${block.flat_index}`}>
                <TableCell className="font-medium">
                  {BLOCK_TYPE_LABEL[block.block_type]}
                  {block.repeat_iteration != null && (
                    <span className="ml-1 text-xs text-mid-gray">
                      (rep. {block.repeat_iteration})
                    </span>
                  )}
                </TableCell>
                <TableCell>{formatSeconds(block.planned_duration_s)}</TableCell>
                <TableCell>{block.target_zone}</TableCell>
                <TableCell>{block.target_cadence_rpm} rpm</TableCell>
                <TableCell>
                  {block.lap_index != null ? `#${block.lap_index + 1}` : "—"}
                </TableCell>
                <TableCell>{formatSeconds(block.lap_elapsed_time_s)}</TableCell>
                <TableCell>
                  {formatHeartRate(block.lap_average_heartrate)}
                </TableCell>
                <TableCell>{formatSpeed(block.lap_average_speed_m_s)}</TableCell>
                <TableCell>
                  <Badge variant={meta.variant}>{meta.label}</Badge>
                </TableCell>
              </TableRow>
            );
          })}

          {extraLaps.map((lap) => (
            <TableRow
              key={`extra-${lap.lap_index}`}
              className="bg-light-gray/30"
              data-testid="plan-vs-actual-extra-lap"
            >
              <TableCell className="font-medium text-mid-gray">
                Vuelta extra
              </TableCell>
              <TableCell aria-hidden="true">—</TableCell>
              <TableCell aria-hidden="true">—</TableCell>
              <TableCell aria-hidden="true">—</TableCell>
              <TableCell>{`#${lap.lap_index + 1}`}</TableCell>
              <TableCell>{formatSeconds(lap.elapsed_time_s)}</TableCell>
              <TableCell>{formatHeartRate(lap.average_heartrate)}</TableCell>
              <TableCell aria-hidden="true">—</TableCell>
              <TableCell>
                <Badge variant="info">Extra</Badge>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
        {tolerancePct != null && (
          <TableCaption>
            Un bloque se marca como cumplido si su duración real está dentro del
            ±{tolerancePct} % de lo planeado. Las vueltas menores a 10 segundos
            se descartan por ruido del dispositivo.
          </TableCaption>
        )}
      </Table>
    </div>
  );
}

export default PlanVsActualTable;
