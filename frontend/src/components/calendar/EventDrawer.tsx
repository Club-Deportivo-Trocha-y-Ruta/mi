import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Loader2, Trash2 } from "lucide-react";

import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
  SheetBody,
  SheetFooter,
} from "@/components/ui/sheet";
import { ConfirmDialog } from "@/components/shared/ConfirmDialog";
import { EventTypeChip } from "./EventTypeChip";
import {
  useCancelCalendarEvent,
  useCalendarEvent,
  useDeleteCalendarEventPermanent,
} from "@/api/calendar";
import { CLUB_LOCALE, CLUB_TIMEZONE, formatFullDate, formatTime } from "@/lib/datetime";
import type {
  Audience,
  CalendarEventRead,
  EventDataBirthday,
  EventDataCompetition,
  EventDataClubEvent,
  EventDataGroupTraining,
  EventDataPersonalTraining,
  EventDataRestDay,
  EventDataTrainingSession,
} from "@/types/calendar.types";

interface EventDrawerProps {
  eventId: number | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  userRole?: "coach" | "admin" | "parent";
}

function formatEventDateTime(iso: string, allDay: boolean): string {
  if (allDay) return formatFullDate(iso);
  return new Intl.DateTimeFormat(CLUB_LOCALE, {
    weekday: "long",
    year: "numeric",
    month: "long",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: CLUB_TIMEZONE,
  }).format(new Date(iso));
}

function audienceLabel(aud: Audience): string {
  switch (aud.audience_type) {
    case "all_club":
      return "Todo el club";
    case "category":
      return `Categoría: ${aud.audience_value.category}`;
    case "athlete_list": {
      const count = aud.audience_value.athlete_ids.length;
      return `${count} atleta${count !== 1 ? "s" : ""} seleccionado${count !== 1 ? "s" : ""}`;
    }
    case "individual":
      return `Atleta individual (id: ${aud.audience_value.athlete_id})`;
    default:
      return "Audiencia desconocida";
  }
}

const INTENSITY_LABELS: Record<string, string> = {
  low: "Baja",
  medium: "Media",
  high: "Alta",
};

const KIND_LABELS: Record<string, string> = {
  social: "Social",
  meeting: "Reunión",
  workshop: "Taller",
};

const SCOPE_LABELS: Record<string, string> = {
  club: "Todo el club",
  category: "Por categoría",
  athlete: "Atleta específico",
};

const RACE_CATEGORY_LABELS: Record<string, string> = {
  A: "A — Tapering completo",
  B: "B — Mini-tapering",
  C: "C — Diagnóstica",
};

const dtClass = "text-xs font-semibold uppercase tracking-wide text-mid-gray";
const ddClass = "mt-1 text-charcoal";

function EventSpecificData({
  eventType,
  eventData,
}: {
  eventType: CalendarEventRead["event_type"];
  eventData: CalendarEventRead["event_data"];
}) {
  if (!eventData) return null;

  switch (eventType) {
    case "competition": {
      const d = eventData as EventDataCompetition;
      return (
        <div>
          <dt className={dtClass}>Datos de competencia</dt>
          <dd className={`${ddClass} space-y-0.5`}>
            <p>Ciudad: {d.city}</p>
            <p>Categoría: {RACE_CATEGORY_LABELS[d.race_category] ?? d.race_category}</p>
            {d.is_departmental && <p>Campeonato Departamental</p>}
          </dd>
        </div>
      );
    }
    case "club_event": {
      const d = eventData as EventDataClubEvent;
      return (
        <div>
          <dt className={dtClass}>Tipo de evento</dt>
          <dd className={ddClass}>
            <p>{KIND_LABELS[d.kind] ?? d.kind}</p>
            {d.registration_url && (
              <a
                href={d.registration_url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-sm text-link-blue underline-offset-2 hover:underline"
              >
                Enlace de registro
              </a>
            )}
          </dd>
        </div>
      );
    }
    case "personal_training": {
      const d = eventData as EventDataPersonalTraining;
      return (
        <div>
          <dt className={dtClass}>Entrenamiento personal</dt>
          <dd className={ddClass}>
            Intensidad: {INTENSITY_LABELS[d.intensity] ?? d.intensity}
          </dd>
        </div>
      );
    }
    case "group_training": {
      const d = eventData as EventDataGroupTraining;
      return (
        <div>
          <dt className={dtClass}>Entrenamiento grupal</dt>
          <dd className={`${ddClass} space-y-0.5`}>
            <p>Intensidad: {INTENSITY_LABELS[d.intensity] ?? d.intensity}</p>
            {d.group_size_max != null && <p>Máx. atletas: {d.group_size_max}</p>}
          </dd>
        </div>
      );
    }
    case "rest_day": {
      const d = eventData as EventDataRestDay;
      return (
        <div>
          <dt className={dtClass}>Día de descanso</dt>
          <dd className={`${ddClass} space-y-0.5`}>
            <p>Alcance: {SCOPE_LABELS[d.scope] ?? d.scope}</p>
            {d.reason && <p>Motivo: {d.reason}</p>}
          </dd>
        </div>
      );
    }
    case "training_session": {
      const d = eventData as EventDataTrainingSession;
      if (!d.training_session_id) return null;
      return (
        <div>
          <dt className={dtClass}>Sesión de entrenamiento</dt>
          <dd className={ddClass}>ID sesión: {d.training_session_id}</dd>
        </div>
      );
    }
    default:
      return null;
  }
}

const STATUS_LABELS: Record<string, string> = {
  scheduled: "Programado",
  confirmed: "Confirmado",
  cancelled: "Cancelado",
  completed: "Completado",
};

// ---------------------------------------------------------------------------
// BirthdayDetail — panel de solo lectura para eventos virtuales de cumpleaños
// ---------------------------------------------------------------------------

interface BirthdayDetailProps {
  startAt: string;
  eventData: EventDataBirthday | null;
}

function BirthdayDetail({ startAt, eventData }: BirthdayDetailProps) {
  const dateLabel = formatFullDate(startAt);

  return (
    <dl className="space-y-4 text-sm">
      <div>
        <dt className="text-xs font-semibold uppercase tracking-wide text-mid-gray">
          Tipo
        </dt>
        <dd className="mt-1 text-charcoal">Cumpleaños</dd>
      </div>

      {eventData?.athlete_first_name && (
        <div>
          <dt className="text-xs font-semibold uppercase tracking-wide text-mid-gray">
            Atleta
          </dt>
          <dd className="mt-1 text-charcoal">{eventData.athlete_first_name}</dd>
        </div>
      )}

      {eventData?.age_turning != null && (
        <div>
          <dt className="text-xs font-semibold uppercase tracking-wide text-mid-gray">
            Cumple
          </dt>
          <dd className="mt-1 text-charcoal">
            {eventData.age_turning} {eventData.age_turning === 1 ? "año" : "años"}
          </dd>
        </div>
      )}

      <div>
        <dt className="text-xs font-semibold uppercase tracking-wide text-mid-gray">
          Fecha
        </dt>
        <dd className="mt-1 capitalize text-charcoal">{dateLabel}</dd>
      </div>
    </dl>
  );
}

export function EventDrawer({
  eventId,
  open,
  onOpenChange,
  userRole = "coach",
}: EventDrawerProps) {
  const navigate = useNavigate();
  const [confirmCancel, setConfirmCancel] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const eventQuery = useCalendarEvent(eventId);
  const cancelMutation = useCancelCalendarEvent();
  const deletePermanentMutation = useDeleteCalendarEventPermanent();

  const canManage = userRole === "coach" || userRole === "admin";

  const event = eventQuery.data;
  const isLoading = eventQuery.isLoading;

  /**
   * ConfirmDialog (AlertDialog de Radix) ahora se anida dentro del Sheet
   * (Dialog de Radix) mientras confirmCancel/confirmDelete están abiertos.
   * Dialog y AlertDialog traen cada uno su propia copia de
   * @radix-ui/react-focus-scope (versiones distintas en node_modules, sin
   * deduplicar) — dos FocusScope "trapped" simultáneos que no se conocen
   * entre sí compiten por recuperar el foco en cada focusout del otro,
   * entrando en un loop síncrono infinito en jsdom (cuelga la suite; en
   * navegador real se manifiesta como el foco "peleado" entre ambos).
   * Al soltar `modal` en el Sheet mientras hay un ConfirmDialog anidado
   * abierto, el Sheet deja de atrapar el foco y el AlertDialog (que sigue
   * siendo modal) queda como única capa activa — sin pelea.
   */
  const nestedConfirmOpen = confirmCancel || confirmDelete;

  function handleEdit() {
    if (eventId) {
      onOpenChange(false);
      navigate(`/calendar/events/${eventId}/edit`);
    }
  }

  function handleConfirmCancel() {
    if (!eventId) return;
    cancelMutation.mutate(
      { id: eventId },
      {
        onSuccess: () => {
          setConfirmCancel(false);
          onOpenChange(false);
        },
      },
    );
  }

  function handleConfirmDelete() {
    if (!eventId) return;
    deletePermanentMutation.mutate(
      { id: eventId },
      {
        onSuccess: () => {
          setConfirmDelete(false);
          onOpenChange(false);
        },
      },
    );
  }

  return (
    <>
      <Sheet open={open} onOpenChange={onOpenChange} modal={!nestedConfirmOpen}>
        <SheetContent side="right" aria-label="Detalle del evento">
          <SheetHeader>
            {isLoading ? (
              <>
                <SheetTitle className="sr-only">Cargando evento</SheetTitle>
                <SheetDescription className="sr-only">
                  Cargando los detalles del evento.
                </SheetDescription>
                <div className="space-y-2" aria-hidden="true">
                  <div className="h-4 w-3/4 animate-pulse rounded bg-light-gray" />
                  <div className="h-3 w-1/2 animate-pulse rounded bg-light-gray" />
                </div>
              </>
            ) : event ? (
              <>
                <SheetTitle>{event.title}</SheetTitle>
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
              <>
                <SheetTitle>Evento</SheetTitle>
                <SheetDescription className="sr-only">
                  Detalle del evento del calendario.
                </SheetDescription>
              </>
            )}
          </SheetHeader>

          <SheetBody>
            {isLoading && (
              <div className="space-y-3">
                {Array.from({ length: 5 }).map((_, i) => (
                  <div
                    key={i}
                    className="h-4 animate-pulse rounded bg-light-gray"
                    style={{ width: `${60 + i * 8}%` }}
                  />
                ))}
              </div>
            )}

            {eventQuery.isError && (
              <p className="text-sm text-red-600">
                No se pudo cargar el detalle del evento.
              </p>
            )}

            {event && event.event_type === "birthday" ? (
              <BirthdayDetail
                startAt={event.start_at}
                eventData={event.event_data as EventDataBirthday | null}
              />
            ) : event ? (
              <dl className="space-y-4 text-sm">
                {/* Date & time */}
                <div>
                  <dt className="text-xs font-semibold uppercase tracking-wide text-mid-gray">
                    Fecha y hora
                  </dt>
                  <dd className="mt-1 text-charcoal">
                    {formatEventDateTime(event.start_at, event.all_day)}
                    {" — "}
                    {event.all_day ? "Todo el día" : formatTime(event.end_at)}
                  </dd>
                </div>

                {/* Location */}
                {event.location && (
                  <div>
                    <dt className="text-xs font-semibold uppercase tracking-wide text-mid-gray">
                      Lugar
                    </dt>
                    <dd className="mt-1 text-charcoal">{event.location}</dd>
                  </div>
                )}

                {/* Description */}
                {event.description && (
                  <div>
                    <dt className="text-xs font-semibold uppercase tracking-wide text-mid-gray">
                      Descripción
                    </dt>
                    <dd className="mt-1 whitespace-pre-wrap text-charcoal">
                      {event.description}
                    </dd>
                  </div>
                )}

                {/* Audiences */}
                {event.audiences && event.audiences.length > 0 && (
                  <div>
                    <dt className="text-xs font-semibold uppercase tracking-wide text-mid-gray">
                      Audiencia
                    </dt>
                    <dd className="mt-1">
                      <ul className="space-y-1">
                        {event.audiences.map((aud, idx) => (
                          <li key={idx} className="text-charcoal">
                            {audienceLabel(aud)}
                          </li>
                        ))}
                      </ul>
                    </dd>
                  </div>
                )}

                {/* Datos específicos por tipo */}
                <EventSpecificData
                  eventType={event.event_type}
                  eventData={event.event_data}
                />
              </dl>
            ) : null}
          </SheetBody>

          {event && event.event_type !== "birthday" && (
            <SheetFooter>
              {canManage && (
                <button
                  type="button"
                  onClick={() => setConfirmDelete(true)}
                  disabled={deletePermanentMutation.isPending}
                  aria-label="Eliminar permanentemente"
                  className="flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium text-red-800 transition-opacity hover:opacity-70 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-400/60 focus-visible:ring-offset-2 disabled:opacity-40"
                  style={{ boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" }}
                >
                  {deletePermanentMutation.isPending ? (
                    <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                  ) : (
                    <>
                      <Trash2 className="h-4 w-4" aria-hidden="true" />
                      Eliminar
                    </>
                  )}
                </button>
              )}
              {canManage && (
                <button
                  type="button"
                  onClick={() => setConfirmCancel(true)}
                  disabled={event.status === "cancelled" || cancelMutation.isPending}
                  className="rounded-lg px-3 py-2 text-sm font-medium text-red-600 transition-opacity hover:opacity-70 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-400/60 focus-visible:ring-offset-2 disabled:opacity-40"
                  style={{ boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" }}
                >
                  {cancelMutation.isPending ? (
                    <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                  ) : (
                    "Cancelar evento"
                  )}
                </button>
              )}
              <button
                type="button"
                onClick={handleEdit}
                className="rounded-lg bg-charcoal px-4 py-2 text-sm font-medium text-white transition-opacity hover:opacity-70 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-charcoal/60 focus-visible:ring-offset-2"
                style={{ boxShadow: "rgba(255, 255, 255, 0.15) 0px 2px 0px inset" }}
              >
                Editar
              </button>
            </SheetFooter>
          )}
        </SheetContent>
      </Sheet>

      <ConfirmDialog
        open={confirmCancel}
        title="Cancelar evento"
        description="El evento pasará al estado 'cancelado'. Los participantes serán notificados."
        confirmLabel="Cancelar evento"
        cancelLabel="No, volver"
        tone="danger"
        isPending={cancelMutation.isPending}
        onCancel={() => setConfirmCancel(false)}
        onConfirm={handleConfirmCancel}
      />

      <ConfirmDialog
        open={confirmDelete}
        title="Eliminar evento permanentemente"
        description="Esta acción NO se puede deshacer. El evento, sus participantes y asistencias serán borrados de la base de datos."
        confirmLabel="Sí, eliminar"
        cancelLabel="No, volver"
        tone="danger"
        isPending={deletePermanentMutation.isPending}
        onCancel={() => setConfirmDelete(false)}
        onConfirm={handleConfirmDelete}
      />
    </>
  );
}
