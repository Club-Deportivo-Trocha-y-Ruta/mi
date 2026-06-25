/**
 * SessionAssembler — arma una sesión de técnica con ejercicios en tres segmentos
 * (calentamiento / principal / vuelta_calma) más los campos de la sesión (US3 / T030).
 *
 * El componente es un formulario RHF completo que:
 *  - Expone tres listas de ejercicios ordenables (drag-free: botones subir/bajar)
 *  - Permite agregar ejercicios desde un picker inline por segmento
 *  - Recopila los metadatos de la sesión (fecha, hora, duración, lugar, foco, objetivos)
 *  - Permite seleccionar los atletas convocados (multi-check)
 *  - Valida con Zod antes de llamar al callback onSubmit
 *
 * El padre (SessionBuilderPage) provee la lista de ejercicios disponibles,
 * la lista de atletas y el callback de envío.
 *
 * WCAG: targets mínimos 48×48; labels explícitas; role="status" en loading;
 * error de campo con aria-describedby; avisos via role="alert".
 */

import { useCallback, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import type {
  AssembleSessionInput,
  ExerciseListItem,
  SessionItemInput,
  SessionSegment,
} from "@/types/technique.types";
import type { AthleteOut } from "@/types/athlete.types";

// ---------------------------------------------------------------------------
// Zod schema — session metadata fields only (items added separately)
// ---------------------------------------------------------------------------

const sessionMetaSchema = z.object({
  scheduled_date: z
    .string()
    .min(1, "Selecciona la fecha de la sesión"),
  scheduled_start_time: z
    .string()
    .min(1, "Indica la hora de inicio")
    .regex(/^\d{2}:\d{2}$/, "Formato HH:MM"),
  duration_min: z
    .number({ error: "Ingresa la duración en minutos" })
    .int()
    .min(10, "Mínimo 10 minutos")
    .max(240, "Máximo 240 minutos"),
  location: z.string().min(1, "Indica el lugar de la sesión"),
  technical_focus: z.string().min(1, "Indica el foco técnico"),
  objectives: z.string().min(1, "Describe los objetivos"),
});

type SessionMetaValues = z.infer<typeof sessionMetaSchema>;

// ---------------------------------------------------------------------------
// Label maps
// ---------------------------------------------------------------------------

const SEGMENT_LABEL: Record<SessionSegment, string> = {
  calentamiento: "Calentamiento",
  principal: "Principal",
  vuelta_calma: "Vuelta a la calma",
};

const SEGMENT_COLOR: Record<SessionSegment, string> = {
  calentamiento: "bg-yellow-50 border-yellow-200",
  principal: "bg-blue-50 border-blue-200",
  vuelta_calma: "bg-green-50 border-green-200",
};

const SEGMENTS: SessionSegment[] = ["calentamiento", "principal", "vuelta_calma"];

// ---------------------------------------------------------------------------
// Per-segment item list (local state, not RHF)
// ---------------------------------------------------------------------------

interface SegmentItem {
  exercise_id: number;
  name: string;
}

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface SessionAssemblerProps {
  /** Full exercise list from the catalog. */
  exercises: ExerciseListItem[];
  /** All club athletes (for convocados multi-select). */
  athletes: AthleteOut[];
  /** Called with the assembled payload when form is valid and items non-empty. */
  onSubmit: (input: AssembleSessionInput) => void;
  /** True while the assemble mutation is pending. */
  isPending: boolean;
  /** Optional error message to display below the submit button. */
  errorMessage?: string | null;
}

// ---------------------------------------------------------------------------
// Small sub-component — SegmentSection
// ---------------------------------------------------------------------------

interface SegmentSectionProps {
  segment: SessionSegment;
  items: SegmentItem[];
  exercises: ExerciseListItem[];
  onAdd: (segment: SessionSegment, exerciseId: number) => void;
  onRemove: (segment: SessionSegment, exerciseId: number) => void;
  onMove: (segment: SessionSegment, index: number, direction: -1 | 1) => void;
}

function SegmentSection({
  segment,
  items,
  exercises,
  onAdd,
  onRemove,
  onMove,
}: SegmentSectionProps) {
  const [pickerValue, setPickerValue] = useState("");

  const addedIds = new Set(items.map((i) => i.exercise_id));
  const available = exercises.filter((ex) => !addedIds.has(ex.id));

  function handleAdd() {
    const id = Number(pickerValue);
    if (!id) return;
    onAdd(segment, id);
    setPickerValue("");
  }

  const pickerId = `picker-${segment}`;
  const labelId = `label-${segment}`;

  return (
    <div
      className={`rounded-xl border p-4 ${SEGMENT_COLOR[segment]}`}
      aria-labelledby={labelId}
    >
      <h3
        id={labelId}
        className="mb-3 text-sm font-semibold text-slate-800"
      >
        {SEGMENT_LABEL[segment]}
        {items.length > 0 && (
          <Badge variant="secondary" className="ml-2 text-xs">
            {items.length}
          </Badge>
        )}
      </h3>

      {/* Ordered exercise list */}
      {items.length === 0 ? (
        <p className="mb-3 text-xs text-slate-400 italic">
          Sin ejercicios. Agrega desde el selector.
        </p>
      ) : (
        <ol className="mb-3 space-y-2" aria-label={`Ejercicios de ${SEGMENT_LABEL[segment]}`}>
          {items.map((item, idx) => (
            <li
              key={item.exercise_id}
              className="flex items-center gap-2 rounded-lg border border-white bg-white px-3 py-2 shadow-sm"
            >
              {/* Position */}
              <span
                className="w-5 shrink-0 text-center text-xs font-semibold text-slate-400"
                aria-label={`Posición ${idx + 1}`}
              >
                {idx + 1}
              </span>

              {/* Name */}
              <span className="min-w-0 flex-1 text-sm text-slate-800 truncate">
                {item.name}
              </span>

              {/* Move up */}
              <button
                type="button"
                aria-label={`Subir ${item.name}`}
                disabled={idx === 0}
                onClick={() => onMove(segment, idx, -1)}
                className="min-h-12 min-w-12 flex items-center justify-center rounded text-slate-400 hover:text-slate-700 disabled:opacity-30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50"
              >
                <svg
                  aria-hidden="true"
                  xmlns="http://www.w3.org/2000/svg"
                  width="16"
                  height="16"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <path d="M18 15l-6-6-6 6" />
                </svg>
              </button>

              {/* Move down */}
              <button
                type="button"
                aria-label={`Bajar ${item.name}`}
                disabled={idx === items.length - 1}
                onClick={() => onMove(segment, idx, 1)}
                className="min-h-12 min-w-12 flex items-center justify-center rounded text-slate-400 hover:text-slate-700 disabled:opacity-30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50"
              >
                <svg
                  aria-hidden="true"
                  xmlns="http://www.w3.org/2000/svg"
                  width="16"
                  height="16"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <path d="M6 9l6 6 6-6" />
                </svg>
              </button>

              {/* Remove */}
              <button
                type="button"
                aria-label={`Quitar ${item.name}`}
                onClick={() => onRemove(segment, item.exercise_id)}
                className="min-h-12 min-w-12 flex items-center justify-center rounded text-slate-400 hover:text-red-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-400/50"
              >
                <svg
                  aria-hidden="true"
                  xmlns="http://www.w3.org/2000/svg"
                  width="16"
                  height="16"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <line x1="18" y1="6" x2="6" y2="18" />
                  <line x1="6" y1="6" x2="18" y2="18" />
                </svg>
              </button>
            </li>
          ))}
        </ol>
      )}

      {/* Picker row */}
      <div className="flex gap-2">
        <label htmlFor={pickerId} className="sr-only">
          Agregar ejercicio a {SEGMENT_LABEL[segment]}
        </label>
        <select
          id={pickerId}
          value={pickerValue}
          onChange={(e) => setPickerValue(e.target.value)}
          className="min-h-12 flex-1 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-primary"
        >
          <option value="">— Selecciona un ejercicio —</option>
          {available.map((ex) => (
            <option key={ex.id} value={String(ex.id)}>
              {ex.name}
            </option>
          ))}
        </select>
        <Button
          type="button"
          variant="outline"
          size="default"
          disabled={!pickerValue}
          onClick={handleAdd}
          className="shrink-0"
        >
          Agregar
        </Button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function SessionAssembler({
  exercises,
  athletes,
  onSubmit,
  isPending,
  errorMessage,
}: SessionAssemblerProps) {
  // Session items per segment (local state — not server state)
  const [segmentItems, setSegmentItems] = useState<
    Record<SessionSegment, SegmentItem[]>
  >({
    calentamiento: [],
    principal: [],
    vuelta_calma: [],
  });

  // Convocados selection (local state)
  const [selectedAthletes, setSelectedAthletes] = useState<Set<number>>(new Set());

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<SessionMetaValues>({
    resolver: zodResolver(sessionMetaSchema),
    defaultValues: {
      scheduled_date: "",
      scheduled_start_time: "",
      duration_min: 60,
      location: "",
      technical_focus: "",
      objectives: "",
    },
  });

  // ---------------------------------------------------------------------------
  // Segment item mutations
  // ---------------------------------------------------------------------------

  const handleAdd = useCallback(
    (segment: SessionSegment, exerciseId: number) => {
      const exercise = exercises.find((ex) => ex.id === exerciseId);
      if (!exercise) return;
      setSegmentItems((prev) => ({
        ...prev,
        [segment]: [...prev[segment], { exercise_id: exerciseId, name: exercise.name }],
      }));
    },
    [exercises],
  );

  const handleRemove = useCallback(
    (segment: SessionSegment, exerciseId: number) => {
      setSegmentItems((prev) => ({
        ...prev,
        [segment]: prev[segment].filter((i) => i.exercise_id !== exerciseId),
      }));
    },
    [],
  );

  const handleMove = useCallback(
    (segment: SessionSegment, index: number, direction: -1 | 1) => {
      setSegmentItems((prev) => {
        const list = [...prev[segment]];
        const targetIndex = index + direction;
        if (targetIndex < 0 || targetIndex >= list.length) return prev;
        [list[index], list[targetIndex]] = [list[targetIndex], list[index]];
        return { ...prev, [segment]: list };
      });
    },
    [],
  );

  // ---------------------------------------------------------------------------
  // Athlete toggle
  // ---------------------------------------------------------------------------

  function toggleAthlete(id: number) {
    setSelectedAthletes((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }

  // ---------------------------------------------------------------------------
  // Total item count (for submit gate)
  // ---------------------------------------------------------------------------

  const totalItems =
    segmentItems.calentamiento.length +
    segmentItems.principal.length +
    segmentItems.vuelta_calma.length;

  // ---------------------------------------------------------------------------
  // Build API payload and call onSubmit
  // ---------------------------------------------------------------------------

  function buildItems(): SessionItemInput[] {
    const items: SessionItemInput[] = [];
    for (const segment of SEGMENTS) {
      segmentItems[segment].forEach((item, idx) => {
        items.push({
          exercise_id: item.exercise_id,
          segment,
          position: idx + 1,
        });
      });
    }
    return items;
  }

  function handleFormSubmit(values: SessionMetaValues) {
    const items = buildItems();
    if (items.length === 0) return; // guard — button is already disabled

    const payload: AssembleSessionInput = {
      scheduled_date: values.scheduled_date,
      scheduled_start_time: `${values.scheduled_start_time}:00`,
      duration_min: values.duration_min,
      location: values.location,
      technical_focus: values.technical_focus,
      objectives: values.objectives,
      convocados_athlete_ids: Array.from(selectedAthletes),
      items,
    };
    onSubmit(payload);
  }

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <form
      onSubmit={handleSubmit(handleFormSubmit)}
      noValidate
      aria-label="Armar sesión técnica"
    >
      {/* ── Session metadata ── */}
      <Card className="mb-6">
        <CardContent className="py-5">
          <h2 className="mb-4 text-base font-semibold text-slate-900">
            Datos de la sesión
          </h2>

          <div className="grid gap-4 sm:grid-cols-2">
            {/* Fecha */}
            <div>
              <label
                htmlFor="session-date"
                className="mb-1 block text-xs font-medium text-slate-700"
              >
                Fecha
              </label>
              <input
                id="session-date"
                type="date"
                {...register("scheduled_date")}
                aria-describedby={
                  errors.scheduled_date ? "err-date" : undefined
                }
                className="min-h-12 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-primary"
              />
              {errors.scheduled_date && (
                <p id="err-date" role="alert" className="mt-1 text-xs text-red-600">
                  {errors.scheduled_date.message}
                </p>
              )}
            </div>

            {/* Hora de inicio */}
            <div>
              <label
                htmlFor="session-time"
                className="mb-1 block text-xs font-medium text-slate-700"
              >
                Hora de inicio
              </label>
              <input
                id="session-time"
                type="time"
                {...register("scheduled_start_time")}
                aria-describedby={
                  errors.scheduled_start_time ? "err-time" : undefined
                }
                className="min-h-12 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-primary"
              />
              {errors.scheduled_start_time && (
                <p id="err-time" role="alert" className="mt-1 text-xs text-red-600">
                  {errors.scheduled_start_time.message}
                </p>
              )}
            </div>

            {/* Duración */}
            <div>
              <label
                htmlFor="session-duration"
                className="mb-1 block text-xs font-medium text-slate-700"
              >
                Duración (minutos)
              </label>
              <input
                id="session-duration"
                type="number"
                inputMode="numeric"
                min={10}
                max={240}
                {...register("duration_min", { valueAsNumber: true })}
                aria-describedby={
                  errors.duration_min ? "err-duration" : undefined
                }
                className="min-h-12 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-primary"
              />
              {errors.duration_min && (
                <p id="err-duration" role="alert" className="mt-1 text-xs text-red-600">
                  {errors.duration_min.message}
                </p>
              )}
            </div>

            {/* Lugar */}
            <div>
              <label
                htmlFor="session-location"
                className="mb-1 block text-xs font-medium text-slate-700"
              >
                Lugar
              </label>
              <input
                id="session-location"
                type="text"
                {...register("location")}
                placeholder="Ej: Cancha del club"
                aria-describedby={
                  errors.location ? "err-location" : undefined
                }
                className="min-h-12 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-primary"
              />
              {errors.location && (
                <p id="err-location" role="alert" className="mt-1 text-xs text-red-600">
                  {errors.location.message}
                </p>
              )}
            </div>

            {/* Foco técnico */}
            <div className="sm:col-span-2">
              <label
                htmlFor="session-focus"
                className="mb-1 block text-xs font-medium text-slate-700"
              >
                Foco técnico
              </label>
              <input
                id="session-focus"
                type="text"
                {...register("technical_focus")}
                placeholder="Ej: Fundamentos de equilibrio y frenado"
                aria-describedby={
                  errors.technical_focus ? "err-focus" : undefined
                }
                className="min-h-12 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-primary"
              />
              {errors.technical_focus && (
                <p id="err-focus" role="alert" className="mt-1 text-xs text-red-600">
                  {errors.technical_focus.message}
                </p>
              )}
            </div>

            {/* Objetivos */}
            <div className="sm:col-span-2">
              <label
                htmlFor="session-objectives"
                className="mb-1 block text-xs font-medium text-slate-700"
              >
                Objetivos
              </label>
              <textarea
                id="session-objectives"
                rows={3}
                {...register("objectives")}
                placeholder="Describe lo que los deportistas deberán lograr al finalizar la sesión"
                aria-describedby={
                  errors.objectives ? "err-objectives" : undefined
                }
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-primary resize-none"
              />
              {errors.objectives && (
                <p id="err-objectives" role="alert" className="mt-1 text-xs text-red-600">
                  {errors.objectives.message}
                </p>
              )}
            </div>
          </div>
        </CardContent>
      </Card>

      {/* ── Exercise segments ── */}
      <div className="mb-6 space-y-4">
        <h2 className="text-base font-semibold text-slate-900">
          Ejercicios por segmento
        </h2>
        {SEGMENTS.map((segment) => (
          <SegmentSection
            key={segment}
            segment={segment}
            items={segmentItems[segment]}
            exercises={exercises}
            onAdd={handleAdd}
            onRemove={handleRemove}
            onMove={handleMove}
          />
        ))}
        {totalItems === 0 && (
          <p role="status" className="text-xs text-red-600">
            Agrega al menos un ejercicio para poder guardar la sesión.
          </p>
        )}
      </div>

      {/* ── Convocados ── */}
      {athletes.length > 0 && (
        <Card className="mb-6">
          <CardContent className="py-5">
            <h2 className="mb-3 text-base font-semibold text-slate-900">
              Convocados
              {selectedAthletes.size > 0 && (
                <Badge variant="secondary" className="ml-2 text-xs">
                  {selectedAthletes.size} seleccionados
                </Badge>
              )}
            </h2>
            <div
              role="group"
              aria-label="Seleccionar deportistas convocados"
              className="flex flex-wrap gap-2"
            >
              {athletes.map((athlete) => {
                const selected = selectedAthletes.has(athlete.id);
                return (
                  <button
                    key={athlete.id}
                    type="button"
                    aria-pressed={selected}
                    onClick={() => toggleAthlete(athlete.id)}
                    className={[
                      "min-h-12 rounded-lg border px-3 py-2 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50",
                      selected
                        ? "border-primary bg-primary text-white"
                        : "border-slate-300 bg-white text-slate-700 hover:border-slate-400",
                    ].join(" ")}
                  >
                    {athlete.first_name} {athlete.last_name}
                  </button>
                );
              })}
            </div>
          </CardContent>
        </Card>
      )}

      {/* ── Submit ── */}
      {errorMessage && (
        <p role="alert" className="mb-3 text-sm text-red-600">
          {errorMessage}
        </p>
      )}

      <Button
        type="submit"
        size="lg"
        disabled={isPending || totalItems === 0}
        className="w-full sm:w-auto"
      >
        {isPending ? "Guardando sesión…" : "Guardar sesión técnica"}
      </Button>
    </form>
  );
}

export default SessionAssembler;
