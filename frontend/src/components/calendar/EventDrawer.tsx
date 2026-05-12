import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Loader2 } from "lucide-react";

import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
  SheetBody,
  SheetFooter,
} from "@/components/ui/sheet";
import { ConfirmModal } from "@/components/common/ConfirmModal";
import { EventTypeChip } from "./EventTypeChip";
import { useCancelCalendarEvent, useCalendarEvent } from "@/api/calendar";
import type { Audience } from "@/types/calendar.types";

interface EventDrawerProps {
  eventId: number | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

function formatDateTime(iso: string, allDay: boolean): string {
  const date = new Date(iso);
  if (allDay) {
    return new Intl.DateTimeFormat("es-CO", {
      weekday: "long",
      year: "numeric",
      month: "long",
      day: "numeric",
      timeZone: "America/Bogota",
    }).format(date);
  }
  return new Intl.DateTimeFormat("es-CO", {
    weekday: "long",
    year: "numeric",
    month: "long",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "America/Bogota",
  }).format(date);
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

const STATUS_LABELS: Record<string, string> = {
  scheduled: "Programado",
  confirmed: "Confirmado",
  cancelled: "Cancelado",
  completed: "Completado",
};

export function EventDrawer({ eventId, open, onOpenChange }: EventDrawerProps) {
  const navigate = useNavigate();
  const [confirmCancel, setConfirmCancel] = useState(false);

  const eventQuery = useCalendarEvent(eventId);
  const cancelMutation = useCancelCalendarEvent();

  const event = eventQuery.data;
  const isLoading = eventQuery.isLoading;

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

  return (
    <>
      <Sheet open={open} onOpenChange={onOpenChange}>
        <SheetContent side="right" aria-label="Detalle del evento">
          <SheetHeader>
            {isLoading ? (
              <div className="space-y-2">
                <div className="h-4 w-3/4 animate-pulse rounded bg-light-gray" />
                <div className="h-3 w-1/2 animate-pulse rounded bg-light-gray" />
              </div>
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
              <SheetTitle>Evento</SheetTitle>
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

            {event && (
              <dl className="space-y-4 text-sm">
                {/* Date & time */}
                <div>
                  <dt className="text-xs font-semibold uppercase tracking-wide text-mid-gray">
                    Fecha y hora
                  </dt>
                  <dd className="mt-1 text-charcoal">
                    {formatDateTime(event.start_at, event.all_day)}
                    {" — "}
                    {event.all_day
                      ? "Todo el día"
                      : new Intl.DateTimeFormat("es-CO", {
                          hour: "2-digit",
                          minute: "2-digit",
                          timeZone: "America/Bogota",
                        }).format(new Date(event.end_at))}
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
              </dl>
            )}
          </SheetBody>

          {event && event.event_type !== "birthday" && (
            <SheetFooter>
              <button
                type="button"
                onClick={() => setConfirmCancel(true)}
                disabled={event.status === "cancelled" || cancelMutation.isPending}
                className="rounded-lg px-3 py-2 text-sm font-medium text-red-600 transition-opacity hover:opacity-70 disabled:opacity-40"
                style={{ boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" }}
              >
                {cancelMutation.isPending ? (
                  <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                ) : (
                  "Cancelar evento"
                )}
              </button>
              <button
                type="button"
                onClick={handleEdit}
                className="rounded-lg bg-charcoal px-4 py-2 text-sm font-medium text-white transition-opacity hover:opacity-70"
                style={{ boxShadow: "rgba(255, 255, 255, 0.15) 0px 2px 0px inset" }}
              >
                Editar
              </button>
            </SheetFooter>
          )}
        </SheetContent>
      </Sheet>

      <ConfirmModal
        open={confirmCancel}
        title="Cancelar evento"
        body="El evento pasará al estado 'cancelado'. Los participantes serán notificados."
        confirmLabel="Cancelar evento"
        cancelLabel="No, volver"
        confirmDanger
        isPending={cancelMutation.isPending}
        onCancel={() => setConfirmCancel(false)}
        onConfirm={handleConfirmCancel}
      />
    </>
  );
}
