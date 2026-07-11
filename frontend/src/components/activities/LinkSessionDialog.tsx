/**
 * LinkSessionDialog — coach/admin dialog to link, re-link, or unlink a
 * Strava activity to a training session (feature 025, T032, FR-007,
 * FR-008, SC-005 "link any single activity in 3 interactions or fewer").
 *
 * Flow:
 *   1. Suggestions (`useSessionSuggestions`) — sessions in the same club
 *      within ±1 day of the activity, same-day + attendance ranked first
 *      by the backend — render as a radio list. Common path: open dialog →
 *      pick a suggestion → click "Vincular" (3 clicks total from the
 *      review row).
 *   2. "Buscar en el calendario" reveals a text filter over ALL of the
 *      coach's sessions (`useTrainingSessions`, already cached elsewhere
 *      in the app) for the rare case the right session falls outside the
 *      ±1 day suggestion window.
 *   3. When the activity is already linked, its current session is
 *      pre-selected and a separate "Desvincular" action clears the link
 *      without going through the radio form.
 *
 * Accessibility: built on the shadcn/ui Dialog (Radix) — focus-trapped,
 * Escape dismisses, `aria-modal`. Radio rows use visually-hidden native
 * `<input type="radio">` elements grouped by `name` so assistive tech gets
 * standard radio-group semantics; the wrapping `<label>` renders the
 * visible card and carries the `peer-focus-visible` ring for keyboard
 * users. 48px-tall touch targets on every interactive row/button.
 *
 * Privacy (Ley 1581): only reads/displays fields already scrubbed of
 * GPS/location data by the backend (`ActivityOut`, `SessionSuggestion`,
 * `TrainingSession` summary fields) — no new privacy surface here.
 */
import { useEffect, useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import type { UseFormRegister } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import axios from "axios";
import {
  CalendarSearch,
  CheckCircle2,
  Link2Off,
  Loader2,
  Search,
  XCircle,
} from "lucide-react";
import { z } from "zod";

import { useTrainingSessions } from "@/api/trainingSessions";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useSessionSuggestions } from "@/hooks/activities/useActivityReview";
import { useLinkActivity } from "@/hooks/activities/useLinkActivity";
import { formatDate, formatTime } from "@/lib/datetime";
import { cn } from "@/lib/utils";
import type { ActivityOut, SessionSuggestion } from "@/types/strava.types";
import type { TrainingSession } from "@/types/trainingSession.types";

// ---------------------------------------------------------------------------
// Zod schema
// ---------------------------------------------------------------------------

const linkSessionSchema = z.object({
  training_session_id: z
    .string()
    .min(1, "Selecciona una sesión para vincular la actividad."),
});

type LinkSessionValues = z.infer<typeof linkSessionSchema>;

// ---------------------------------------------------------------------------
// Formatters & labels (mirror de ActivityCard.tsx — convención "naive-local")
// ---------------------------------------------------------------------------

const SPORT_TYPE_LABELS: Record<string, string> = {
  Ride: "Ruta",
  MountainBikeRide: "MTB",
  GravelRide: "Gravel",
  VirtualRide: "Virtual",
  EBikeRide: "E-bike",
  Run: "Carrera",
  Workout: "Entrenamiento",
};

function sportTypeLabel(sportType: string): string {
  return SPORT_TYPE_LABELS[sportType] ?? sportType;
}

const SESSION_KIND_LABELS: Record<string, string> = {
  entrenamiento: "Entrenamiento",
  actividad_conjunta: "Actividad conjunta",
  salida: "Salida",
  otro: "Otro",
};

function sessionKindLabel(kind: string | null | undefined): string {
  if (!kind) return "Sesión";
  return SESSION_KIND_LABELS[kind] ?? kind;
}

/**
 * `start_date_local` / `scheduled_date` de sugerencias llegan como datetime
 * NAIVE que YA representa la hora local del club (no UTC) — a diferencia de
 * `lib/datetime.ts` (que asume naive = UTC), acá NO se debe convertir zona
 * horaria: se parsean los componentes tal cual vienen para evitar un
 * corrimiento de horas/día. Ver misma nota en `ActivityCard.tsx`.
 */
function formatNaiveLocalDateTime(value: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/.exec(value);
  if (!match) return value;
  const [, year, month, day, hour, minute] = match;
  const local = new Date(
    Number(year),
    Number(month) - 1,
    Number(day),
    Number(hour),
    Number(minute),
  );
  const datePart = new Intl.DateTimeFormat("es-CO", {
    day: "2-digit",
    month: "short",
  }).format(local);
  const timePart = new Intl.DateTimeFormat("es-CO", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(local);
  return `${datePart} · ${timePart}`;
}

function mapLinkErrorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const detail = (error.response?.data as { detail?: string } | undefined)
      ?.detail;
    if (typeof detail === "string" && detail.trim() !== "") return detail;
  }
  return "No se pudo actualizar el vínculo. Verifica la conexión e intenta de nuevo.";
}

// ---------------------------------------------------------------------------
// Session option — forma unificada para sugerencias y resultados de calendario
// ---------------------------------------------------------------------------

interface SessionOption {
  training_session_id: number;
  dateTimeLabel: string;
  kindLabel: string;
  location: string | null;
  technicalFocus: string | null;
  sameDay?: boolean;
  attended?: boolean;
  /** Etiqueta de búsqueda en minúsculas para el filtro de texto libre. */
  searchText: string;
}

function suggestionToOption(s: SessionSuggestion): SessionOption {
  return {
    training_session_id: s.training_session_id,
    dateTimeLabel: formatNaiveLocalDateTime(s.scheduled_date),
    kindLabel: sessionKindLabel(s.session_kind),
    location: s.location,
    technicalFocus: s.technical_focus,
    sameDay: s.same_day,
    attended: s.athlete_in_attendance,
    searchText: [
      s.location,
      s.technical_focus,
      sessionKindLabel(s.session_kind),
    ]
      .filter(Boolean)
      .join(" ")
      .toLowerCase(),
  };
}

function trainingSessionToOption(s: TrainingSession): SessionOption {
  return {
    training_session_id: s.id,
    dateTimeLabel: `${formatDate(s.scheduled_date)} · ${formatTime(s.scheduled_start_time)}`,
    kindLabel: sessionKindLabel(s.session_kind),
    location: s.location,
    technicalFocus: s.technical_focus,
    searchText: [s.location, s.technical_focus, sessionKindLabel(s.session_kind)]
      .filter(Boolean)
      .join(" ")
      .toLowerCase(),
  };
}

// ---------------------------------------------------------------------------
// Radio row
// ---------------------------------------------------------------------------

interface SessionOptionRowProps {
  option: SessionOption;
  checked: boolean;
  disabled: boolean;
  register: UseFormRegister<LinkSessionValues>;
}

function SessionOptionRow({
  option,
  checked,
  disabled,
  register,
}: SessionOptionRowProps) {
  return (
    <label
      className={cn(
        "flex min-h-[48px] cursor-pointer items-start gap-3 rounded-xl bg-white p-3 transition-colors",
        "peer-focus-visible:outline-none",
        checked ? "ring-2 ring-charcoal" : "hover:bg-light-gray",
        disabled && "cursor-not-allowed opacity-60",
        "shadow-ring",
      )}
    >
      <input
        type="radio"
        value={String(option.training_session_id)}
        disabled={disabled}
        className="peer sr-only"
        {...register("training_session_id")}
      />
      <span
        className={cn(
          "mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full border",
          checked ? "border-charcoal bg-charcoal" : "border-[rgba(34,42,53,0.3)]",
          "peer-focus-visible:ring-2 peer-focus-visible:ring-charcoal/40",
        )}
        aria-hidden="true"
      >
        {checked && <span className="h-1.5 w-1.5 rounded-full bg-white" />}
      </span>

      <span className="min-w-0 flex-1">
        <span className="flex flex-wrap items-center gap-1.5">
          <span className="text-sm font-medium text-charcoal">
            {option.dateTimeLabel}
          </span>
          <span className="text-xs text-mid-gray">· {option.kindLabel}</span>
        </span>
        <span className="mt-0.5 block truncate text-xs text-mid-gray">
          {option.location ?? "Sin lugar"}
          {option.technicalFocus ? ` · ${option.technicalFocus}` : ""}
        </span>
        {(option.sameDay || option.attended) && (
          <span className="mt-1 flex flex-wrap gap-1">
            {option.sameDay && (
              <Badge variant="info" className="text-[10px]">
                Mismo día
              </Badge>
            )}
            {option.attended && (
              <Badge variant="success" className="text-[10px]">
                Asistió
              </Badge>
            )}
          </span>
        )}
      </span>
    </label>
  );
}

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface LinkSessionDialogProps {
  activity: ActivityOut;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function LinkSessionDialog({
  activity,
  open,
  onOpenChange,
}: LinkSessionDialogProps) {
  const currentSessionId = activity.link?.training_session_id ?? null;

  const [toast, setToast] = useState<{ type: "success" | "error"; message: string } | null>(
    null,
  );
  const [showCalendarSearch, setShowCalendarSearch] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");

  const suggestionsQuery = useSessionSuggestions(activity.id, open);
  // Búsqueda de calendario: reutiliza la query global de sesiones (misma
  // caché que SessionsListPage) — el filtro por texto se aplica en cliente.
  const calendarQuery = useTrainingSessions();

  const linkMutation = useLinkActivity();

  const {
    register,
    handleSubmit,
    watch,
    reset,
    formState: { errors },
  } = useForm<LinkSessionValues>({
    resolver: zodResolver(linkSessionSchema),
    defaultValues: {
      training_session_id: currentSessionId ? String(currentSessionId) : "",
    },
  });

  // Re-sincroniza el formulario cada vez que el diálogo se abre con una
  // actividad (posiblemente distinta o recién actualizada).
  useEffect(() => {
    if (open) {
      reset({
        training_session_id: currentSessionId ? String(currentSessionId) : "",
      });
      setToast(null);
      setShowCalendarSearch(false);
      setSearchQuery("");
    }
  }, [open, activity.id, currentSessionId, reset]);

  const selectedValue = watch("training_session_id");
  const isPending = linkMutation.isPending;

  const suggestionOptions = useMemo(
    () => (suggestionsQuery.data?.suggestions ?? []).map(suggestionToOption),
    [suggestionsQuery.data],
  );

  const suggestionIds = useMemo(
    () => new Set(suggestionOptions.map((o) => o.training_session_id)),
    [suggestionOptions],
  );

  const calendarOptions = useMemo(() => {
    const query = searchQuery.trim().toLowerCase();
    return (calendarQuery.data ?? [])
      .filter((s) => !suggestionIds.has(s.id))
      .map(trainingSessionToOption)
      .filter((o) => query === "" || o.searchText.includes(query) || o.dateTimeLabel.toLowerCase().includes(query))
      .slice(0, 20);
  }, [calendarQuery.data, suggestionIds, searchQuery]);

  function handleOpenChange(nextOpen: boolean) {
    if (isPending && !nextOpen) return;
    onOpenChange(nextOpen);
  }

  function onSubmit(values: LinkSessionValues) {
    const trainingSessionId = Number(values.training_session_id);
    if (trainingSessionId === currentSessionId) {
      onOpenChange(false);
      return;
    }
    setToast(null);
    linkMutation.mutate(
      {
        activityId: activity.id,
        trainingSessionId,
        athleteId: activity.athlete_id,
        previousSessionId: currentSessionId,
      },
      {
        onSuccess: () => {
          setToast({ type: "success", message: "Actividad vinculada correctamente." });
          setTimeout(() => onOpenChange(false), 900);
        },
        onError: (err) => {
          setToast({ type: "error", message: mapLinkErrorMessage(err) });
        },
      },
    );
  }

  function handleUnlink() {
    setToast(null);
    linkMutation.mutate(
      {
        activityId: activity.id,
        trainingSessionId: null,
        athleteId: activity.athlete_id,
        previousSessionId: currentSessionId,
      },
      {
        onSuccess: () => {
          setToast({ type: "success", message: "Actividad desvinculada." });
          setTimeout(() => onOpenChange(false), 900);
        },
        onError: (err) => {
          setToast({ type: "error", message: mapLinkErrorMessage(err) });
        },
      },
    );
  }

  const hasSuggestions = suggestionOptions.length > 0;

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent
        className="max-h-[90dvh] w-full max-w-lg overflow-y-auto"
        aria-label="Vincular actividad a sesión"
      >
        <DialogHeader>
          <DialogTitle>
            {currentSessionId ? "Editar vínculo de sesión" : "Vincular a sesión"}
          </DialogTitle>
          <DialogDescription>
            {activity.athlete_name} · {sportTypeLabel(activity.sport_type)} ·{" "}
            {formatNaiveLocalDateTime(activity.start_date_local)}
          </DialogDescription>
        </DialogHeader>

        <DialogBody>
          <form
            id="link-session-form"
            onSubmit={handleSubmit(onSubmit)}
            className="space-y-4"
            noValidate
          >
            {/* Sugerencias */}
            <div className="space-y-2">
              <span className="block text-xs font-medium text-mid-gray">
                Sesiones sugeridas
              </span>

              {suggestionsQuery.isLoading && (
                <div className="flex items-center gap-2 py-3 text-sm text-mid-gray">
                  <Loader2 size={14} className="animate-spin" aria-hidden="true" />
                  Buscando sesiones cercanas…
                </div>
              )}

              {suggestionsQuery.isError && (
                <p className="text-sm text-mid-gray">
                  No se pudieron cargar las sugerencias. Usa la búsqueda en el
                  calendario más abajo.
                </p>
              )}

              {!suggestionsQuery.isLoading && !suggestionsQuery.isError && !hasSuggestions && (
                <p className="text-sm text-mid-gray">
                  No hay sesiones cercanas a esta actividad. Búscala en el
                  calendario.
                </p>
              )}

              {hasSuggestions && (
                <div
                  role="radiogroup"
                  aria-label="Sesiones sugeridas"
                  className="space-y-2"
                >
                  {suggestionOptions.map((option) => (
                    <SessionOptionRow
                      key={option.training_session_id}
                      option={option}
                      disabled={isPending}
                      checked={selectedValue === String(option.training_session_id)}
                      register={register}
                    />
                  ))}
                </div>
              )}
            </div>

            {/* Búsqueda de calendario */}
            <div className="border-t border-[rgba(34,42,53,0.08)] pt-4">
              <button
                type="button"
                onClick={() => setShowCalendarSearch((v) => !v)}
                disabled={isPending}
                className={cn(
                  "flex min-h-[48px] w-full items-center gap-2 rounded-lg px-3 text-sm font-medium text-charcoal transition-colors",
                  "hover:bg-light-gray disabled:opacity-50",
                  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-charcoal/40",
                )}
                aria-expanded={showCalendarSearch}
                aria-controls="link-session-calendar-search"
              >
                <CalendarSearch size={16} aria-hidden="true" />
                {showCalendarSearch
                  ? "Ocultar búsqueda en el calendario"
                  : "¿No encuentras la sesión? Buscar en el calendario"}
              </button>

              {showCalendarSearch && (
                <div id="link-session-calendar-search" className="mt-3 space-y-2">
                  <div className="relative">
                    <Search
                      size={14}
                      className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-mid-gray"
                      aria-hidden="true"
                    />
                    <input
                      type="search"
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                      disabled={isPending}
                      placeholder="Buscar por fecha, lugar o enfoque técnico…"
                      aria-label="Buscar sesión en el calendario"
                      className={cn(
                        "w-full rounded-lg bg-white py-3 pl-9 pr-3 text-sm outline-none focus:ring-2 focus:ring-blue-500/40 disabled:opacity-50",
                        "shadow-ring",
                      )}
                    />
                  </div>

                  {calendarQuery.isLoading && (
                    <div className="flex items-center gap-2 py-2 text-sm text-mid-gray">
                      <Loader2 size={14} className="animate-spin" aria-hidden="true" />
                      Cargando calendario…
                    </div>
                  )}

                  {!calendarQuery.isLoading && calendarOptions.length === 0 && (
                    <p className="py-2 text-sm text-mid-gray">
                      Sin resultados para esta búsqueda.
                    </p>
                  )}

                  {calendarOptions.length > 0 && (
                    <div
                      role="radiogroup"
                      aria-label="Resultados de búsqueda en el calendario"
                      className="max-h-56 space-y-2 overflow-y-auto pr-1"
                    >
                      {calendarOptions.map((option) => (
                        <SessionOptionRow
                          key={option.training_session_id}
                          option={option}
                          disabled={isPending}
                          checked={selectedValue === String(option.training_session_id)}
                          register={register}
                        />
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>

            {errors.training_session_id && (
              <p className="text-xs text-red-600" role="alert">
                {errors.training_session_id.message}
              </p>
            )}

            {/* Toast inline */}
            {toast && (
              <div
                role="status"
                aria-live="polite"
                className={cn(
                  "flex items-start gap-2 rounded-lg px-3 py-2 text-sm",
                  toast.type === "success"
                    ? "border border-emerald-200 bg-emerald-50 text-emerald-900"
                    : "border border-red-200 bg-red-50 text-red-800",
                )}
              >
                {toast.type === "success" ? (
                  <CheckCircle2 size={16} aria-hidden="true" className="mt-0.5 shrink-0" />
                ) : (
                  <XCircle size={16} aria-hidden="true" className="mt-0.5 shrink-0" />
                )}
                <span>{toast.message}</span>
              </div>
            )}
          </form>

          {currentSessionId && (
            <div className="mt-5 border-t border-[rgba(34,42,53,0.08)] pt-4">
              <p className="mb-3 text-xs text-mid-gray">
                Quitar el vínculo actual de esta actividad. La actividad
                vuelve al estado "sin enlazar".
              </p>
              <button
                type="button"
                onClick={handleUnlink}
                disabled={isPending}
                className={cn(
                  "inline-flex min-h-[48px] items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition-colors",
                  "border border-red-200 text-red-700 hover:bg-red-50",
                  "disabled:cursor-not-allowed disabled:opacity-50",
                  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-400/50",
                )}
              >
                {isPending ? (
                  <Loader2 size={14} className="animate-spin" aria-hidden="true" />
                ) : (
                  <Link2Off size={14} aria-hidden="true" />
                )}
                Desvincular
              </button>
            </div>
          )}
        </DialogBody>

        <DialogFooter>
          <button
            type="button"
            onClick={() => handleOpenChange(false)}
            disabled={isPending}
            className="rounded-lg px-4 py-2 text-sm font-medium text-mid-gray hover:text-charcoal disabled:opacity-50"
          >
            Cancelar
          </button>
          <button
            type="submit"
            form="link-session-form"
            disabled={isPending || !selectedValue}
            className={cn(
              "inline-flex min-h-[48px] items-center gap-2 rounded-lg bg-charcoal px-4 py-2 text-sm font-semibold text-white",
              "transition-opacity hover:opacity-90 disabled:opacity-50",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-charcoal/50",
            )}
          >
            {isPending && <Loader2 size={14} className="animate-spin" aria-hidden="true" />}
            {currentSessionId ? "Actualizar vínculo" : "Vincular"}
          </button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default LinkSessionDialog;
