/**
 * CompetitionFormPage — formulario de creación y edición de una competencia.
 *
 * mode="create" → ruta /competitions/new
 * mode="edit"   → ruta /competitions/:id/edit
 *
 * Campos:
 *   - Serie (hardcoded Copa Valle por ahora — CF5+ debería consumir endpoint)
 *   - Número de válida (select 1-7 + CD + "Otro")
 *   - Nombre (auto-sugerido como "Válida N · Sede" si vacío)
 *   - Fecha (input nativo)
 *   - Sede (select del catálogo VENUE_ALTITUDES + "Otra")
 *   - Altitud (readonly autocompletada; botón para editar manualmente)
 *   - Estado (select)
 *   - Campeonato departamental (checkbox — solo visible si sequence_number≠99,
 *     porque 99=CD ya implica is_championship=true)
 *
 * Notas de diseño:
 *   - En modo create, las condiciones climáticas NO se incluyen aquí.
 *     El coach las ingresa después vía RaceConditionsCard en la detail page.
 *   - En modo edit, PATCH solo envía los campos de RaceEventUpdate (extra=forbid).
 *   - Error 422 con sequence_number duplicado muestra mensaje inline.
 *   - Soporta ?returnTo= para flujo "crear desde calendario".
 */
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";

import {
  competitionEventSchema,
  COPA_VALLE_SERIES,
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
import { VENUE_ALTITUDES } from "@/types/raceEvents.types";

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
// Página
// ---------------------------------------------------------------------------

export function CompetitionFormPage({ mode }: CompetitionFormPageProps) {
  const navigate = useNavigate();
  const { id } = useParams();
  const [searchParams] = useSearchParams();
  // Sanitizar returnTo: solo se permiten paths internos (inician con /).
  // Rechaza URLs absolutas o protocolos para evitar open-redirect.
  const rawReturnTo = searchParams.get("returnTo");
  const returnTo =
    rawReturnTo && /^\/[^/\\]/.test(rawReturnTo) ? rawReturnTo : null;

  const eventId = id ? Number(id) : null;
  const isEdit = mode === "edit";

  // En modo edit, cargamos el evento para precargar el formulario
  const eventQuery = useRaceEvent(isEdit ? eventId : null);

  const createMutation = useCreateRaceEvent();
  const updateMutation = useUpdateRaceEvent();

  // Estado de la sede: "predefined" | "custom"
  const [locationMode, setLocationMode] = useState<"predefined" | "custom">("predefined");
  // Controla si la altitud es editable manualmente
  const [altitudeEditable, setAltitudeEditable] = useState(false);
  // Mensaje de error global (ej. 409 duplicado)
  const [globalError, setGlobalError] = useState<string | null>(null);
  // Error específico de sequence_number (409 duplicado)
  const [seqError, setSeqError] = useState<string | null>(null);
  // Altitud calculada automáticamente (para mostrar en campo readonly)
  const [computedAltitude, setComputedAltitude] = useState<number | null>(null);

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
      series_id: COPA_VALLE_SERIES.id,
      sequence_number: 1,
      name: "",
      event_date: "",
      location: null,
      is_championship: false,
      status: "scheduled",
    },
  });

  const watchedSequence = watch("sequence_number");
  const watchedLocation = watch("location");
  const watchedName = watch("name");
  const watchedStatus = watch("status");

  // Precargar en modo edit
  useEffect(() => {
    if (isEdit && eventQuery.data) {
      const ev = eventQuery.data;
      // Detectar si la sede es del catálogo o personalizada
      const isPredefined = ev.location ? VENUE_KEYS.includes(ev.location) : false;
      setLocationMode(isPredefined ? "predefined" : "custom");

      reset({
        series_id: ev.series_id,
        sequence_number: ev.sequence_number,
        name: ev.name,
        event_date: ev.event_date,
        location: ev.location ?? null,
        is_championship: ev.is_championship,
        status: ev.status,
      });
    }
  }, [isEdit, eventQuery.data, reset]);

  // Auto-completar altitud cuando cambia la sede
  useEffect(() => {
    if (watchedLocation && VENUE_ALTITUDES[watchedLocation]) {
      setComputedAltitude(VENUE_ALTITUDES[watchedLocation] ?? null);
    } else {
      setComputedAltitude(null);
    }
  }, [watchedLocation]);

  // Cuando el número de válida es 99 (CD), forzar is_championship=true
  useEffect(() => {
    if (watchedSequence === 99) {
      setValue("is_championship", true, { shouldDirty: true });
    }
  }, [watchedSequence, setValue]);

  // Auto-sugerir nombre si está vacío
  useEffect(() => {
    if (!watchedName && watchedSequence && watchedLocation) {
      const label =
        watchedSequence === 99
          ? "Campeonato Departamental"
          : `Válida ${watchedSequence}`;
      const suggested = `${label} · ${watchedLocation}`;
      setValue("name", suggested, { shouldDirty: true });
    }
  }, [watchedSequence, watchedLocation, watchedName, setValue]);

  function buildPayload(values: CompetitionEventFormValues) {
    return {
      series_id: values.series_id,
      sequence_number: values.sequence_number,
      name: values.name,
      event_date: values.event_date,
      location: values.location || null,
      is_championship: values.is_championship,
      status: values.status,
    };
  }

  async function onSubmit(values: CompetitionEventFormValues) {
    setGlobalError(null);
    setSeqError(null);

    if (!isEdit) {
      createMutation.mutate(
        { body: buildPayload(values) },
        {
          onSuccess: (created) => {
            const dest = returnTo ?? `/competitions/${created.id}`;
            navigate(dest);
          },
          onError: (err) => {
            const msg = getRaceEventErrorMessage(err);
            // 409 duplicado de sequence_number
            if (
              typeof err === "object" &&
              err !== null &&
              (err as { response?: { status?: number } }).response?.status === 409
            ) {
              setSeqError(
                "Ya existe una válida con este número en la temporada. Elige otro número.",
              );
            } else {
              // 422 y resto → muestra detail real del backend si está
              // disponible (más útil que un mensaje genérico).
              setGlobalError(msg);
            }
          },
        },
      );
      return;
    }

    if (!eventId) return;

    updateMutation.mutate(
      {
        id: eventId,
        body: {
          name: values.name,
          event_date: values.event_date,
          location: values.location ?? null,
          sequence_number: values.sequence_number,
          status: values.status,
          is_championship: values.is_championship,
        },
      },
      {
        onSuccess: () => {
          const dest = returnTo ?? `/competitions/${eventId}`;
          navigate(dest);
        },
        onError: (err) => {
          const msg = getRaceEventErrorMessage(err);
          if (
            typeof err === "object" &&
            err !== null &&
            (err as { response?: { status?: number } }).response?.status === 409
          ) {
            setSeqError(
              "Ya existe una válida con este número en la temporada. Elige otro número.",
            );
          } else {
            setGlobalError(msg);
          }
        },
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

  // Alerta si cambia status a cancelado
  const showCancelledAlert = isEdit && watchedStatus === "cancelled" && eventQuery.data?.status !== "cancelled";

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
              ? "Actualiza los metadatos de la válida."
              : "Registra una nueva válida en el sistema."}
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

          {/* Serie */}
          <div>
            <label htmlFor="series-id" className={labelClass}>
              Serie
            </label>
            <input
              id="series-id"
              type="text"
              value={COPA_VALLE_SERIES.name}
              readOnly
              className={`${inputClass} bg-light-gray cursor-not-allowed`}
              style={inputStyle}
            />
            {/* Campo oculto para el valor real */}
            <input type="hidden" {...register("series_id", { valueAsNumber: true })} />
            <p className="mt-1 text-xs text-mid-gray">
              Serie activa del club. CF5+ permitirá seleccionar otras series.
            </p>
          </div>

          {/* Número de válida */}
          <div>
            <label htmlFor="sequence-number" className={labelClass}>
              Número de válida
            </label>
            <select
              id="sequence-number"
              {...register("sequence_number", { valueAsNumber: true })}
              className={inputClass}
              style={inputStyle}
              aria-invalid={!!(errors.sequence_number || seqError)}
              aria-describedby={
                errors.sequence_number || seqError ? "sequence-number-error" : undefined
              }
            >
              {VALIDA_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
            {(errors.sequence_number || seqError) && (
              <p id="sequence-number-error" className={errorClass}>
                {seqError ?? errors.sequence_number?.message}
              </p>
            )}
          </div>

          {/* Nombre */}
          <div>
            <label htmlFor="event-name" className={labelClass}>
              Nombre
            </label>
            <input
              id="event-name"
              type="text"
              placeholder="Ej: Válida 1 · Sevilla"
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
              Si está vacío, se auto-sugiere al elegir número y sede.
            </p>
          </div>

          {/* Campeonato Departamental — solo si no es sequence_number=99 */}
          {watchedSequence !== 99 && (
            <label className="flex cursor-pointer items-center gap-2 text-sm text-charcoal">
              <input
                type="checkbox"
                {...register("is_championship")}
                className="h-4 w-4 rounded border-mid-gray"
              />
              Campeonato Departamental (CD)
            </label>
          )}
          {watchedSequence === 99 && (
            <p className="text-xs text-mid-gray italic">
              Número 99 se reserva automáticamente para el Campeonato Departamental.
            </p>
          )}
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
                registran en detalle desde la página de la válida.
              </p>
            </div>
          )}
        </div>

        {/* Sección 3: Estado */}
        <div className={sectionClass} style={sectionStyle}>
          <h2 className="text-base font-semibold text-charcoal">Estado</h2>
          <div>
            <label htmlFor="event-status" className={labelClass}>
              Estado de la válida
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
