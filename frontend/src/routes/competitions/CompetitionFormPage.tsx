/**
 * CompetitionFormPage — formulario de creación y edición de una competencia.
 *
 * mode="create" → ruta /competitions/new
 * mode="edit"   → ruta /competitions/:id/edit
 *
 * Spec 014 — Cup vs Championship:
 *   - Selector "Tipo de competencia" (Copa | Campeonato).
 *   - Picker de serie dinámico alimentado por useRaceSeriesList, filtrado por
 *     el tipo seleccionado. Estados loading/empty/error cubiertos.
 *   - Sin serie por defecto (no asume Copa Valle).
 *   - Campo "Válida #" visible y requerido SOLO para copa; oculto para campeonato.
 *   - Para campeonato: permite crear/seleccionar una serie tipo championship.
 *   - Modo edit: precarga correcta para ambos kinds.
 *   - Payload de submit deriva los campos correctos:
 *       Copa: sequence_number enviado, is_championship ignorado (backend deriva).
 *       Campeonato: sequence_number omitido, is_championship ignorado.
 *
 * Campos:
 *   - Tipo de competencia (Copa / Campeonato)
 *   - Serie (picker dinámico según tipo)
 *   - Número de válida (solo copa)
 *   - Nombre (auto-sugerido si vacío)
 *   - Fecha
 *   - Sede
 *   - Altitud (readonly, auto-completada)
 *   - Estado
 *
 * Notas de diseño:
 *   - En modo create, las condiciones climáticas NO se incluyen aquí.
 *   - En modo edit, PATCH solo envía campos de RaceEventUpdate (extra=forbid).
 *   - Error 409 con championship single-event muestra mensaje inline.
 *   - Soporta ?returnTo= para flujo "crear desde calendario".
 */
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { Loader2 } from "lucide-react";

import {
  competitionEventSchema,
  STATUS_OPTIONS,
  VALIDA_OPTIONS,
  type CompetitionEventFormValues,
} from "@/schemas/competitionEvent.schema";
import {
  getRaceEventErrorMessage,
  useCreateRaceEvent,
  useRaceEvent,
  useUpdateRaceEvent,
} from "@/hooks/race/useRaceEvents";
import { useRaceSeriesList, useCreateRaceSeries } from "@/hooks/race/useRaceSeries";
import { VENUE_ALTITUDES } from "@/types/raceEvents.types";
import type { RaceSeriesKind, RaceSeriesLevel } from "@/types/raceSeries.types";

// ---------------------------------------------------------------------------
// Estilos compartidos (patrón del proyecto)
// ---------------------------------------------------------------------------

const labelClass = "block text-sm font-medium text-charcoal";
const inputClass =
  "mt-1 w-full rounded-lg bg-white px-3 py-2 text-sm text-charcoal placeholder:text-mid-gray outline-none transition-shadow focus:ring-2 focus:ring-blue-500/40 min-h-[44px]";
const inputStyle = { boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" };
const errorClass = "mt-1 text-xs text-red-600";
const sectionClass = "rounded-xl bg-white p-5 space-y-4";
const sectionStyle = {
  boxShadow:
    "rgba(19, 19, 22, 0.7) 0px 1px 5px -4px, rgba(34, 42, 53, 0.08) 0px 0px 0px 1px, rgba(34, 42, 53, 0.05) 0px 4px 8px 0px",
};

// ---------------------------------------------------------------------------
// Opciones de sede
// ---------------------------------------------------------------------------

const VENUE_KEYS = Object.keys(VENUE_ALTITUDES);

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface CompetitionFormPageProps {
  mode: "create" | "edit";
}

// ---------------------------------------------------------------------------
// Tipo de competencia — UI discriminator
// ---------------------------------------------------------------------------

const COMPETITION_TYPE_OPTIONS: { value: RaceSeriesKind; label: string }[] = [
  { value: "cup", label: "Copa (con válidas numeradas)" },
  { value: "championship", label: "Campeonato (evento único anual)" },
];

// ---------------------------------------------------------------------------
// Nivel de serie de campeonato — spec 023
// ---------------------------------------------------------------------------

const SERIES_LEVEL_OPTIONS: { value: RaceSeriesLevel; label: string }[] = [
  { value: "departmental", label: "Departamental" },
  { value: "national", label: "Nacional" },
];

// ---------------------------------------------------------------------------
// Inline create-series form para campeonatos
// ---------------------------------------------------------------------------

interface CreateChampionshipSeriesFormProps {
  season: number;
  onCreated: (seriesId: number) => void;
}

function CreateChampionshipSeriesForm({
  season,
  onCreated,
}: CreateChampionshipSeriesFormProps) {
  const [name, setName] = useState("");
  const [organizer, setOrganizer] = useState("");
  const [level, setLevel] = useState<RaceSeriesLevel>("departmental");
  const [formError, setFormError] = useState<string | null>(null);
  const createSeries = useCreateRaceSeries();

  function handleCreate() {
    const trimmedName = name.trim();
    if (!trimmedName) {
      setFormError("El nombre de la serie es obligatorio.");
      return;
    }
    setFormError(null);
    createSeries.mutate(
      {
        name: trimmedName,
        season_year: season,
        kind: "championship",
        organizer: organizer.trim() || null,
        level,
      },
      {
        onSuccess: (created) => onCreated(created.id),
        onError: (err) => {
          if (
            typeof err === "object" &&
            err !== null &&
            (err as { response?: { status?: number } }).response?.status === 409
          ) {
            setFormError("Ya existe una serie con ese nombre para la temporada.");
          } else {
            setFormError("No se pudo crear la serie. Intenta de nuevo.");
          }
        },
      },
    );
  }

  return (
    <div className="mt-3 space-y-3 rounded-lg border border-blue-100 bg-blue-50 p-4">
      <p className="text-xs font-semibold text-blue-900">
        Crear nueva serie de campeonato
      </p>
      <div>
        <label className="block text-xs font-medium text-mid-gray">
          Nombre de la serie
        </label>
        <input
          type="text"
          placeholder="Ej: Campeonato Departamental 2026"
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="mt-1 w-full rounded-lg bg-white px-3 py-2 text-sm text-charcoal outline-none focus:ring-2 focus:ring-blue-500/40 min-h-[44px]"
          style={inputStyle}
          aria-label="Nombre de la nueva serie de campeonato"
        />
      </div>
      <div>
        <label className="block text-xs font-medium text-mid-gray">
          Organizador{" "}
          <span className="font-normal text-mid-gray">(opcional)</span>
        </label>
        <input
          type="text"
          placeholder="Ej: Liga Vallecaucana de Ciclismo"
          value={organizer}
          onChange={(e) => setOrganizer(e.target.value)}
          className="mt-1 w-full rounded-lg bg-white px-3 py-2 text-sm text-charcoal outline-none focus:ring-2 focus:ring-blue-500/40 min-h-[44px]"
          style={inputStyle}
          aria-label="Organizador de la serie"
        />
      </div>
      <div>
        <label className="block text-xs font-medium text-mid-gray">
          Nivel de la serie
        </label>
        <select
          value={level}
          onChange={(e) => setLevel(e.target.value as RaceSeriesLevel)}
          className="mt-1 w-full rounded-lg bg-white px-3 py-2 text-sm text-charcoal outline-none focus:ring-2 focus:ring-blue-500/40 min-h-[48px]"
          style={inputStyle}
          aria-label="Nivel de la serie"
        >
          {SERIES_LEVEL_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </div>
      {formError && (
        <p className="text-xs text-red-600" role="alert">
          {formError}
        </p>
      )}
      <button
        type="button"
        onClick={handleCreate}
        disabled={createSeries.isPending}
        className="inline-flex items-center gap-2 rounded-lg bg-blue-700 px-4 py-2 text-xs font-semibold text-white transition-opacity hover:opacity-80 disabled:opacity-50 min-h-[44px]"
      >
        {createSeries.isPending && (
          <Loader2 size={12} className="animate-spin" aria-hidden="true" />
        )}
        Crear serie
      </button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Página principal
// ---------------------------------------------------------------------------

export function CompetitionFormPage({ mode }: CompetitionFormPageProps) {
  const navigate = useNavigate();
  const { id } = useParams();
  const [searchParams] = useSearchParams();
  // Sanitizar returnTo: solo se permiten paths internos (inician con /).
  const rawReturnTo = searchParams.get("returnTo");
  const returnTo =
    rawReturnTo && /^\/[^/\\]/.test(rawReturnTo) ? rawReturnTo : null;

  const eventId = id ? Number(id) : null;
  const isEdit = mode === "edit";

  // UI state
  const [seriesKind, setSeriesKind] = useState<RaceSeriesKind>("cup");
  const [showCreateSeries, setShowCreateSeries] = useState(false);
  const [locationMode, setLocationMode] = useState<"predefined" | "custom">("predefined");
  const [altitudeEditable, setAltitudeEditable] = useState(false);
  const [computedAltitude, setComputedAltitude] = useState<number | null>(null);
  const [createCalendarEvent, setCreateCalendarEvent] = useState(true);
  const [globalError, setGlobalError] = useState<string | null>(null);
  const [seqError, setSeqError] = useState<string | null>(null);

  // Datos
  const eventQuery = useRaceEvent(isEdit ? eventId : null);
  const createMutation = useCreateRaceEvent();
  const updateMutation = useUpdateRaceEvent();

  // Series dinámicas filtradas por tipo seleccionado
  const currentYear = new Date().getFullYear();
  const seriesListQuery = useRaceSeriesList({ kind: seriesKind, season: currentYear });

  const {
    register,
    handleSubmit,
    watch,
    setValue,
    reset,
    formState: { errors, isSubmitting, isDirty },
  } = useForm<CompetitionEventFormValues>({
    resolver: zodResolver(competitionEventSchema),
    defaultValues: {
      series_kind: "cup",
      series_id: 0,
      sequence_number: 1,
      name: "",
      event_date: "",
      location: null,
      status: "scheduled",
    },
  });

  const watchedSequence = watch("sequence_number");
  const watchedLocation = watch("location");
  const watchedName = watch("name");
  const watchedStatus = watch("status");
  const watchedSeriesId = watch("series_id");

  // Precargar en modo edit
  useEffect(() => {
    if (isEdit && eventQuery.data) {
      const ev = eventQuery.data;
      const kind: RaceSeriesKind = ev.is_championship ? "championship" : "cup";
      setSeriesKind(kind);

      const isPredefined = ev.location ? VENUE_KEYS.includes(ev.location) : false;
      setLocationMode(isPredefined ? "predefined" : "custom");

      if (kind === "cup") {
        reset({
          series_kind: "cup",
          series_id: ev.series_id,
          sequence_number: ev.sequence_number,
          name: ev.name,
          event_date: ev.event_date,
          location: ev.location ?? null,
          status: ev.status,
        });
      } else {
        reset({
          series_kind: "championship",
          series_id: ev.series_id,
          sequence_number: undefined,
          name: ev.name,
          event_date: ev.event_date,
          location: ev.location ?? null,
          status: ev.status,
        });
      }
    }
  }, [isEdit, eventQuery.data, reset]);

  // Sincronizar series_kind en el formulario al cambiar el selector externo
  function handleKindChange(newKind: RaceSeriesKind) {
    setSeriesKind(newKind);
    setShowCreateSeries(false);
    // Reset serie y número al cambiar de tipo
    if (newKind === "cup") {
      reset((current) => ({
        ...current,
        series_kind: "cup",
        series_id: 0,
        sequence_number: 1,
      }));
    } else {
      reset((current) => ({
        ...current,
        series_kind: "championship",
        series_id: 0,
        sequence_number: undefined,
      }));
    }
  }

  // Auto-completar altitud cuando cambia la sede
  useEffect(() => {
    if (watchedLocation && VENUE_ALTITUDES[watchedLocation]) {
      setComputedAltitude(VENUE_ALTITUDES[watchedLocation] ?? null);
    } else {
      setComputedAltitude(null);
    }
  }, [watchedLocation]);

  // Auto-sugerir nombre si está vacío (solo copa)
  useEffect(() => {
    if (seriesKind !== "cup") return;
    if (!watchedName && watchedSequence && watchedLocation) {
      const suggested = `Válida ${watchedSequence} · ${watchedLocation}`;
      setValue("name", suggested, { shouldDirty: true });
    }
  }, [seriesKind, watchedSequence, watchedLocation, watchedName, setValue]);

  // Auto-sugerir nombre para campeonato
  useEffect(() => {
    if (seriesKind !== "championship") return;
    if (!watchedName && watchedLocation) {
      const series = seriesListQuery.data?.items.find((s) => s.id === watchedSeriesId);
      if (series) {
        setValue("name", `${series.name} · ${watchedLocation}`, { shouldDirty: true });
      }
    }
  }, [seriesKind, watchedLocation, watchedName, watchedSeriesId, seriesListQuery.data, setValue]);

  function buildCreatePayload(values: CompetitionEventFormValues) {
    if (values.series_kind === "cup") {
      return {
        series_id: values.series_id,
        sequence_number: values.sequence_number,
        name: values.name,
        event_date: values.event_date,
        location: values.location || null,
        status: values.status,
        create_calendar_event: createCalendarEvent,
      };
    }
    // championship: omitir sequence_number; backend lo fuerza a 1
    return {
      series_id: values.series_id,
      name: values.name,
      event_date: values.event_date,
      location: values.location || null,
      status: values.status,
      create_calendar_event: createCalendarEvent,
    };
  }

  function buildUpdatePayload(values: CompetitionEventFormValues) {
    if (values.series_kind === "cup") {
      return {
        name: values.name,
        event_date: values.event_date,
        location: values.location ?? null,
        sequence_number: values.sequence_number,
        status: values.status,
      };
    }
    // championship: no enviar sequence_number
    return {
      name: values.name,
      event_date: values.event_date,
      location: values.location ?? null,
      status: values.status,
    };
  }

  function handleSubmitError(err: unknown) {
    const msg = getRaceEventErrorMessage(err);
    if (
      typeof err === "object" &&
      err !== null &&
      (err as { response?: { status?: number } }).response?.status === 409
    ) {
      const detail =
        (err as { response?: { data?: { detail?: string } } }).response?.data?.detail ?? "";
      // Championship single-event guard
      if (detail.includes("campeonato") || detail.includes("único evento")) {
        setGlobalError(detail);
      } else {
        setSeqError(
          "Ya existe una válida con este número en la temporada. Elige otro número.",
        );
      }
    } else {
      setGlobalError(msg);
    }
  }

  function onSubmit(values: CompetitionEventFormValues) {
    setGlobalError(null);
    setSeqError(null);

    if (!isEdit) {
      createMutation.mutate(
        { body: buildCreatePayload(values) },
        {
          onSuccess: (created) => {
            const dest = returnTo ?? `/competitions/${created.id}`;
            navigate(dest);
          },
          onError: handleSubmitError,
        },
      );
      return;
    }

    if (!eventId) return;

    updateMutation.mutate(
      { id: eventId, body: buildUpdatePayload(values) },
      {
        onSuccess: () => {
          const dest = returnTo ?? `/competitions/${eventId}`;
          navigate(dest);
        },
        onError: handleSubmitError,
      },
    );
  }

  function handleCancel() {
    if (isDirty) {
      if (!window.confirm("Tienes cambios sin guardar. ¿Salir sin guardar?")) return;
    }
    if (returnTo) {
      navigate(returnTo);
      return;
    }
    navigate(isEdit && eventId ? `/competitions/${eventId}` : "/competitions");
  }

  // ── Loading en modo edit ──────────────────────────────────────────────────

  if (isEdit && eventQuery.isLoading) {
    return (
      <section className="max-w-2xl mx-auto space-y-4">
        <div className="h-8 w-60 animate-pulse rounded bg-light-gray" />
        <div className="h-64 animate-pulse rounded-xl bg-light-gray" />
      </section>
    );
  }

  if (isEdit && eventQuery.isError) {
    return (
      <section className="max-w-2xl mx-auto space-y-4">
        <h1
          className="text-2xl text-charcoal"
          style={{ fontFamily: "'Cal Sans', system-ui, sans-serif", fontWeight: 600 }}
        >
          Editar competencia
        </h1>
        <p className="text-sm text-red-700">No se pudo cargar la competencia.</p>
        <Link
          to="/competitions"
          className="text-sm font-medium text-charcoal transition-opacity hover:opacity-70"
        >
          Volver a la lista
        </Link>
      </section>
    );
  }

  const isPending = createMutation.isPending || updateMutation.isPending;
  const showCancelledAlert =
    isEdit && watchedStatus === "cancelled" && eventQuery.data?.status !== "cancelled";

  // Helper para describir el estado del picker de series
  const seriesItems = seriesListQuery.data?.items ?? [];
  const seriesLoading = seriesListQuery.isLoading;
  const seriesError = seriesListQuery.isError;
  const seriesEmpty = !seriesLoading && !seriesError && seriesItems.length === 0;

  const kindLabel = seriesKind === "cup" ? "copa" : "campeonato";

  return (
    <section className="max-w-2xl mx-auto space-y-5">
      {/* Header */}
      <div className="flex items-start justify-between gap-3">
        <div>
          <h1
            className="text-2xl text-charcoal"
            style={{ fontFamily: "'Cal Sans', system-ui, sans-serif", fontWeight: 600 }}
          >
            {isEdit ? "Editar competencia" : "Nueva competencia"}
          </h1>
          <p className="mt-0.5 text-sm text-mid-gray">
            {isEdit
              ? "Actualiza los metadatos de la competencia."
              : "Registra una nueva competencia en el sistema."}
          </p>
        </div>
        <button
          type="button"
          onClick={handleCancel}
          className="rounded-lg bg-white px-3 py-2 text-sm font-medium text-mid-gray transition-opacity hover:opacity-70 min-h-[44px]"
          style={{ boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" }}
        >
          Cancelar
        </button>
      </div>

      {/* Banner si cambia a cancelada */}
      {showCancelledAlert && (
        <div
          className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900"
          role="note"
        >
          El evento permanecerá en el histórico pero no aparecerá como activo.
        </div>
      )}

      <form
        onSubmit={(e) => {
          void handleSubmit(onSubmit)(e);
        }}
        noValidate
        className="space-y-5"
      >
        {/* Sección 1: Identificación */}
        <div className={sectionClass} style={sectionStyle}>
          <h2 className="text-base font-semibold text-charcoal">Identificación</h2>

          {/* Tipo de competencia */}
          <div>
            <label htmlFor="competition-kind" className={labelClass}>
              Tipo de competencia
            </label>
            <select
              id="competition-kind"
              value={seriesKind}
              onChange={(e) => handleKindChange(e.target.value as RaceSeriesKind)}
              disabled={isEdit}
              className={`${inputClass} ${isEdit ? "bg-light-gray cursor-not-allowed" : ""}`}
              style={inputStyle}
              aria-label="Tipo de competencia"
            >
              {COMPETITION_TYPE_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
            {isEdit && (
              <p className="mt-1 text-xs text-mid-gray">
                El tipo de competencia no se puede cambiar en modo edición.
              </p>
            )}
          </div>

          {/* Serie — picker dinámico */}
          <div>
            <label htmlFor="series-id" className={labelClass}>
              Serie
            </label>

            {/* Loading state */}
            {seriesLoading && (
              <div className="mt-1 flex items-center gap-2 rounded-lg bg-light-gray px-3 py-2 text-sm text-mid-gray min-h-[44px]">
                <Loader2 size={14} className="animate-spin" aria-hidden="true" />
                Cargando series…
              </div>
            )}

            {/* Error state */}
            {seriesError && !seriesLoading && (
              <div
                className="mt-1 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700"
                role="alert"
              >
                No se pudieron cargar las series. Recarga la página.
              </div>
            )}

            {/* Empty state */}
            {seriesEmpty && (
              <div className="mt-1 rounded-lg border border-amber-100 bg-amber-50 px-3 py-2 text-xs text-amber-800">
                No hay series de {kindLabel} para {currentYear}.
                {seriesKind === "championship" && (
                  <button
                    type="button"
                    onClick={() => setShowCreateSeries(true)}
                    className="ml-1 font-semibold underline hover:no-underline"
                  >
                    Crear una nueva serie
                  </button>
                )}
              </div>
            )}

            {/* Select when loaded */}
            {!seriesLoading && !seriesError && seriesItems.length > 0 && (
              <select
                id="series-id"
                {...register("series_id", { valueAsNumber: true })}
                className={inputClass}
                style={inputStyle}
                aria-invalid={!!(errors as { series_id?: { message?: string } }).series_id}
              >
                <option value={0} disabled>
                  Selecciona una serie…
                </option>
                {seriesItems.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name}
                    {s.organizer ? ` — ${s.organizer}` : ""}
                    {s.event_count > 0 ? ` (${s.event_count} ${seriesKind === "cup" ? "válidas" : "evento"})` : ""}
                  </option>
                ))}
              </select>
            )}

            {/* Crear serie de campeonato inline */}
            {seriesKind === "championship" && !seriesLoading && !seriesError && (
              <div className="mt-2">
                {!showCreateSeries ? (
                  <button
                    type="button"
                    onClick={() => setShowCreateSeries(true)}
                    className="text-xs font-medium text-blue-700 hover:underline"
                  >
                    + Crear nueva serie de campeonato
                  </button>
                ) : (
                  <CreateChampionshipSeriesForm
                    season={currentYear}
                    onCreated={(seriesId) => {
                      setValue("series_id", seriesId, { shouldDirty: true });
                      setShowCreateSeries(false);
                    }}
                  />
                )}
              </div>
            )}

            {(errors as { series_id?: { message?: string } }).series_id && (
              <p className={errorClass}>
                {(errors as { series_id?: { message?: string } }).series_id?.message}
              </p>
            )}
          </div>

          {/* Número de válida — solo para copa */}
          {seriesKind === "cup" && (
            <div>
              <label htmlFor="sequence-number" className={labelClass}>
                Número de válida
              </label>
              <select
                id="sequence-number"
                {...register("sequence_number", { valueAsNumber: true })}
                className={inputClass}
                style={inputStyle}
                aria-invalid={
                  !!(errors as { sequence_number?: { message?: string } }).sequence_number ||
                  !!seqError
                }
                aria-describedby={
                  (errors as { sequence_number?: { message?: string } }).sequence_number || seqError
                    ? "sequence-number-error"
                    : undefined
                }
              >
                {VALIDA_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
              {((errors as { sequence_number?: { message?: string } }).sequence_number ||
                seqError) && (
                <p id="sequence-number-error" className={errorClass}>
                  {seqError ??
                    (errors as { sequence_number?: { message?: string } }).sequence_number
                      ?.message}
                </p>
              )}
            </div>
          )}

          {/* Nombre */}
          <div>
            <label htmlFor="event-name" className={labelClass}>
              Nombre
            </label>
            <input
              id="event-name"
              type="text"
              placeholder={
                seriesKind === "cup"
                  ? "Ej: Válida 1 · Sevilla"
                  : "Ej: Campeonato Departamental · Ginebra"
              }
              {...register("name")}
              className={inputClass}
              style={inputStyle}
              aria-invalid={!!errors.name}
              aria-describedby={errors.name ? "event-name-error" : undefined}
            />
            {errors.name && (
              <p id="event-name-error" className={errorClass}>
                {errors.name.message}
              </p>
            )}
            <p className="mt-1 text-xs text-mid-gray">
              Si está vacío, se auto-sugiere al elegir sede.
            </p>
          </div>
        </div>

        {/* Sección 2: Logística */}
        <div className={sectionClass} style={sectionStyle}>
          <h2 className="text-base font-semibold text-charcoal">Logística</h2>

          {/* Fecha */}
          <div>
            <label htmlFor="event-date" className={labelClass}>
              Fecha
            </label>
            <input
              id="event-date"
              type="date"
              {...register("event_date")}
              className={inputClass}
              style={inputStyle}
              aria-invalid={!!errors.event_date}
              aria-describedby={errors.event_date ? "event-date-error" : undefined}
            />
            {errors.event_date && (
              <p id="event-date-error" className={errorClass}>
                {errors.event_date.message}
              </p>
            )}
          </div>

          {/* Sede */}
          <div>
            <label htmlFor="event-location" className={labelClass}>
              Sede{" "}
              <span className="font-normal text-mid-gray">(opcional)</span>
            </label>
            {locationMode === "predefined" ? (
              <div className="flex gap-2">
                <select
                  id="event-location"
                  className={`${inputClass} flex-1`}
                  style={inputStyle}
                  value={watchedLocation ?? ""}
                  onChange={(e) => {
                    const val = e.target.value;
                    setValue("location", val || null, { shouldDirty: true });
                    setAltitudeEditable(false);
                  }}
                >
                  <option value="">Selecciona una sede…</option>
                  {VENUE_KEYS.map((venue) => (
                    <option key={venue} value={venue}>
                      {venue} ({VENUE_ALTITUDES[venue]} msnm)
                    </option>
                  ))}
                </select>
                <button
                  type="button"
                  onClick={() => {
                    setLocationMode("custom");
                    setValue("location", null, { shouldDirty: true });
                  }}
                  className="shrink-0 rounded-lg bg-white px-3 py-2 text-xs font-medium text-mid-gray transition-opacity hover:opacity-70 min-h-[44px]"
                  style={inputStyle}
                >
                  Otra sede
                </button>
              </div>
            ) : (
              <div className="flex gap-2">
                <input
                  id="event-location"
                  type="text"
                  placeholder="Nombre de la sede"
                  {...register("location")}
                  className={`${inputClass} flex-1`}
                  style={inputStyle}
                  aria-invalid={!!errors.location}
                />
                <button
                  type="button"
                  onClick={() => {
                    setLocationMode("predefined");
                    setValue("location", null, { shouldDirty: true });
                  }}
                  className="shrink-0 rounded-lg bg-white px-3 py-2 text-xs font-medium text-mid-gray transition-opacity hover:opacity-70 min-h-[44px]"
                  style={inputStyle}
                >
                  Del catálogo
                </button>
              </div>
            )}
            {errors.location && (
              <p className={errorClass}>{errors.location.message}</p>
            )}
          </div>

          {/* Altitud — readonly por default, auto-completada */}
          {computedAltitude !== null && (
            <div>
              <div className="flex items-center justify-between">
                <label className={labelClass}>
                  Altitud (msnm)
                  <span className="ml-2 text-xs font-normal text-mid-gray">
                    (auto-completada)
                  </span>
                </label>
                {!altitudeEditable && (
                  <button
                    type="button"
                    onClick={() => setAltitudeEditable(true)}
                    className="text-xs font-medium text-charcoal transition-opacity hover:opacity-70"
                  >
                    Editar manualmente
                  </button>
                )}
              </div>
              <input
                type="number"
                value={computedAltitude}
                readOnly={!altitudeEditable}
                onChange={(e) => setComputedAltitude(Number(e.target.value))}
                className={`mt-1 w-full rounded-lg px-3 py-2 text-sm text-charcoal outline-none min-h-[44px] ${
                  altitudeEditable
                    ? "bg-white transition-shadow focus:ring-2 focus:ring-blue-500/40"
                    : "bg-light-gray cursor-not-allowed"
                }`}
                style={inputStyle}
                aria-label="Altitud en metros sobre el nivel del mar"
              />
              <p className="mt-1 text-xs text-mid-gray">
                Las condiciones climáticas (altitud, temperatura, etc.) se
                registran en detalle desde la página de la competencia.
              </p>
            </div>
          )}
        </div>

        {/* Sección 3: Estado */}
        <div className={sectionClass} style={sectionStyle}>
          <h2 className="text-base font-semibold text-charcoal">Estado</h2>
          <div>
            <label htmlFor="event-status" className={labelClass}>
              Estado de la competencia
            </label>
            <select
              id="event-status"
              {...register("status")}
              className={inputClass}
              style={inputStyle}
              aria-invalid={!!errors.status}
            >
              {STATUS_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
            {errors.status && (
              <p className={errorClass}>{errors.status.message}</p>
            )}
          </div>
        </div>

        {/* Sección 4: Calendario (solo en create) — FR-024 */}
        {!isEdit && (
          <div className={sectionClass} style={sectionStyle}>
            <h2 className="text-base font-semibold text-charcoal">Calendario</h2>
            <label className="flex cursor-pointer items-start gap-2.5 text-sm text-charcoal">
              <input
                type="checkbox"
                checked={createCalendarEvent}
                onChange={(e) => setCreateCalendarEvent(e.target.checked)}
                className="mt-0.5 h-4 w-4 rounded border-mid-gray"
                data-testid="create-calendar-event-checkbox"
              />
              <span>
                Crear evento en el calendario del club
                <span className="mt-0.5 block text-xs font-normal text-mid-gray">
                  Se creará un evento ligado automáticamente. Si luego cambias
                  fecha, nombre o sede, el calendario se actualizará de forma
                  automática. Puedes asociar un evento existente más tarde desde
                  el detalle de la competencia.
                </span>
              </span>
            </label>
          </div>
        )}

        {/* Error global */}
        {globalError && (
          <p
            className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700"
            role="alert"
            aria-live="assertive"
          >
            {globalError}
          </p>
        )}

        {/* Botones */}
        <div className="flex justify-end gap-3">
          <button
            type="button"
            onClick={handleCancel}
            className="rounded-lg bg-white px-4 py-2 text-sm font-medium text-charcoal transition-opacity hover:opacity-70 min-h-[44px]"
            style={{ boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" }}
          >
            Cancelar
          </button>
          <button
            type="submit"
            disabled={isPending || isSubmitting}
            className="rounded-lg bg-charcoal px-5 py-2 text-sm font-medium text-white transition-opacity hover:opacity-70 disabled:opacity-50 min-h-[44px]"
            style={{ boxShadow: "rgba(255, 255, 255, 0.15) 0px 2px 0px inset" }}
          >
            {isPending || isSubmitting
              ? "Guardando…"
              : isEdit
                ? "Guardar cambios"
                : "Crear competencia"}
          </button>
        </div>
      </form>
    </section>
  );
}
