import { Link } from "react-router-dom";

import { fetchTrainingSession } from "@/api/trainingSessions";
import { SessionStatusBadge } from "@/components/training/SessionStatusBadge";
import { usePrefetchOnIntent } from "@/hooks/usePrefetchOnIntent";
import { useAuthStore } from "@/store/auth.store";
import type { SessionStatus, TrainingSession } from "@/types/trainingSession.types";

interface SessionsTableProps {
  items: TrainingSession[];
  onExecute?: (id: number) => void;
  onCancel?: (id: number) => void;
  executePendingId?: number | null;
  cancelPendingId?: number | null;
}

function formatDate(dateStr: string): string {
  const [year, month, day] = dateStr.split("-");
  return `${day}/${month}/${year}`;
}

function formatTime(timeStr: string): string {
  return timeStr.slice(0, 5);
}

export function SessionsTable({
  items,
  onExecute,
  onCancel,
  executePendingId = null,
  cancelPendingId = null,
}: SessionsTableProps) {
  const prefetch = usePrefetchOnIntent();
  const userId = useAuthStore((s) => s.user?.id ?? null);
  // Feature 012, US3: al mostrar intención sobre una fila/card se prepara el
  // detalle con la misma queryKey/fn de useTrainingSession (incluye userId).
  const prefetchSession = (id: number) => () =>
    prefetch({
      queryKey: ["training-session", userId, id],
      queryFn: () => fetchTrainingSession(id),
    });
  return (
    <>
      {/* Vista mobile: cards */}
      <ul role="list" className="flex flex-col gap-3 md:hidden">
        {items.map((session) => (
          <li key={session.id}>
            <div
              className="rounded-xl bg-white p-4"
              style={{
                boxShadow:
                  "rgba(19, 19, 22, 0.7) 0px 1px 5px -4px, rgba(34, 42, 53, 0.08) 0px 0px 0px 1px, rgba(34, 42, 53, 0.05) 0px 4px 8px 0px",
              }}
              onTouchStart={prefetchSession(session.id)}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                  <p className="truncate text-base font-medium text-charcoal">
                    {session.technical_focus}
                  </p>
                  <p className="mt-0.5 text-sm text-mid-gray">
                    {formatDate(session.scheduled_date)} · {formatTime(session.scheduled_start_time)}
                  </p>
                  <p className="mt-0.5 truncate text-sm text-mid-gray">{session.location}</p>
                </div>
                <SessionStatusBadge status={session.status} />
              </div>
              {session.attendance_summary && (
                <p className="mt-2 text-xs text-mid-gray">
                  Asistencia: {session.attendance_summary.presentes}/{session.attendance_summary.total}
                </p>
              )}
              <div className="mt-3 flex flex-wrap gap-2">
                <Link
                  to={`/training/sessions/${session.id}`}
                  className="rounded-lg bg-white px-3 py-2 text-xs font-medium text-charcoal transition-opacity hover:opacity-70"
                  style={{ boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" }}
                >
                  Ver
                </Link>
                {session.status !== "cancelled" && (
                  <Link
                    to={`/training/sessions/${session.id}/edit`}
                    className="rounded-lg bg-white px-3 py-2 text-xs font-medium text-charcoal transition-opacity hover:opacity-70"
                    style={{ boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" }}
                  >
                    Editar
                  </Link>
                )}
                {session.status === "planned" && onExecute && (
                  <button
                    type="button"
                    onClick={() => onExecute(session.id)}
                    disabled={executePendingId === session.id}
                    className="rounded-lg bg-green-50 px-3 py-2 text-xs font-medium text-green-700 transition-opacity hover:opacity-70 disabled:opacity-40"
                    style={{ boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" }}
                  >
                    Ejecutar
                  </button>
                )}
                {session.status === "planned" && onCancel && (
                  <button
                    type="button"
                    onClick={() => onCancel(session.id)}
                    disabled={cancelPendingId === session.id}
                    className="rounded-lg bg-red-50 px-3 py-2 text-xs font-medium text-red-600 transition-opacity hover:opacity-70 disabled:opacity-40"
                    style={{ boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" }}
                  >
                    Cancelar
                  </button>
                )}
              </div>
            </div>
          </li>
        ))}
      </ul>

      {/* Vista desktop: tabla */}
      <div
        className="hidden overflow-x-auto rounded-xl bg-white md:block"
        style={{
          boxShadow:
            "rgba(19, 19, 22, 0.7) 0px 1px 5px -4px, rgba(34, 42, 53, 0.08) 0px 0px 0px 1px, rgba(34, 42, 53, 0.05) 0px 4px 8px 0px",
        }}
      >
        <table className="min-w-full text-sm">
          <caption className="sr-only">Lista de sesiones de entrenamiento</caption>
          <thead
            className="text-left"
            style={{ borderBottom: "1px solid rgba(34, 42, 53, 0.08)" }}
          >
            <tr>
              <th scope="col" className="px-4 py-3 text-xs font-medium uppercase tracking-wide text-mid-gray">
                Fecha
              </th>
              <th scope="col" className="px-4 py-3 text-xs font-medium uppercase tracking-wide text-mid-gray">
                Hora
              </th>
              <th scope="col" className="px-4 py-3 text-xs font-medium uppercase tracking-wide text-mid-gray">
                Foco técnico
              </th>
              <th scope="col" className="px-4 py-3 text-xs font-medium uppercase tracking-wide text-mid-gray">
                Lugar
              </th>
              <th scope="col" className="px-4 py-3 text-xs font-medium uppercase tracking-wide text-mid-gray">
                Estado
              </th>
              <th scope="col" className="px-4 py-3 text-xs font-medium uppercase tracking-wide text-mid-gray">
                Asistencia
              </th>
              <th scope="col" className="px-4 py-3 text-xs font-medium uppercase tracking-wide text-mid-gray">
                Acciones
              </th>
            </tr>
          </thead>
          <tbody>
            {items.map((session) => (
              <tr
                key={session.id}
                className="transition-colors hover:bg-light-gray"
                style={{ borderTop: "1px solid rgba(34, 42, 53, 0.06)" }}
                onMouseEnter={prefetchSession(session.id)}
              >
                <td className="px-4 py-3 text-charcoal">
                  {formatDate(session.scheduled_date)}
                </td>
                <td className="px-4 py-3 text-mid-gray">
                  {formatTime(session.scheduled_start_time)}
                </td>
                <td className="max-w-[200px] truncate px-4 py-3 font-medium text-charcoal">
                  {session.technical_focus}
                </td>
                <td className="max-w-[160px] truncate px-4 py-3 text-mid-gray">
                  {session.location}
                </td>
                <td className="px-4 py-3">
                  <SessionStatusBadge status={session.status as SessionStatus} />
                </td>
                <td className="px-4 py-3 text-mid-gray">
                  {session.attendance_summary
                    ? `${session.attendance_summary.presentes}/${session.attendance_summary.total}`
                    : "—"}
                </td>
                <td className="px-4 py-3">
                  <div className="flex gap-2">
                    <Link
                      to={`/training/sessions/${session.id}`}
                      className="rounded-lg bg-white px-3 py-1.5 text-xs font-medium text-charcoal transition-opacity hover:opacity-70"
                      style={{ boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" }}
                    >
                      Ver
                    </Link>
                    {session.status !== "cancelled" && (
                      <Link
                        to={`/training/sessions/${session.id}/edit`}
                        className="rounded-lg bg-white px-3 py-1.5 text-xs font-medium text-charcoal transition-opacity hover:opacity-70"
                        style={{ boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" }}
                      >
                        Editar
                      </Link>
                    )}
                    {session.status === "planned" && onExecute && (
                      <button
                        type="button"
                        onClick={() => onExecute(session.id)}
                        disabled={executePendingId === session.id}
                        className="rounded-lg bg-green-50 px-3 py-1.5 text-xs font-medium text-green-700 transition-opacity hover:opacity-70 disabled:opacity-40"
                        style={{ boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" }}
                      >
                        Ejecutar
                      </button>
                    )}
                    {session.status === "planned" && onCancel && (
                      <button
                        type="button"
                        onClick={() => onCancel(session.id)}
                        disabled={cancelPendingId === session.id}
                        className="rounded-lg bg-red-50 px-3 py-1.5 text-xs font-medium text-red-600 transition-opacity hover:opacity-70 disabled:opacity-40"
                        style={{ boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" }}
                      >
                        Cancelar
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
