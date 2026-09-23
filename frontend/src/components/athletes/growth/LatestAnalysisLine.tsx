/**
 * LatestAnalysisLine — fila de estado del último análisis de IA por
 * medición, sobre el historial antropométrico del tab Crecimiento
 * (feature 042, Wave 3, T073/T074, FR-027).
 *
 * Fuente de datos: `GrowthSummaryOut.latest_ai_analysis`
 * (`contracts/growth-summary-latest-analysis.md`), ya incluida en la misma
 * respuesta que `useGrowthSummary` — este componente NO dispara ninguna
 * petición propia para el estado de la fila (SC-008: sin round trip
 * adicional). El único fetch que puede ocurrir es al abrir el diálogo de
 * detalle (`AnthropometricRecordExplanationCard`, ya usado por
 * `AnthropometryHistory`), y solo mientras el diálogo está abierto.
 *
 * Siete estados, cada uno con su propio `data-state` para poder probarlos
 * por separado:
 *
 *   - `loading`: `summaryQuery` aún no resuelve → skeleton.
 *   - `error`: `summaryQuery.isError` → mensaje discreto, no bloqueante
 *     (el resto del tab ya tiene su propio `ErrorState` con reintento; esta
 *     fila no duplica ese control).
 *   - (sin fila / `null`): antes de la primera medición no hay nada que
 *     analizar — el componente no renderiza NADA (el bloque resumen de
 *     `GrowthTab` ya cubre ese caso con su propio estado vacío).
 *   - `none`: hay mediciones pero `latest_ai_analysis` es `null`/`undefined`
 *     (sin consentimiento, IA apagada, o nunca generado). Coach ve un botón
 *     para generar uno (abre el diálogo de la medición más reciente);
 *     familia solo ve el mensaje pasivo compartido (`FR-033`), sin acción
 *     ni enlace.
 *   - `current`: hay análisis vigente (`is_stale=false`) — línea + fecha +
 *     enlace "Ver análisis completo", igual para coach y familia.
 *   - `stale`: `is_stale=true` — en modo coach se agrega la insignia
 *     "Desactualizado" y el resumen se atenúa (sigue siendo información
 *     útil, no un error, `data-model.md` §4); en modo familia se ve
 *     IDÉNTICO a `current` — nunca la palabra "Desactualizado" ni ningún
 *     tratamiento visual distinto (la familia solo ve una fecha honesta).
 *   - `flagged`: exclusivo de coach — el backend nunca deja llegar un
 *     veredicto `flagged`/`fallback`/`skipped` a un padre (§0 del
 *     contrato), y por defensa en profundidad este componente trata
 *     cualquier veredicto bloqueado que llegara en modo familia como si
 *     `latest_ai_analysis` fuera `null` (FR-016: una familia nunca debe
 *     poder inferir que existe un análisis retenido). El coach sí ve el
 *     resumen (es el humano en el ciclo) con una nota corta.
 *
 * Nunca se renderiza un slug de modelo, proveedor o id de traza aquí — esta
 * fila solo usa `summary_line`, `record_id`, `critic_verdict` (coach) e
 * `is_stale`, los únicos campos que expone `LatestAiAnalysis`.
 *
 * `is_stale` SIEMPRE viene del servidor (`data-model.md` §4) — este
 * componente no lo recalcula a partir de fechas propias. Ese es exactamente
 * el bug G-02 que `docs/18-growth-module-redesign/proposal.md` ya documentó
 * una vez para este módulo.
 */
import { useState } from "react";
import type { UseQueryResult } from "@tanstack/react-query";

import { AnthropometricRecordExplanationCard } from "@/components/ai/AnthropometricRecordExplanationCard";
import { StatusBadge } from "@/components/shared/StatusBadge";
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { AI_ANALYSIS_NOT_YET_AVAILABLE_MESSAGE } from "@/lib/ai/notYetAvailableMessage";
import { cn } from "@/lib/utils";
import type { CriticVerdict } from "@/types/ai.types";
import type { AnthropometricRecord } from "@/types/anthropometry.types";
import type { GrowthSummary } from "@/types/growth.types";

export interface LatestAnalysisLineProps {
  /** Misma query ya usada por el bloque resumen de `GrowthTab` — no se
   *  vuelve a pedir el resumen desde aquí (SC-008). */
  summaryQuery: UseQueryResult<GrowthSummary, Error>;
  /** Mediciones ya cargadas por `useAnthropometry` en `GrowthTab` — se usan
   *  solo para resolver la fecha de la medición analizada y para abrir su
   *  diálogo; nunca para recalcular `is_stale`. */
  records: AnthropometricRecord[];
  athleteId: number;
  mode: "coach" | "parent";
}

const MONTHS_ES_SHORT = [
  "ene", "feb", "mar", "abr", "may", "jun",
  "jul", "ago", "sep", "oct", "nov", "dic",
];

/**
 * Fecha corta en español ("14 ago 2026") a partir de un `YYYY-MM-DD` plano.
 * Se parte el string en vez de `new Date(...)` para no correr un día al
 * proyectar una fecha sin hora a `America/Bogota` — mismo criterio que
 * `AnthropometryHistory.tsx::formatDate` y
 * `NextMeasurementCard.tsx::formatDueDate`.
 */
function formatMeasurementDate(dateStr: string): string {
  const [year, month, day] = dateStr.split("-");
  const label = MONTHS_ES_SHORT[Number(month) - 1] ?? month;
  return `${Number(day)} ${label} ${year}`;
}

/** Veredictos que nunca llegan a una familia (FR-016, `data-model.md` §3). */
const BLOCKED_VERDICTS = new Set<CriticVerdict>(["flagged", "fallback", "skipped"]);

/** Nota corta solo-coach por veredicto bloqueado — mismo tono que
 *  `AnthropometricRecordExplanationCard`'s `VERDICT_MARKER_COPY`, resumido
 *  a una línea porque aquí solo hay espacio para eso. */
const VERDICT_NOTE: Record<"flagged" | "fallback" | "skipped", string> = {
  flagged: "Con observaciones — revísalo antes de compartirlo con la familia.",
  fallback: "Análisis de respaldo — no llegó a revisarse.",
  skipped: "Sin revisión de calidad todavía.",
};

interface MeasurementDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  athleteId: number;
  record: AnthropometricRecord;
  readOnly: boolean;
}

/**
 * Diálogo mínimo, propio de esta fila — no es el modal completo de
 * `AnthropometryHistory` (esa es la superficie de T075, fuera del alcance
 * de este componente). Enfocado en lo que esta fila promete: el análisis de
 * IA de esa medición puntual. La fecha completa de la medición ya está en
 * el historial de abajo.
 */
function MeasurementDialog({
  open,
  onOpenChange,
  athleteId,
  record,
  readOnly,
}: MeasurementDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-xl" data-testid="latest-analysis-line-dialog">
        <DialogHeader>
          <DialogTitle>
            Medición del {formatMeasurementDate(record.evaluation_date)}
          </DialogTitle>
        </DialogHeader>
        <DialogBody className="max-h-[70vh] overflow-y-auto">
          <AnthropometricRecordExplanationCard
            athleteId={athleteId}
            recordId={record.id}
            readOnly={readOnly}
          />
        </DialogBody>
      </DialogContent>
    </Dialog>
  );
}

function LineShell({
  state,
  children,
  className,
}: {
  state: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      data-testid="latest-analysis-line"
      data-state={state}
      className={cn(
        "flex min-h-12 flex-wrap items-center justify-between gap-2 rounded-card bg-surface-raised px-4 py-3 shadow-card ring-1 ring-hairline",
        className,
      )}
    >
      {children}
    </div>
  );
}

export function LatestAnalysisLine({
  summaryQuery,
  records,
  athleteId,
  mode,
}: LatestAnalysisLineProps) {
  const [dialogOpen, setDialogOpen] = useState(false);
  const isCoach = mode === "coach";

  // ---- loading ------------------------------------------------------------
  if (summaryQuery.isLoading) {
    return (
      <div
        role="status"
        aria-busy="true"
        aria-label="Cargando el estado del análisis de IA…"
        data-testid="latest-analysis-line"
        data-state="loading"
        className="flex min-h-12 items-center rounded-card bg-surface-raised px-4 py-3 shadow-card ring-1 ring-hairline"
      >
        <Skeleton className="h-4 w-2/3" />
      </div>
    );
  }

  // ---- error ----------------------------------------------------------------
  if (summaryQuery.isError) {
    return (
      <p
        role="alert"
        data-testid="latest-analysis-line"
        data-state="error"
        className="min-h-12 rounded-card bg-surface-raised px-4 py-3 text-xs leading-loose text-danger shadow-card ring-1 ring-hairline"
      >
        No se pudo cargar el estado del análisis de IA.
      </p>
    );
  }

  const summary = summaryQuery.data;

  // Sin mediciones aún: nada que analizar. El bloque resumen de `GrowthTab`
  // ya cubre este caso con su propio estado vacío; esta fila no repite un
  // segundo mensaje "sin datos" debajo de aquel.
  if (!summary || summary.records_count === 0) {
    return null;
  }

  const analysis = summary.latest_ai_analysis;
  const verdict: CriticVerdict | null = analysis?.critic_verdict ?? null;

  // Defensa en profundidad (FR-016): un veredicto bloqueado nunca debe
  // insinuarle a una familia que existe un análisis retenido, así que en
  // modo familia se trata exactamente como si no existiera análisis.
  const hiddenFromFamily = !isCoach && verdict !== null && BLOCKED_VERDICTS.has(verdict);
  const effectiveAnalysis = hiddenFromFamily ? null : analysis;

  // ---- none -----------------------------------------------------------------
  if (!effectiveAnalysis) {
    const latestRecord = records[0];
    return (
      <LineShell state="none">
        <p className="text-sm text-mid-gray">
          {isCoach
            ? "Aún no hay un análisis de IA para la medición más reciente."
            : AI_ANALYSIS_NOT_YET_AVAILABLE_MESSAGE}
        </p>
        {/* Familia: sin acción de generar y sin enlace — no hay nada que
            abrir todavía (FR-027). Coach: enlace que abre el diálogo de la
            medición más reciente, donde vive el botón real de generar. */}
        {isCoach && latestRecord && (
          <>
            <button
              type="button"
              data-testid="latest-analysis-line-link"
              onClick={() => setDialogOpen(true)}
              className="shrink-0 text-sm font-medium text-link-blue underline-offset-2 hover:underline"
            >
              Generar análisis
            </button>
            <MeasurementDialog
              open={dialogOpen}
              onOpenChange={setDialogOpen}
              athleteId={athleteId}
              record={latestRecord}
              readOnly={false}
            />
          </>
        )}
      </LineShell>
    );
  }

  const record = records.find((r) => r.id === effectiveAnalysis.record_id);
  const dateLabel = record ? formatMeasurementDate(record.evaluation_date) : null;
  const isFlagged = isCoach && verdict !== null && BLOCKED_VERDICTS.has(verdict);
  const isStale = effectiveAnalysis.is_stale;
  // "Desactualizado" y la atenuación son exclusivas de coach — en familia
  // esta misma fila se ve idéntica a "current" (data-model.md §4).
  const showStaleTreatment = isCoach && isStale;
  const state = isFlagged ? "flagged" : isStale ? "stale" : "current";

  return (
    <LineShell state={state}>
      <div className="flex min-w-0 flex-col gap-0.5">
        <p
          className={cn(
            "text-sm",
            showStaleTreatment ? "text-mid-gray" : "text-charcoal",
          )}
        >
          {effectiveAnalysis.summary_line}
        </p>
        <div className="flex flex-wrap items-center gap-2 text-xs text-mid-gray">
          {dateLabel && <span>Medición del {dateLabel}</span>}
          {showStaleTreatment && (
            <StatusBadge status="neutral" label="Desactualizado" />
          )}
        </div>
        {isFlagged && verdict && BLOCKED_VERDICTS.has(verdict) && (
          <p
            data-testid="latest-analysis-line-verdict-note"
            className="text-xs text-amber-800"
          >
            {VERDICT_NOTE[verdict as "flagged" | "fallback" | "skipped"]}
          </p>
        )}
      </div>

      {/* Sin la medición cargada todavía no hay nada que abrir — se omite
          el enlace en vez de apuntar a un diálogo vacío (FR-027). */}
      {record && (
        <>
          <button
            type="button"
            data-testid="latest-analysis-line-link"
            onClick={() => setDialogOpen(true)}
            className="shrink-0 text-sm font-medium text-link-blue underline-offset-2 hover:underline"
          >
            {isFlagged ? "Revisar análisis" : "Ver análisis completo"}
          </button>
          <MeasurementDialog
            open={dialogOpen}
            onOpenChange={setDialogOpen}
            athleteId={athleteId}
            record={record}
            readOnly={!isCoach}
          />
        </>
      )}
    </LineShell>
  );
}
