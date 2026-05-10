import { Link, useParams } from "react-router-dom";
import { MapPin, Clock, CalendarDays, ArrowLeft } from "lucide-react";

import { EventTypeChip } from "@/components/calendar/EventTypeChip";
import { ParentRSVPInline } from "@/components/parents/ParentRSVPInline";
import { useCalendarEvent, useEventAttendances } from "@/api/calendar";
import { useMyAthletes } from "@/hooks/parents/useMyAthletes";
import type { MyAthleteOut } from "@/types/parent.types";
import type { EventAttendanceRead, RSVPStatus } from "@/types/calendar.types";

const CARD_SHADOW =
  "rgba(19, 19, 22, 0.7) 0px 1px 5px -4px, rgba(34, 42, 53, 0.08) 0px 0px 0px 1px, rgba(34, 42, 53, 0.05) 0px 4px 8px 0px";

// ─── Helpers ──────────────────────────────────────────────────────────────────

function formatFullDate(iso: string): string {
  return new Intl.DateTimeFormat("es-CO", {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
    timeZone: "America/Bogota",
  }).format(new Date(iso));
}

function formatTime(iso: string): string {
  return new Intl.DateTimeFormat("es-CO", {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "America/Bogota",
  }).format(new Date(iso));
}

function durationLabel(startIso: string, endIso: string): string {
  const diffMs = new Date(endIso).getTime() - new Date(startIso).getTime();
  const totalMin = Math.round(diffMs / 60_000);
  if (totalMin < 60) return `${totalMin} min`;
  const h = Math.floor(totalMin / 60);
  const m = totalMin % 60;
  return m === 0 ? `${h} h` : `${h} h ${m} min`;
}

const STATUS_LABELS: Record<string, string> = {
  scheduled: "Programado",
  confirmed: "Confirmado",
  cancelled: "Cancelado",
  completed: "Completado",
};

const RSVP_LABELS: Record<RSVPStatus, { label: string; classes: string }> = {
  pending: { label: "Pendiente", classes: "bg-gray-100 text-gray-600" },
  accepted: { label: "Aceptado", classes: "bg-green-100 text-green-700" },
  declined: { label: "Rechazado", classes: "bg-red-100 text-red-700" },
  tentative: { label: "Tentativo", classes: "bg-amber-100 text-amber-700" },
};

function SkeletonCard() {
  return (
    <div className="rounded-xl bg-white p-5 space-y-3" style={{ boxShadow: CARD_SHADOW }}>
      {[...Array(4)].map((_, i) => (
        <div
          key={i}
          className="h-4 animate-pulse rounded bg-light-gray"
          style={{ width: `${75 - i * 12}%` }}
        />
      ))}
    </div>
  );
}

// ─── Athlete section ──────────────────────────────────────────────────────────

interface AthleteDetailSectionProps {
  athlete: MyAthleteOut;
  attendance: EventAttendanceRead | undefined;
  eventId: number;
  isTrainingSession: boolean;
  trainingSessionId?: number;
  isCancelledOrPast: boolean;
}

function AthleteDetailSection({
  athlete,
  attendance,
  eventId,
  isTrainingSession,
  trainingSessionId,
  isCancelledOrPast,
}: AthleteDetailSectionProps) {
  const name = `${athlete.athlete_first_name} ${athlete.athlete_last_name}`;

  if (isTrainingSession) {
    return (
      <div className="space-y-1.5">
        <p className="text-sm font-medium text-charcoal">{name}</p>
        {trainingSessionId ? (
          <Link
            to={`/parents/training/sessions/${trainingSessionId}`}
            className="inline-flex items-center gap-1 text-sm text-mid-gray underline-offset-2 hover:underline"
          >
            Ver detalle del entrenamiento →
          </Link>
        ) : (
          <p className="text-xs text-mid-gray">
            Estado de asistencia disponible en el detalle del entrenamiento.
          </p>
        )}
      </div>
    );
  }

  const currentRSVP: RSVPStatus = attendance?.rsvp_status ?? "pending";
  const rsvpConfig = RSVP_LABELS[currentRSVP];

  return (
    <div className="space-y-3" data-testid={`athlete-section-${athlete.athlete_id}`}>
      <div className="flex items-center justify-between gap-2">
        <p className="text-sm font-medium text-charcoal">{name}</p>
        <span
          className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${rsvpConfig.classes}`}
          data-testid={`rsvp-badge-${athlete.athlete_id}`}
        >
          {rsvpConfig.label}
        </span>
      </div>
      {!isCancelledOrPast && (
        <ParentRSVPInline
          eventId={eventId}
          athleteId={athlete.athlete_id}
          currentRSVP={currentRSVP}
          disabled={isCancelledOrPast}
        />
      )}
    </div>
  );
}

// ─── Main page ────────────────────────────────────────────────────────────────

export function ParentEventDetailPage() {
  const { id } = useParams<{ id: string }>();
  const eventId = Number(id);

  const eventQuery = useCalendarEvent(eventId);
  const athletesQuery = useMyAthletes();

  const event = eventQuery.data;
  const myAthletes: MyAthleteOut[] = athletesQuery.data ?? [];
  const myAthleteIds = new Set(myAthletes.map((a) => a.athlete_id));

  const isLoading = eventQuery.isLoading || athletesQuery.isLoading;

  const isTrainingSession = event?.event_type === "training_session";

  // Fetch attendances only for non-training events (training uses session_attendance).
  const attendancesQuery = useEventAttendances(
    event != null && !isTrainingSession ? eventId : null,
    event?.event_type ?? "club_event",
  );
  const myAttendances = (attendancesQuery.data ?? []).filter((a) =>
    myAthleteIds.has(a.athlete_id),
  );
  const trainingSessionId =
    isTrainingSession &&
    event?.event_data != null &&
    "training_session_id" in event.event_data
      ? (event.event_data as { training_session_id?: number }).training_session_id
      : undefined;

  const now = new Date();
  const isCancelledOrPast =
    event?.status === "cancelled" ||
    (event != null && new Date(event.start) < now);

  if (isLoading) {
    return (
      <section className="space-y-4">
        <div className="h-4 w-28 animate-pulse rounded bg-light-gray" />
        <SkeletonCard />
        <SkeletonCard />
      </section>
    );
  }

  if (eventQuery.isError || !event) {
    return (
      <section className="space-y-4">
        <Link
          to="/parents/calendar"
          className="flex w-fit items-center gap-1 text-sm font-medium text-mid-gray hover:text-charcoal"
        >
          <ArrowLeft size={14} aria-hidden="true" />
          Calendario
        </Link>
        <div className="rounded-xl bg-white p-8 text-center" style={{ boxShadow: CARD_SHADOW }}>
          <p className="text-base font-medium text-charcoal">Evento no encontrado</p>
          <p className="mt-1 text-sm text-mid-gray">
            El evento no existe o no tienes acceso a él.
          </p>
        </div>
      </section>
    );
  }

  return (
    <section className="space-y-5">
      {/* Breadcrumb */}
      <nav aria-label="Ruta de navegación">
        <Link
          to="/parents/calendar"
          className="flex w-fit items-center gap-1 text-sm font-medium text-mid-gray hover:text-charcoal"
        >
          <ArrowLeft size={14} aria-hidden="true" />
          Calendario
        </Link>
        <p className="mt-1 text-xs text-mid-gray" aria-hidden="true">
          Calendario / {event.title}
        </p>
      </nav>

      {/* Header del evento */}
      <div
        className="rounded-xl bg-white px-5 py-4 space-y-2"
        style={{ boxShadow: CARD_SHADOW }}
        data-testid="event-header"
      >
        <div className="flex flex-wrap items-center gap-2">
          <h1
            className="text-xl text-charcoal"
            style={{ fontFamily: "'Cal Sans', system-ui, sans-serif", fontWeight: 600 }}
          >
            {event.title}
          </h1>
          <EventTypeChip eventType={event.event_type} />
          <span className="rounded-full bg-gray-100 px-2.5 py-0.5 text-xs font-medium text-gray-600">
            {STATUS_LABELS[event.status] ?? event.status}
          </span>
        </div>
      </div>

      {/* Fecha y hora */}
      <div
        className="rounded-xl bg-white px-5 py-4 space-y-3 text-sm"
        style={{ boxShadow: CARD_SHADOW }}
      >
        <h2 className="text-xs font-semibold uppercase tracking-wide text-mid-gray mb-2">
          Fecha y hora
        </h2>

        <div className="flex items-start gap-2">
          <CalendarDays size={14} className="mt-0.5 shrink-0 text-mid-gray" aria-hidden="true" />
          <p className="font-medium capitalize text-charcoal">{formatFullDate(event.start)}</p>
        </div>

        {!event.allDay && (
          <div className="flex items-center gap-2 pl-5">
            <Clock size={13} className="shrink-0 text-mid-gray" aria-hidden="true" />
            <span className="text-mid-gray">
              {formatTime(event.start)} — {formatTime(event.end)} ({durationLabel(event.start, event.end)})
            </span>
          </div>
        )}

        {event.allDay && (
          <p className="pl-5 text-mid-gray">Todo el día</p>
        )}

        {event.location && (
          <div className="flex items-start gap-2">
            <MapPin size={14} className="mt-0.5 shrink-0 text-mid-gray" aria-hidden="true" />
            <p className="text-charcoal">{event.location}</p>
          </div>
        )}
      </div>

      {/* Descripción */}
      {event.description && (
        <div
          className="rounded-xl bg-white px-5 py-4"
          style={{ boxShadow: CARD_SHADOW }}
        >
          <h2 className="text-xs font-semibold uppercase tracking-wide text-mid-gray mb-2">
            Descripción
          </h2>
          <p
            className="whitespace-pre-wrap text-sm text-charcoal"
            data-testid="event-description"
          >
            {event.description}
          </p>
        </div>
      )}

      {/* Estado de mis atletas */}
      {myAthletes.length > 0 && (
        <div
          className="rounded-xl bg-white px-5 py-4 space-y-4"
          style={{ boxShadow: CARD_SHADOW }}
          data-testid="my-athletes-section"
        >
          <h2 className="text-xs font-semibold uppercase tracking-wide text-mid-gray">
            Estado de tu{myAthletes.length > 1 ? "s atletas" : " atleta"}
          </h2>
          {myAthletes.map((athlete) => {
            const attendance = myAttendances.find(
              (a) => a.athlete_id === athlete.athlete_id,
            );
            return (
              <AthleteDetailSection
                key={athlete.athlete_id}
                athlete={athlete}
                attendance={attendance}
                eventId={event.id}
                isTrainingSession={isTrainingSession}
                trainingSessionId={trainingSessionId}
                isCancelledOrPast={isCancelledOrPast}
              />
            );
          })}
        </div>
      )}
    </section>
  );
}
