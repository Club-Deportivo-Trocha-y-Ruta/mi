/**
 * ActivityMatchPage — vista de detalle de la comparación plan-vs-real de una
 * sesión (feature 026, US2 / FR-017). Ruta lazy, solo coach/admin.
 *
 * Ruta: /training/sessions/:id/activity-match/:activityId
 *
 * Consume `useSessionMatch` (que re-consulta cada 3 s mientras el job diferido
 * está en `computing`) y renderiza los cuatro estados de UI del contrato — todos
 * `200`, ninguno es un error crudo:
 *   - `no_activity`  → estado vacío ("aún no hay actividad enlazada").
 *   - `computing`    → spinner ("calculando comparación…"); el hook refresca solo.
 *   - `failed`       → estado de fallo con botón de reintento (recálculo manual).
 *   - `computed`     → encabezado de la actividad + `PlanVsActualTable`.
 *
 * El error de red/carga (query.isError) y el 403/404 se cubren aparte con su
 * propio estado + reintento (refetch).
 */

import { Link, useParams } from "react-router-dom";
import { AlertTriangle, ArrowLeft, Loader2, LinkIcon } from "lucide-react";

import { PlanVsActualTable } from "@/components/intervals/PlanVsActualTable";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useRecalculateMatch, useSessionMatch } from "@/hooks/intervals/useIntervals";
import { formatDateTime } from "@/lib/datetime";

/** Segundos → "h:mm:ss" o "m:ss" para el tiempo total de la actividad. */
function formatElapsed(seconds: number): string {
  const total = Math.round(seconds);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const pad = (n: number) => String(n).padStart(2, "0");
  return h > 0 ? `${h}:${pad(m)}:${pad(s)}` : `${m}:${pad(s)}`;
}

function BackLink({ sessionId }: { sessionId: number }) {
  return (
    <Link
      // feature 032 / T036: la comparación plan-vs-real solo se llega desde el
      // enlace "Ver comparación plan vs. real" de la sección Plan — volver
      // debe aterrizar ahí, no en la sección default.
      to={`/training/sessions/${sessionId}?section=plan`}
      className="inline-flex items-center gap-1.5 text-sm font-medium text-charcoal transition-opacity hover:opacity-70"
    >
      <ArrowLeft size={16} aria-hidden="true" />
      Volver a la sesión
    </Link>
  );
}

export function ActivityMatchPage() {
  const params = useParams();
  const sessionId = Number(params.id);
  const activityId = params.activityId ? Number(params.activityId) : undefined;

  const matchQuery = useSessionMatch(sessionId, activityId);
  const recalcMutation = useRecalculateMatch();

  const match = matchQuery.data;

  const handleRetry = () => {
    if (!match) return;
    recalcMutation.mutate({
      structureId: match.structure_id,
      trainingSessionId: sessionId,
      input: activityId ? { activity_id: activityId } : undefined,
    });
  };

  // --- Carga inicial ------------------------------------------------------
  if (matchQuery.isLoading) {
    return (
      <section className="space-y-5">
        <BackLink sessionId={sessionId} />
        <div className="rounded-xl bg-white p-5 space-y-3 shadow-card">
          <Skeleton className="h-6 w-1/3 rounded" />
          <Skeleton className="h-40 w-full rounded" />
        </div>
      </section>
    );
  }

  // --- Error de red / 403 / 404 ------------------------------------------
  if (matchQuery.isError || !match) {
    return (
      <section className="space-y-5">
        <BackLink sessionId={sessionId} />
        <div
          className="rounded-xl bg-white p-8 text-center shadow-card"
          role="alert"
        >
          <p className="text-base font-medium text-charcoal">
            No se pudo cargar la comparación
          </p>
          <p className="mt-1 text-sm text-mid-gray">
            Ocurrió un problema al obtener el detalle. Puede que no tengas
            permiso o que la sesión no exista.
          </p>
          <Button
            variant="outline"
            className="mt-4"
            onClick={() => void matchQuery.refetch()}
            disabled={matchQuery.isFetching}
          >
            {matchQuery.isFetching && (
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
            )}
            Reintentar
          </Button>
        </div>
      </section>
    );
  }

  return (
    <section className="space-y-5">
      <BackLink sessionId={sessionId} />

      <div className="rounded-xl bg-white px-5 py-4 shadow-card">
        <h1
          className="font-display text-xl text-charcoal"
        >
          Comparación plan vs. real
        </h1>
        {match.status === "computed" && match.activity && (
          <p className="mt-1 text-sm text-mid-gray">
            {match.activity.sport_type} ·{" "}
            {formatDateTime(match.activity.start_date_local)} ·{" "}
            {formatElapsed(match.activity.elapsed_time_s)}
            {match.computed_at && (
              <> · Calculado el {formatDateTime(match.computed_at)}</>
            )}
          </p>
        )}
      </div>

      {/* Estado: sin actividad enlazada -------------------------------- */}
      {match.status === "no_activity" && (
        <div
          className="rounded-xl bg-white p-8 text-center shadow-card"
          data-testid="match-no-activity"
        >
          <LinkIcon
            className="mx-auto h-8 w-8 text-mid-gray"
            aria-hidden="true"
          />
          <p className="mt-3 text-base font-medium text-charcoal">
            Aún no hay una actividad enlazada
          </p>
          <p className="mt-1 text-sm text-mid-gray">
            Enlazá una actividad de Strava a esta sesión para ver la comparación
            entre el plan y lo que efectivamente se hizo.
          </p>
          <div className="mt-4">
            <BackLink sessionId={sessionId} />
          </div>
        </div>
      )}

      {/* Estado: cálculo en curso -------------------------------------- */}
      {match.status === "computing" && (
        <div
          className="rounded-xl bg-white p-8 text-center shadow-card"
          role="status"
          aria-live="polite"
          data-testid="match-computing"
        >
          <Loader2
            className="mx-auto h-8 w-8 animate-spin text-mid-gray"
            aria-hidden="true"
          />
          <p className="mt-3 text-base font-medium text-charcoal">
            Calculando comparación…
          </p>
          <p className="mt-1 text-sm text-mid-gray">
            Estamos trayendo las vueltas de la actividad y comparándolas con el
            plan. Esto se actualiza solo en unos segundos.
          </p>
        </div>
      )}

      {/* Estado: fallo del último cálculo ------------------------------ */}
      {match.status === "failed" && (
        <div
          className="rounded-xl bg-white p-8 text-center shadow-card"
          role="alert"
          data-testid="match-failed"
        >
          <AlertTriangle
            className="mx-auto h-8 w-8 text-amber-600"
            aria-hidden="true"
          />
          <p className="mt-3 text-base font-medium text-charcoal">
            No se pudo calcular la comparación
          </p>
          <p className="mt-1 text-sm text-mid-gray">
            El último intento falló (por ejemplo, Strava no respondió a tiempo).
            Podés volver a intentarlo.
          </p>
          {match.retry_available !== false && (
            <Button
              className="mt-4"
              onClick={handleRetry}
              disabled={recalcMutation.isPending}
              data-testid="match-retry-button"
            >
              {recalcMutation.isPending && (
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
              )}
              Reintentar cálculo
            </Button>
          )}
          {recalcMutation.isError && (
            <p className="mt-3 text-sm text-red-600" role="alert">
              No se pudo iniciar el recálculo. Intentá de nuevo en un momento.
            </p>
          )}
        </div>
      )}

      {/* Estado: comparación lista ------------------------------------- */}
      {match.status === "computed" && (
        <div className="rounded-xl bg-white px-5 py-4 space-y-4 shadow-card">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-mid-gray">
              Bloques vs. vueltas
            </h2>
            <Button
              variant="outline"
              size="sm"
              onClick={handleRetry}
              disabled={recalcMutation.isPending}
              data-testid="match-recalculate-button"
            >
              {recalcMutation.isPending && (
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
              )}
              Recalcular
            </Button>
          </div>

          <PlanVsActualTable
            blocks={match.blocks ?? []}
            extraLaps={match.extra_laps ?? []}
            summary={match.summary}
            tolerancePct={match.tolerance_pct}
          />

          {recalcMutation.isError && (
            <p className="text-sm text-red-600" role="alert">
              No se pudo iniciar el recálculo. Intentá de nuevo en un momento.
            </p>
          )}
        </div>
      )}
    </section>
  );
}

export default ActivityMatchPage;
