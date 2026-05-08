import { Link } from "react-router-dom";
import { ArrowRight } from "lucide-react";

import { SessionStatusBadge } from "@/components/training/SessionStatusBadge";
import type { AttendanceStatus, TrainingSession } from "@/types/trainingSession.types";

interface ParentSessionCardProps {
  session: TrainingSession;
  kidAttendanceStatus?: AttendanceStatus | null;
}

const CARD_SHADOW =
  "rgba(19, 19, 22, 0.7) 0px 1px 5px -4px, rgba(34, 42, 53, 0.08) 0px 0px 0px 1px, rgba(34, 42, 53, 0.05) 0px 4px 8px 0px";

const ATTENDANCE_CONFIG: Record<
  AttendanceStatus,
  { label: string; className: string }
> = {
  presente: { label: "Presente", className: "bg-green-100 text-green-800" },
  tarde: { label: "Tarde", className: "bg-amber-100 text-amber-800" },
  ausente: { label: "Ausente", className: "bg-red-100 text-red-700" },
  justificado: { label: "Justificado", className: "bg-blue-100 text-blue-800" },
  lesionado: { label: "Lesionado", className: "bg-purple-100 text-purple-800" },
};

function formatDate(dateStr: string): string {
  const [year, month, day] = dateStr.split("-");
  const date = new Date(Number(year), Number(month) - 1, Number(day));
  return new Intl.DateTimeFormat("es-CO", {
    weekday: "short",
    day: "numeric",
    month: "short",
  }).format(date);
}

function formatTime(timeStr: string): string {
  return timeStr.slice(0, 5);
}

export function ParentSessionCard({ session, kidAttendanceStatus }: ParentSessionCardProps) {
  const attendanceBadge = kidAttendanceStatus
    ? ATTENDANCE_CONFIG[kidAttendanceStatus]
    : null;

  return (
    <Link
      to={`/parents/training/sessions/${session.id}`}
      className="flex flex-col rounded-xl bg-white transition-shadow hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500/30"
      style={{ boxShadow: CARD_SHADOW }}
      aria-label={`Ver sesión: ${session.technical_focus} del ${formatDate(session.scheduled_date)}`}
      data-testid="parent-session-card"
    >
      <div className="flex items-start justify-between px-4 pt-4 pb-3 gap-3">
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

      <div
        className="flex items-center justify-end px-4 py-2.5 gap-2"
        style={{ borderTop: "1px solid rgba(34, 42, 53, 0.06)" }}
      >
        {attendanceBadge && (
          <span
            className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${attendanceBadge.className}`}
            aria-label={`Asistencia de tu atleta: ${attendanceBadge.label}`}
          >
            {attendanceBadge.label}
          </span>
        )}
        <ArrowRight size={14} className="text-mid-gray" aria-hidden="true" />
      </div>
    </Link>
  );
}
