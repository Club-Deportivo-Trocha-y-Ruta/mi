import { Link } from "react-router-dom";
import { MapPin, Clock, CalendarDays, ArrowRight } from "lucide-react";

import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
  SheetBody,
  SheetFooter,
} from "@/components/ui/sheet";
import { EventTypeChip } from "@/components/calendar/EventTypeChip";
import { ParentRSVPInline } from "./ParentRSVPInline";
import { useCalendarEvent, useEventAttendances } from "@/api/calendar";
import { useMyAthletes } from "@/hooks/parents/useMyAthletes";
import type { MyAthleteOut } from "@/types/parent.types";
import type { EventAttendanceRead, RSVPStatus } from "@/types/calendar.types";

interface ParentEventDrawerProps {
  eventId: number | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Optional pre-fetched attendances for the current parent's athletes */
  myAttendances?: EventAttendanceRead[];
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function formatFullDate(iso: string): string {
  const date = new Date(iso);
  return new Intl.DateTimeFormat("es-CO", {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
    timeZone: "America/Bogota",
  }).format(date);
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

// ─── Athlete row inside drawer ────────────────────────────────────────────────

const RSVP_LABELS: Record<RSVPStatus, { label: string; classes: string }> = {
  pending: { label: "Pendiente", classes: "bg-gray-100 text-gray-600" },
  accepted: { label: "Aceptado", classes: "bg-green-100 text-green-700" },
  declined: { label: "Rechazado", classes: "bg-red-100 text-red-700" },
  tentative: { label: "Tentativo", classes: "bg-amber-100 text-amber-700" },
};

interface AthleteRSVPSectionProps {
  athlete: MyAthleteOut;
  attendance: EventAttendanceRead | undefined;
  eventId: number;
  isTrainingSession: boolean;
  trainingSessionId?: number;
  isCancelledOrPast: boolean;
}

function AthleteRSVPSection({
  athlete,
  attendance,
  eventId,
  isTrainingSession,
  trainingSessionId,
  isCancelledOrPast,
}: AthleteRSVPSectionProps) {
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
            Ver detalle del entrenamiento
            <ArrowRight size={12} aria-hidden="true" />
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
    <div className="space-y-3">
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

// ─── Main component ───────────────────────────────────────────────────────────

export function ParentEventDrawer({
  eventId,
  open,
  onOpenChange,
  myAttendances = [],
}: ParentEventDrawerProps) {
  const athletesQuery = useMyAthletes();
  const eventQuery = useCalendarEvent(eventId);

  const event = eventQuery.data;
  const myAthletes: MyAthleteOut[] = athletesQuery.data ?? [];
  const myAthleteIds = new Set(myAthletes.map((a) => a.athlete_id));

  const isLoading = eventQuery.isLoading || athletesQuery.isLoading;

  const isTrainingSession = event?.event_type === "training_session";

  // Fetch attendances internally only when caller didn't provide them and the
  // event is a non-training type that supports RSVP. Disabled otherwise.
  const shouldFetchAttendances =
    myAttendances.length === 0 && event != null && !isTrainingSession;
  const attendancesQuery = useEventAttendances(
    shouldFetchAttendances ? eventId : null,
    event?.event_type ?? "club_event",
  );
  const effectiveAttendances =
    myAttendances.length > 0 ? myAttendances : attendancesQuery.data ?? [];
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

  // Filter attendances to ONLY those belonging to this parent's athletes.
  // This is a defensive client-side guard — the backend already scopes data,
  // but we never render another athlete's RSVP under any circumstances.
  const myFilteredAttendances = effectiveAttendances.filter((a) =>
    myAthleteIds.has(a.athlete_id),
  );

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" aria-label="Detalle del evento">
        {/* ── Header ── */}
        <SheetHeader>
          {isLoading ? (
            <div className="space-y-2">
              <div className="h-4 w-3/4 animate-pulse rounded bg-light-gray" />
              <div className="h-3 w-1/2 animate-pulse rounded bg-light-gray" />
            </div>
          ) : event ? (
            <>
              <SheetTitle data-testid="drawer-title">{event.title}</SheetTitle>
              <SheetDescription asChild>
                <div className="flex items-center gap-2">
                  <EventTypeChip eventType={event.event_type} />
                  <span className="text-xs text-mid-gray">
                    {STATUS_LABELS[event.status] ?? event.status}
                  </span>
                </div>
              </SheetDescription>
            </>
          ) : (
            <SheetTitle>Evento</SheetTitle>
          )}
        </SheetHeader>

        {/* ── Body ── */}
        <SheetBody>
          {isLoading && (
            <div className="space-y-3">
              {Array.from({ length: 5 }).map((_, i) => (
                <div
                  key={i}
                  className="h-4 animate-pulse rounded bg-light-gray"
                  style={{ width: `${55 + i * 9}%` }}
                />
              ))}
            </div>
          )}

          {eventQuery.isError && (
            <p className="text-sm text-red-600" role="alert">
              No se pudo cargar el detalle del evento.
            </p>
          )}

          {event && (
            <div className="space-y-5 text-sm">
              {/* Fecha y hora */}
              <div className="space-y-1.5">
                <div className="flex items-start gap-2">
                  <CalendarDays
                    size={14}
                    className="mt-0.5 shrink-0 text-mid-gray"
                    aria-hidden="true"
                  />
                  <div>
                    <p className="font-medium capitalize text-charcoal">
                      {formatFullDate(event.start)}
                    </p>
                    {!event.allDay && (
                      <p className="text-mid-gray">
                        {formatTime(event.start)} — {formatTime(event.end)}
                      </p>
                    )}
                    {event.allDay && (
                      <p className="text-mid-gray">Todo el día</p>
                    )}
                  </div>
                </div>

                {!event.allDay && (
                  <div className="flex items-center gap-2 pl-5">
                    <Clock
                      size={13}
                      className="shrink-0 text-mid-gray"
                      aria-hidden="true"
                    />
                    <span className="text-mid-gray">
                      Duración: {durationLabel(event.start, event.end)}
                    </span>
                  </div>
                )}
              </div>

              {/* Lugar */}
              {event.location && (
                <div className="flex items-start gap-2">
                  <MapPin
                    size={14}
                    className="mt-0.5 shrink-0 text-mid-gray"
                    aria-hidden="true"
                  />
                  <p className="text-charcoal">{event.location}</p>
                </div>
              )}

              {/* Descripción */}
              {event.description && (
                <div>
                  <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-mid-gray">
                    Descripción
                  </p>
                  <p
                    className="whitespace-pre-wrap text-charcoal"
                    data-testid="drawer-description"
                  >
                    {event.description}
                  </p>
                </div>
              )}

              {/* Estado de mis hijos — sección principal de privacidad */}
              {myAthletes.length > 0 && (
                <div
                  className="space-y-4 rounded-xl border border-[rgba(34,42,53,0.08)] p-4"
                  data-testid="my-athletes-section"
                >
                  <p className="text-xs font-semibold uppercase tracking-wide text-mid-gray">
                    Estado de tu{myAthletes.length > 1 ? "s atletas" : " atleta"}
                  </p>
                  {myAthletes.map((athlete) => {
                    const attendance = myFilteredAttendances.find(
                      (a) => a.athlete_id === athlete.athlete_id,
                    );
                    return (
                      <AthleteRSVPSection
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
            </div>
          )}
        </SheetBody>

        {/* ── Footer ── */}
        {event && (
          <SheetFooter>
            <Link
              to={`/parents/calendar/events/${event.id}`}
              onClick={() => onOpenChange(false)}
              className="inline-flex items-center gap-1.5 rounded-lg bg-charcoal px-4 py-2 text-sm font-medium text-white transition-opacity hover:opacity-70"
              style={{
                boxShadow: "rgba(255, 255, 255, 0.15) 0px 2px 0px inset",
              }}
              data-testid="view-detail-link"
            >
              Ver detalle completo
              <ArrowRight size={14} aria-hidden="true" />
            </Link>
          </SheetFooter>
        )}
      </SheetContent>
    </Sheet>
  );
}
