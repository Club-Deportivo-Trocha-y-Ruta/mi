import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Sparkles } from "lucide-react";

import { ConfirmDialog } from "@/components/shared/ConfirmDialog";
import { EmptyState } from "@/components/shared/EmptyState";
import { ErrorState } from "@/components/shared/ErrorState";
import { PageHeader } from "@/components/shared/PageHeader";
import { SiblingViewTabs } from "@/components/layout/SiblingViewTabs";
import { NotifyParentsDialog } from "@/components/training/NotifyParentsDialog";
import { SessionFiltersBar } from "@/components/training/SessionFiltersBar";
import { SessionsTable } from "@/components/training/SessionsTable";
import {
  useCancelTrainingSession,
  useExecuteTrainingSession,
  useTrainingSessions,
} from "@/api/trainingSessions";
import { todayISODate } from "@/lib/datetime";
import { useTrainingFiltersStore } from "@/store/trainingFiltersStore";
import type { TrainingSession } from "@/types/trainingSession.types";

// Feature 032, US3: ventana de búsqueda para el fallback "próxima sesión"
// cuando el filtro "Hoy" no tiene resultados (research.md R10).
const FALLBACK_WINDOW_DAYS = 90;

function addDaysISO(dateStr: string, days: number): string {
  const [year, month, day] = dateStr.split("-").map(Number);
  const date = new Date(Date.UTC(year, month - 1, day));
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

// R6/R10 ordering gotcha: la lista por defecto del backend viene DESC
// (fecha más lejana primero) — nunca confiar en el orden de la API para
// "próxima sesión"; siempre re-ordenar ascendente en el cliente.
function compareScheduled(a: TrainingSession, b: TrainingSession): number {
  if (a.scheduled_date !== b.scheduled_date) {
    return a.scheduled_date < b.scheduled_date ? -1 : 1;
  }
  if (a.scheduled_start_time !== b.scheduled_start_time) {
    return a.scheduled_start_time < b.scheduled_start_time ? -1 : 1;
  }
  return 0;
}

export function SessionsListPage() {
  const { from_date, to_date, status } = useTrainingFiltersStore();

  const filters = {
    from_date,
    to_date,
    ...(status ? { status } : {}),
  };

  const sessionsQuery = useTrainingSessions(filters);
  const executeMutation = useExecuteTrainingSession();
  const cancelMutation = useCancelTrainingSession();

  const [executeTarget, setExecuteTarget] = useState<TrainingSession | null>(null);
  const [cancelTarget, setCancelTarget] = useState<TrainingSession | null>(null);

  const items = sessionsQuery.data ?? [];

  // El filtro activo es exactamente "Hoy" (SessionFiltersBar's setToday()) y
  // no trajo resultados: se ofrece la próxima sesión disponible en una
  // ventana acotada hacia adelante, en vez de una lista vacía sin salida.
  const isTodayFilter = from_date === to_date && from_date === todayISODate();
  const needsFallback =
    isTodayFilter && !sessionsQuery.isLoading && !sessionsQuery.isError && items.length === 0;

  const fallbackFilters = useMemo(
    () => ({
      from_date: todayISODate(),
      to_date: addDaysISO(todayISODate(), FALLBACK_WINDOW_DAYS),
    }),
    [],
  );
  const fallbackQuery = useTrainingSessions(fallbackFilters, needsFallback);

  const fallbackSession =
    needsFallback && fallbackQuery.data && fallbackQuery.data.length > 0
      ? [...fallbackQuery.data].sort(compareScheduled)[0]
      : null;

  const isFallbackLoading = needsFallback && fallbackQuery.isLoading;
  const isFallbackError = needsFallback && fallbackQuery.isError;
  const displayItems = fallbackSession ? [fallbackSession] : items;
  const showEmptyState =
    !sessionsQuery.isLoading &&
    !sessionsQuery.isError &&
    !isFallbackLoading &&
    !isFallbackError &&
    displayItems.length === 0;

  return (
    <section className="space-y-5">
      <PageHeader
        title="Sesiones de Entrenamiento"
        subtitle="Planifica y gestiona las sesiones del club."
        actions={
          <>
            <Link
              to="/training/sessions/assistant"
              className="inline-flex min-h-[44px] items-center gap-2 rounded-lg bg-white px-4 py-2 text-sm font-medium text-charcoal transition-opacity hover:opacity-70 shadow-ring"
            >
              <Sparkles size={14} aria-hidden="true" />
              Crear con IA
            </Link>
            <Link
              to="/training/sessions/new"
              className="rounded-lg bg-charcoal px-4 py-2 text-sm font-medium text-white transition-opacity hover:opacity-70 shadow-button-highlight"
            >
              + Nueva sesión
            </Link>
          </>
        }
      />

      <SiblingViewTabs
        items={[
          { label: "Calendario", to: "/calendar" },
          { label: "Sesiones", to: "/training/sessions" },
          { label: "Actividades", to: "/activities" },
        ]}
      />

      <SessionFiltersBar />

      {sessionsQuery.isLoading && (
        <div className="space-y-2 rounded-xl bg-white p-4 shadow-ring">
          {Array.from({ length: 5 }).map((_, idx) => (
            <div key={idx} className="h-9 animate-pulse rounded-lg bg-light-gray" />
          ))}
        </div>
      )}

      {sessionsQuery.isError && (
        <ErrorState
          message="No se pudo cargar la lista de sesiones."
          onRetry={() => void sessionsQuery.refetch()}
        />
      )}

      {!sessionsQuery.isLoading && !sessionsQuery.isError && (isFallbackLoading || isFallbackError) && (
        <div className="space-y-2 rounded-xl bg-white p-4 shadow-ring">
          {isFallbackLoading &&
            Array.from({ length: 2 }).map((_, idx) => (
              <div key={idx} className="h-9 animate-pulse rounded-lg bg-light-gray" />
            ))}
          {isFallbackError && (
            <ErrorState
              message="No se pudo cargar la próxima sesión."
              onRetry={() => void fallbackQuery.refetch()}
            />
          )}
        </div>
      )}

      {showEmptyState && (
        <EmptyState
          title="No hay sesiones para los filtros seleccionados."
          action={
            <Link
              to="/training/sessions/new"
              className="inline-block text-sm font-medium text-charcoal transition-opacity hover:opacity-70"
            >
              + Crear primera sesión
            </Link>
          }
        />
      )}

      {!sessionsQuery.isLoading && !sessionsQuery.isError && !isFallbackLoading && !isFallbackError && displayItems.length > 0 && (
        <>
          {fallbackSession && (
            <p className="rounded-xl bg-white px-4 py-3 text-sm font-medium text-charcoal shadow-card">
              No hay sesión hoy — próxima sesión:
            </p>
          )}
          <SessionsTable
            items={displayItems}
            onExecute={(id) => {
              const session = displayItems.find((s) => s.id === id) ?? null;
              setExecuteTarget(session);
            }}
            onCancel={(id) => {
              const session = displayItems.find((s) => s.id === id) ?? null;
              setCancelTarget(session);
            }}
            executePendingId={executeMutation.isPending ? executeTarget?.id : null}
            cancelPendingId={cancelMutation.isPending ? cancelTarget?.id : null}
          />
        </>
      )}

      <ConfirmDialog
        open={executeTarget !== null}
        title="Marcar sesión como ejecutada"
        description="La sesión pasará al estado 'ejecutada'. Quedará registrada como realizada en el historial del club."
        confirmLabel="Marcar ejecutada"
        cancelLabel="No"
        tone="default"
        isPending={executeMutation.isPending}
        onCancel={() => setExecuteTarget(null)}
        onConfirm={() => {
          if (executeTarget) {
            executeMutation.mutate(executeTarget.id, {
              onSettled: () => setExecuteTarget(null),
            });
          }
        }}
      />

      <NotifyParentsDialog
        open={cancelTarget !== null}
        variant="cancel"
        parentCount={cancelTarget?.attendance_summary?.total ?? 0}
        isPending={cancelMutation.isPending}
        errorMessage={
          cancelMutation.isError
            ? "No se pudo cancelar la sesión. Intenta de nuevo."
            : null
        }
        onSend={(reason) => {
          if (cancelTarget) {
            cancelMutation.mutate(
              { id: cancelTarget.id, notify: true, reason },
              { onSettled: () => setCancelTarget(null) },
            );
          }
        }}
        onSkip={() => {
          if (cancelTarget) {
            cancelMutation.mutate(
              { id: cancelTarget.id, notify: false },
              { onSettled: () => setCancelTarget(null) },
            );
          }
        }}
        onCancel={() => setCancelTarget(null)}
      />
    </section>
  );
}
