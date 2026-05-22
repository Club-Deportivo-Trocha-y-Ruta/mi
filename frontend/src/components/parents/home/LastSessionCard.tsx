/**
 * LastSessionCard — Card "Última sesión" del home feed (Wave 4).
 *
 * Muestra la última sesión ejecutada del atleta activo. Tono de la copy:
 *   - "presente" → celebración suave ("Estuvo en el último entrenamiento").
 *   - "justificado" o "lesionado" → tono neutro factual.
 *   - "ausente" o "tarde" o sin attendance → tono neutro.
 *
 * Reglas:
 *   - Sólo renderiza si `session.status === "executed"` (el hook ya filtra,
 *     pero defensa).
 *   - Si no hay sesión ejecutada en los últimos 30 días → empty state
 *     informativo.
 */
import { Link } from "react-router-dom";
import { ArrowRight, Trophy } from "lucide-react";

import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  ATTENDANCE_LABELS,
  ATTENDANCE_TONE,
  type AttendanceStatus,
} from "@/lib/attendanceStatus";
import type {
  KidAttendance,
  TrainingSession,
} from "@/types/trainingSession.types";

interface LastSessionCardProps {
  session: TrainingSession | null | undefined;
  isLoading: boolean;
  isError?: boolean;
  /** athleteId para extraer la attendance del kid del array kid_attendances. */
  athleteId: number | null;
  athleteName?: string;
}

function formatPastDate(dateStr: string): string {
  const [y, m, d] = dateStr.split("-").map(Number);
  const target = new Date(y, m - 1, d);
  return new Intl.DateTimeFormat("es-CO", {
    weekday: "short",
    day: "numeric",
    month: "short",
  }).format(target);
}

function getAttendanceFor(
  session: TrainingSession,
  athleteId: number | null,
): KidAttendance | null {
  if (!athleteId) return null;
  return (
    session.kid_attendances?.find((a) => a.athlete_id === athleteId) ?? null
  );
}

function leadCopy(status: AttendanceStatus | null, athleteName?: string): string {
  const who = athleteName ?? "Tu atleta";
  if (status === "presente") return `${who} estuvo en el último entrenamiento`;
  if (status === "tarde") return `${who} llegó tarde al último entrenamiento`;
  if (status === "justificado")
    return `${who} no asistió (con justificación)`;
  if (status === "lesionado") return `${who} no asistió por lesión`;
  if (status === "ausente") return `${who} no asistió al último entrenamiento`;
  return "Última sesión";
}

function LoadingState() {
  return (
    <Card
      className="px-5 py-4"
      role="status"
      aria-busy="true"
      aria-label="Cargando última sesión"
    >
      <Skeleton className="mb-2 h-3 w-32" />
      <Skeleton className="mb-3 h-5 w-2/3" />
      <Skeleton className="h-4 w-1/2" />
    </Card>
  );
}

function EmptyState() {
  return (
    <Card className="flex items-start gap-3 px-5 py-5" data-testid="last-empty">
      <Trophy
        size={20}
        aria-hidden="true"
        className="mt-0.5 shrink-0 text-mid-gray"
      />
      <div>
        <p className="text-sm font-medium text-charcoal">
          Aún no hay entrenamientos completados
        </p>
        <p className="mt-1 text-sm text-mid-gray">
          Cuando el entrenador cierre una sesión, podrás ver cómo le fue aquí.
        </p>
      </div>
    </Card>
  );
}

export function LastSessionCard({
  session,
  isLoading,
  isError = false,
  athleteId,
  athleteName,
}: LastSessionCardProps) {
  if (isLoading) return <LoadingState />;
  if (isError) {
    return (
      <Card className="px-5 py-4">
        <p className="text-sm text-mid-gray">
          No fue posible cargar la última sesión.
        </p>
      </Card>
    );
  }
  if (!session) return <EmptyState />;

  const attendance = getAttendanceFor(session, athleteId);
  const status = attendance?.status ?? null;
  const isCelebratory = status === "presente";

  // Card celebratorio: solo aplicamos un *tinte* sutil — no cambiamos
  // tipografía ni colores principales. La "celebración" la transmite el
  // copy del lead, no el fondo. Esto respeta el reset visual de Wave 3.
  const accentClass = isCelebratory
    ? "border-l-4 border-l-green-400"
    : "border-l-4 border-l-light-gray";

  return (
    <Card
      data-testid="last-session-card"
      className={`overflow-hidden ${accentClass}`}
    >
      <Link
        to={`/parents/training/sessions/${session.id}`}
        aria-label={`Ver detalle de la última sesión: ${session.technical_focus}`}
        className="flex items-start gap-3 px-5 py-4 transition-colors hover:bg-light-gray/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40"
      >
        <Trophy
          size={22}
          aria-hidden="true"
          className={isCelebratory ? "mt-0.5 shrink-0 text-green-600" : "mt-0.5 shrink-0 text-primary"}
        />
        <div className="min-w-0 flex-1">
          <p className="text-xs font-medium uppercase tracking-wide text-mid-gray">
            Última sesión
          </p>
          <p className="mt-0.5 text-sm text-charcoal">{leadCopy(status, athleteName)}</p>
          <p className="mt-1 truncate text-base font-semibold text-charcoal">
            {session.technical_focus}
          </p>
          <p className="text-sm text-mid-gray">{formatPastDate(session.scheduled_date)}</p>
          {status && (
            <span
              className={`mt-2 inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${ATTENDANCE_TONE[status]}`}
              aria-label={`Asistencia: ${ATTENDANCE_LABELS[status]}`}
            >
              {ATTENDANCE_LABELS[status]}
            </span>
          )}
        </div>
        <span className="mt-1 inline-flex items-center gap-1 text-xs font-medium text-link-blue">
          Ver detalle
          <ArrowRight size={12} aria-hidden="true" />
        </span>
      </Link>
    </Card>
  );
}
