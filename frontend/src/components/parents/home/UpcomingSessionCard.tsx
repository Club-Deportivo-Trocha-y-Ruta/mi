/**
 * UpcomingSessionCard — Card "Próximo entrenamiento" del home feed (Wave 4).
 *
 * Estados:
 *   - loading: skeleton accesible (un solo `role="status"` por sección — el
 *     consumidor envuelve si renderiza varios cards en paralelo).
 *   - error: mensaje neutro, no expone detalle técnico.
 *   - empty (no hay próxima sesión): copy pedagógico — no hay drama,
 *     puede pasar tras semanas de descanso o vacaciones.
 *   - con sesión: fecha relativa cuando es cercana ("Mañana 4 pm"), fecha
 *     absoluta cuando >7 días. Foco técnico, lugar, link "Ver detalle".
 */
import { Link } from "react-router-dom";
import { ArrowRight, CalendarClock } from "lucide-react";

import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import type { TrainingSession } from "@/types/trainingSession.types";

interface UpcomingSessionCardProps {
  session: TrainingSession | null | undefined;
  isLoading: boolean;
  isError?: boolean;
  /** Nombre del atleta para incluir en el aria-label del link. Útil cuando el
   *  home apila cards por hijo (multi-atleta sin selección). */
  athleteName?: string;
}

function pad2(n: number): string {
  return String(n).padStart(2, "0");
}

function startOfDay(d: Date): Date {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate());
}

function diffInDays(target: Date, ref: Date): number {
  const ms = startOfDay(target).getTime() - startOfDay(ref).getTime();
  return Math.round(ms / (1000 * 60 * 60 * 24));
}

function formatTime12h(timeStr: string): string {
  const [hStr, mStr] = timeStr.split(":");
  const h = Number(hStr);
  const m = Number(mStr);
  const period = h >= 12 ? "pm" : "am";
  const display = h % 12 === 0 ? 12 : h % 12;
  return m === 0 ? `${display} ${period}` : `${display}:${pad2(m)} ${period}`;
}

function formatRelativeDate(session: TrainingSession): string {
  const [y, mo, d] = session.scheduled_date.split("-").map(Number);
  const target = new Date(y, mo - 1, d);
  const now = new Date();
  const days = diffInDays(target, now);
  const time = formatTime12h(session.scheduled_start_time);

  if (days === 0) return `Hoy ${time}`;
  if (days === 1) return `Mañana ${time}`;
  if (days > 1 && days < 7) {
    const weekday = new Intl.DateTimeFormat("es-CO", {
      weekday: "long",
    }).format(target);
    return `${weekday} ${time}`;
  }
  const fullDate = new Intl.DateTimeFormat("es-CO", {
    weekday: "short",
    day: "numeric",
    month: "short",
  }).format(target);
  return `${fullDate} · ${time}`;
}

function LoadingState() {
  return (
    <Card
      className="px-5 py-4"
      role="status"
      aria-busy="true"
      aria-label="Cargando próximo entrenamiento"
    >
      <Skeleton className="mb-2 h-3 w-32" />
      <Skeleton className="mb-3 h-5 w-2/3" />
      <Skeleton className="h-4 w-1/2" />
    </Card>
  );
}

function EmptyState() {
  return (
    <Card className="flex items-start gap-3 px-5 py-5" data-testid="upcoming-empty">
      <CalendarClock
        size={20}
        aria-hidden="true"
        className="mt-0.5 shrink-0 text-mid-gray"
      />
      <div>
        <p className="text-sm font-medium text-charcoal">
          No hay entrenamientos programados
        </p>
        <p className="mt-1 text-sm text-mid-gray">
          Cuando el entrenador planifique el próximo lo verás aquí.
        </p>
      </div>
    </Card>
  );
}

export function UpcomingSessionCard({
  session,
  isLoading,
  isError = false,
  athleteName,
}: UpcomingSessionCardProps) {
  if (isLoading) return <LoadingState />;
  if (isError) {
    return (
      <Card className="px-5 py-4">
        <p className="text-sm text-mid-gray">
          No fue posible cargar el próximo entrenamiento.
        </p>
      </Card>
    );
  }
  if (!session) return <EmptyState />;

  const relative = formatRelativeDate(session);
  const labelSuffix = athleteName ? ` de ${athleteName}` : "";

  return (
    <Card data-testid="upcoming-session-card" className="overflow-hidden">
      <Link
        to={`/parents/training/sessions/${session.id}`}
        aria-label={`Ver próximo entrenamiento${labelSuffix}: ${session.technical_focus}`}
        className="flex items-start gap-3 px-5 py-4 transition-colors hover:bg-light-gray/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40"
      >
        <CalendarClock
          size={22}
          aria-hidden="true"
          className="mt-0.5 shrink-0 text-primary"
        />
        <div className="min-w-0 flex-1">
          <p className="text-xs font-medium uppercase tracking-wide text-mid-gray">
            Próximo entrenamiento
          </p>
          <p className="mt-0.5 truncate text-base font-semibold text-charcoal">
            {session.technical_focus}
          </p>
          <p className="mt-0.5 text-sm text-charcoal">{relative}</p>
          {session.location && (
            <p className="truncate text-sm text-mid-gray">{session.location}</p>
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
