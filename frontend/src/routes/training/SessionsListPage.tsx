import { useState } from "react";
import { Link } from "react-router-dom";

import { ConfirmModal } from "@/components/common/ConfirmModal";
import { ErrorState } from "@/components/shared/ErrorState";
import { NotifyParentsDialog } from "@/components/training/NotifyParentsDialog";
import { SessionFiltersBar } from "@/components/training/SessionFiltersBar";
import { SessionsTable } from "@/components/training/SessionsTable";
import {
  useCancelTrainingSession,
  useExecuteTrainingSession,
  useTrainingSessions,
} from "@/api/trainingSessions";
import { useTrainingFiltersStore } from "@/store/trainingFiltersStore";
import type { TrainingSession } from "@/types/trainingSession.types";

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

  return (
    <section className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1
            className="text-2xl text-charcoal"
            style={{ fontFamily: "'Cal Sans', system-ui, sans-serif", fontWeight: 600 }}
          >
            Sesiones de Entrenamiento
          </h1>
          <p className="mt-0.5 text-sm text-mid-gray">
            Planifica y gestiona las sesiones del club.
          </p>
        </div>
        <Link
          to="/training/sessions/new"
          className="rounded-lg bg-charcoal px-4 py-2 text-sm font-medium text-white transition-opacity hover:opacity-70"
          style={{ boxShadow: "rgba(255, 255, 255, 0.15) 0px 2px 0px inset" }}
        >
          + Nueva sesión
        </Link>
      </div>

      <SessionFiltersBar />

      {sessionsQuery.isLoading && (
        <div
          className="space-y-2 rounded-xl bg-white p-4"
          style={{ boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" }}
        >
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

      {!sessionsQuery.isLoading && !sessionsQuery.isError && items.length === 0 && (
        <div
          className="rounded-xl bg-white p-10 text-center"
          style={{
            boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px",
            borderStyle: "dashed",
          }}
        >
          <p className="text-sm text-mid-gray">
            No hay sesiones para los filtros seleccionados.
          </p>
          <Link
            to="/training/sessions/new"
            className="mt-3 inline-block text-sm font-medium text-charcoal transition-opacity hover:opacity-70"
          >
            + Crear primera sesión
          </Link>
        </div>
      )}

      {!sessionsQuery.isLoading && !sessionsQuery.isError && items.length > 0 && (
        <SessionsTable
          items={items}
          onExecute={(id) => {
            const session = items.find((s) => s.id === id) ?? null;
            setExecuteTarget(session);
          }}
          onCancel={(id) => {
            const session = items.find((s) => s.id === id) ?? null;
            setCancelTarget(session);
          }}
          executePendingId={executeMutation.isPending ? executeTarget?.id : null}
          cancelPendingId={cancelMutation.isPending ? cancelTarget?.id : null}
        />
      )}

      <ConfirmModal
        open={executeTarget !== null}
        title="Marcar sesión como ejecutada"
        body="La sesión pasará al estado 'ejecutada'. Quedará registrada como realizada en el historial del club."
        confirmLabel="Marcar ejecutada"
        cancelLabel="No"
        confirmDanger={false}
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
