/**
 * BlockAssembler — arma un bloque de fuerza con ejercicios ordenables, cada
 * uno con duración/repeticiones editables, y un indicador en vivo del total
 * estimado frente a la meta de duración del bloque (feature 021 / T025).
 *
 * FR-009 / research D2: el umbral de 30 minutos es una **regla de producto
 * del club** (configurable vía `duration_target_min`, default 30), no un
 * límite clínico ni científicamente derivado. El indicador es puramente
 * informativo — nunca bloquea el guardado:
 *   - dentro   (< meta)  → verde  (badge "success")
 *   - al límite (= meta) → ámbar (badge "warning")
 *   - por encima (> meta) → ámbar (badge "warning"), no bloqueante
 *
 * Guardrail de franja de edad (FR-011, US3, T031): el backend valida las
 * entradas solo al guardar (`POST/PUT /blocks`), devolviendo 422
 * `AGE_BAND_GUARDRAIL` para la primera entrada no anulada cuyo ejercicio no
 * es apto para `target_age_band`. Al guardar, si `onSubmit` rechaza con ese
 * error, se abre `AgeBandGuardrailDialog` en vez del error de validación
 * genérico; "Confirmar anulación" marca esa entrada con
 * `is_age_override: true` (+ `override_note`) y reintenta el guardado —
 * repite hasta que no queden entradas sin resolver. "Cancelar" cierra el
 * diálogo sin persistir nada — el bloque en construcción queda sin cambios.
 * Las entradas con `is_age_override: true` se marcan visualmente con una
 * insignia ámbar con tooltip.
 *
 * Mirror de `components/technique/SessionAssembler.tsx` (feature 018):
 * formulario RHF para metadatos + lista ordenable en estado local (no RHF)
 * para las entradas del bloque.
 */
import { useCallback, useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { AlertTriangle } from "lucide-react";

import { extractAgeBandGuardrail } from "@/api/strength";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { AgeBandGuardrailDialog } from "./AgeBandGuardrailDialog";
import type { StrengthExerciseListItem } from "./ExerciseCard";
import {
  STRENGTH_AGE_BAND_LABEL,
  type StrengthAgeBand,
} from "./ExerciseCard";

// ---------------------------------------------------------------------------
// Zod schema — block metadata fields only (entries managed separately)
// ---------------------------------------------------------------------------

const DEFAULT_DURATION_TARGET_MIN = 30;

const blockMetaSchema = z.object({
  name: z
    .string()
    .min(1, "Ingresa un nombre para el bloque")
    .max(120, "Máximo 120 caracteres"),
  target_age_band: z.enum(["10-12", "13-15"], {
    error: "Selecciona la franja de edad objetivo",
  }),
  duration_target_min: z
    .number({ error: "Ingresa la meta de duración en minutos" })
    .int()
    .min(5, "Mínimo 5 minutos")
    .max(120, "Máximo 120 minutos"),
});

type BlockMetaValues = z.infer<typeof blockMetaSchema>;

// ---------------------------------------------------------------------------
// Entry shapes
// ---------------------------------------------------------------------------

/** Entrada local del bloque en construcción — estado del componente, no RHF. */
export interface BlockAssemblerEntry {
  exercise_id: number;
  name: string;
  duration_min: number;
  reps: string;
  /** Anulación registrada del guardrail de franja de edad (FR-011, US3). */
  is_age_override?: boolean;
  override_note?: string | null;
}

/** Payload que se envía al padre al enviar el formulario (mirror POST /blocks). */
export interface BlockAssemblerSubmitInput {
  name: string;
  target_age_band: StrengthAgeBand;
  duration_target_min: number;
  entries: Array<{
    exercise_id: number;
    position: number;
    duration_min: number;
    reps?: string;
    is_age_override: boolean;
    override_note?: string;
  }>;
}

export type DurationIndicatorStatus = "within" | "at" | "over";

/** Calcula el estado del indicador. Puro para poder testear los límites 29/30/31. */
export function computeDurationStatus(
  totalMin: number,
  targetMin: number,
): DurationIndicatorStatus {
  if (totalMin > targetMin) return "over";
  if (totalMin === targetMin) return "at";
  return "within";
}

/**
 * Encuentra la primera entrada (en orden) cuyo ejercicio no es apto para
 * `targetAgeBand` y que no fue marcada con `is_age_override` — el mismo
 * algoritmo, mismo orden, primera coincidencia, que
 * `_enforce_age_band_guardrail` en el backend (FR-011). Se usa para
 * identificar de forma determinística qué entrada disparó el 422
 * `AGE_BAND_GUARDRAIL` al guardar, sin depender de parsear el mensaje en
 * español del backend. Función pura, testeable de forma aislada.
 */
export function findFirstAgeBandViolation(
  entries: BlockAssemblerEntry[],
  exercises: StrengthExerciseListItem[],
  targetAgeBand: StrengthAgeBand,
): { entry: BlockAssemblerEntry; exercise: StrengthExerciseListItem } | null {
  for (const entry of entries) {
    if (entry.is_age_override) continue;
    const exercise = exercises.find((ex) => ex.id === entry.exercise_id);
    if (!exercise) continue;
    if (!exercise.age_bands.includes(targetAgeBand)) {
      return { entry, exercise };
    }
  }
  return null;
}

/** Arma el payload de guardado (mirror POST/PUT /blocks) a partir de los metadatos + entradas actuales. */
function buildSubmitPayload(
  values: BlockMetaValues,
  currentEntries: BlockAssemblerEntry[],
): BlockAssemblerSubmitInput {
  return {
    name: values.name,
    target_age_band: values.target_age_band,
    duration_target_min: values.duration_target_min,
    entries: currentEntries.map((entry, idx) => ({
      exercise_id: entry.exercise_id,
      position: idx,
      duration_min: entry.duration_min,
      reps: entry.reps || undefined,
      is_age_override: entry.is_age_override ?? false,
      override_note: entry.override_note ?? undefined,
    })),
  };
}

const INDICATOR_COPY: Record<
  DurationIndicatorStatus,
  { label: string; variant: "success" | "warning" }
> = {
  within: { label: "Dentro de la meta", variant: "success" },
  at: { label: "En el límite de la meta", variant: "warning" },
  over: { label: "Por encima de la meta", variant: "warning" },
};

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface BlockAssemblerProps {
  /** Catálogo completo de ejercicios disponibles para agregar al bloque. */
  exercises: StrengthExerciseListItem[];
  /**
   * Llamado con el payload armado cuando el formulario es válido y hay >=1
   * entrada. Puede devolver una promesa que rechace con el error de la
   * mutación (p.ej. Axios) — si rechaza con 422 `AGE_BAND_GUARDRAIL`, este
   * componente abre `AgeBandGuardrailDialog` en vez de propagar el error.
   */
  onSubmit: (input: BlockAssemblerSubmitInput) => void | Promise<void>;
  /** true mientras la mutación de guardado está en curso. */
  isPending: boolean;
  /** Mensaje de error opcional a mostrar debajo del botón de envío. */
  errorMessage?: string | null;
  /** Valores iniciales — modo edición de un bloque existente. */
  defaultValues?: Partial<BlockMetaValues>;
  /** Entradas iniciales — modo edición de un bloque existente. */
  defaultEntries?: BlockAssemblerEntry[];
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function BlockAssembler({
  exercises,
  onSubmit,
  isPending,
  errorMessage,
  defaultValues,
  defaultEntries,
}: BlockAssemblerProps) {
  const [entries, setEntries] = useState<BlockAssemblerEntry[]>(
    defaultEntries ?? [],
  );
  const [pickerValue, setPickerValue] = useState("");

  const {
    register,
    handleSubmit,
    watch,
    formState: { errors },
  } = useForm<BlockMetaValues>({
    resolver: zodResolver(blockMetaSchema),
    defaultValues: {
      name: defaultValues?.name ?? "",
      target_age_band: defaultValues?.target_age_band ?? "10-12",
      duration_target_min:
        defaultValues?.duration_target_min ?? DEFAULT_DURATION_TARGET_MIN,
    },
  });

  const durationTargetMin = watch("duration_target_min");

  // ---------------------------------------------------------------------------
  // Running total + indicator
  // ---------------------------------------------------------------------------

  const totalDurationMin = useMemo(
    () => entries.reduce((sum, entry) => sum + (entry.duration_min || 0), 0),
    [entries],
  );

  const durationStatus = computeDurationStatus(
    totalDurationMin,
    Number.isFinite(durationTargetMin)
      ? durationTargetMin
      : DEFAULT_DURATION_TARGET_MIN,
  );
  const indicatorCopy = INDICATOR_COPY[durationStatus];

  // ---------------------------------------------------------------------------
  // Entry mutations
  // ---------------------------------------------------------------------------

  const addedIds = useMemo(
    () => new Set(entries.map((e) => e.exercise_id)),
    [entries],
  );
  const availableExercises = exercises.filter((ex) => !addedIds.has(ex.id));

  const handleAdd = useCallback(() => {
    const id = Number(pickerValue);
    if (!id) return;
    const exercise = exercises.find((ex) => ex.id === id);
    if (!exercise) return;
    setEntries((prev) => [
      ...prev,
      {
        exercise_id: exercise.id,
        name: exercise.name,
        duration_min: exercise.suggested_duration_min,
        reps: exercise.suggested_reps,
        is_age_override: false,
        override_note: null,
      },
    ]);
    setPickerValue("");
  }, [pickerValue, exercises]);

  const handleRemove = useCallback((exerciseId: number) => {
    setEntries((prev) => prev.filter((e) => e.exercise_id !== exerciseId));
  }, []);

  const handleMove = useCallback((index: number, direction: -1 | 1) => {
    setEntries((prev) => {
      const list = [...prev];
      const targetIndex = index + direction;
      if (targetIndex < 0 || targetIndex >= list.length) return prev;
      [list[index], list[targetIndex]] = [list[targetIndex], list[index]];
      return list;
    });
  }, []);

  const handleDurationChange = useCallback(
    (exerciseId: number, value: number) => {
      setEntries((prev) =>
        prev.map((e) =>
          e.exercise_id === exerciseId
            ? { ...e, duration_min: Number.isFinite(value) ? value : 0 }
            : e,
        ),
      );
    },
    [],
  );

  const handleRepsChange = useCallback((exerciseId: number, value: string) => {
    setEntries((prev) =>
      prev.map((e) =>
        e.exercise_id === exerciseId ? { ...e, reps: value } : e,
      ),
    );
  }, []);

  // ---------------------------------------------------------------------------
  // Submit + age-band guardrail (FR-011, US3, T031)
  // ---------------------------------------------------------------------------

  const [guardrailState, setGuardrailState] = useState<{
    values: BlockMetaValues;
    entry: BlockAssemblerEntry;
    exercise: StrengthExerciseListItem;
  } | null>(null);

  const submitWithEntries = useCallback(
    async (values: BlockMetaValues, currentEntries: BlockAssemblerEntry[]) => {
      const payload = buildSubmitPayload(values, currentEntries);
      try {
        await onSubmit(payload);
      } catch (err) {
        const guardrail = extractAgeBandGuardrail(err);
        if (!guardrail) return; // otro error — el padre ya lo mostró vía errorMessage
        const violation = findFirstAgeBandViolation(
          currentEntries,
          exercises,
          values.target_age_band,
        );
        if (!violation) return; // no debería pasar: el backend usa el mismo algoritmo
        setGuardrailState({ values, ...violation });
      }
    },
    [onSubmit, exercises],
  );

  async function handleFormSubmit(values: BlockMetaValues) {
    if (entries.length === 0) return; // guard — button is already disabled
    await submitWithEntries(values, entries);
  }

  const handleConfirmOverride = useCallback(
    (overrideNote: string | null) => {
      if (!guardrailState) return;
      const { values, entry } = guardrailState;
      const updatedEntries = entries.map((e) =>
        e.exercise_id === entry.exercise_id
          ? { ...e, is_age_override: true, override_note: overrideNote }
          : e,
      );
      setEntries(updatedEntries);
      setGuardrailState(null);
      void submitWithEntries(values, updatedEntries);
    },
    [guardrailState, entries, submitWithEntries],
  );

  function handleGuardrailOpenChange(open: boolean) {
    // Cancelar / Escape / botón "X" — cierra sin persistir: el bloque en
    // construcción no cambia.
    if (!open) setGuardrailState(null);
  }

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <TooltipProvider delayDuration={200}>
    <form
      onSubmit={handleSubmit(handleFormSubmit)}
      noValidate
      aria-label="Armar bloque de fuerza"
    >
      {/* ── Block metadata ── */}
      <Card className="mb-6">
        <CardContent className="py-5">
          <h2 className="mb-4 text-base font-semibold text-slate-900">
            Datos del bloque
          </h2>

          <div className="grid gap-4 sm:grid-cols-2">
            {/* Nombre */}
            <div className="sm:col-span-2">
              <label
                htmlFor="block-name"
                className="mb-1 block text-xs font-medium text-slate-700"
              >
                Nombre del bloque
              </label>
              <input
                id="block-name"
                type="text"
                {...register("name")}
                placeholder="Ej: Fuerza de tren inferior — pretemporada"
                aria-describedby={errors.name ? "err-name" : undefined}
                className="min-h-12 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-primary"
              />
              {errors.name && (
                <p id="err-name" role="alert" className="mt-1 text-xs text-red-600">
                  {errors.name.message}
                </p>
              )}
            </div>

            {/* Franja de edad objetivo */}
            <div>
              <label
                htmlFor="block-age-band"
                className="mb-1 block text-xs font-medium text-slate-700"
              >
                Franja de edad objetivo
              </label>
              <select
                id="block-age-band"
                {...register("target_age_band")}
                aria-describedby={
                  errors.target_age_band ? "err-age-band" : undefined
                }
                className="min-h-12 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-primary"
              >
                <option value="10-12">
                  {STRENGTH_AGE_BAND_LABEL["10-12"]} años
                </option>
                <option value="13-15">
                  {STRENGTH_AGE_BAND_LABEL["13-15"]} años
                </option>
              </select>
              {errors.target_age_band && (
                <p
                  id="err-age-band"
                  role="alert"
                  className="mt-1 text-xs text-red-600"
                >
                  {errors.target_age_band.message}
                </p>
              )}
            </div>

            {/* Meta de duración */}
            <div>
              <label
                htmlFor="block-duration-target"
                className="mb-1 block text-xs font-medium text-slate-700"
              >
                Meta de duración (minutos)
              </label>
              <input
                id="block-duration-target"
                type="number"
                inputMode="numeric"
                min={5}
                max={120}
                {...register("duration_target_min", { valueAsNumber: true })}
                aria-describedby="block-duration-target-hint"
                className="min-h-12 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-primary"
              />
              <p
                id="block-duration-target-hint"
                className="mt-1 text-xs text-slate-400"
              >
                Guía de diseño de sesión del club (por defecto 30 min), no un
                límite clínico.
              </p>
              {errors.duration_target_min && (
                <p role="alert" className="mt-1 text-xs text-red-600">
                  {errors.duration_target_min.message}
                </p>
              )}
            </div>
          </div>
        </CardContent>
      </Card>

      {/* ── Running total indicator ── */}
      <div
        role="status"
        aria-live="polite"
        className="mb-6 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-200 bg-white p-4"
      >
        <div>
          <p className="text-sm font-semibold text-slate-900">
            Total estimado del bloque:{" "}
            <span data-testid="block-total-minutes">{totalDurationMin}</span>{" "}
            de {Number.isFinite(durationTargetMin) ? durationTargetMin : DEFAULT_DURATION_TARGET_MIN} min
          </p>
          <p className="mt-0.5 text-xs text-slate-500">
            Los 30 minutos son la guía de diseño de sesión del club, no un
            límite clínico: superarla es solo una señal para revisar el
            bloque, no un bloqueo.
          </p>
        </div>
        <Badge variant={indicatorCopy.variant} data-testid="duration-indicator">
          {indicatorCopy.label}
        </Badge>
      </div>

      {/* ── Entries ── */}
      <Card className="mb-6">
        <CardContent className="py-5">
          <h2 className="mb-3 text-base font-semibold text-slate-900">
            Ejercicios del bloque
            {entries.length > 0 && (
              <Badge variant="secondary" className="ml-2 text-xs">
                {entries.length}
              </Badge>
            )}
          </h2>

          {entries.length === 0 ? (
            <p className="mb-3 text-xs text-slate-400 italic">
              Sin ejercicios. Agrega desde el selector.
            </p>
          ) : (
            <ol className="mb-4 space-y-2" aria-label="Ejercicios del bloque">
              {entries.map((entry, idx) => (
                <li
                  key={entry.exercise_id}
                  className="flex flex-wrap items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 shadow-sm"
                >
                  {/* Position */}
                  <span
                    className="w-5 shrink-0 text-center text-xs font-semibold text-slate-400"
                    aria-label={`Posición ${idx + 1}`}
                  >
                    {idx + 1}
                  </span>

                  {/* Name */}
                  <span className="min-w-[10rem] flex-1 text-sm text-slate-800">
                    {entry.name}
                  </span>

                  {/* Insignia de anulación de franja de edad (FR-011, US3) */}
                  {entry.is_age_override && (
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <span>
                          <Badge
                            variant="warning"
                            className="gap-1"
                            data-testid={`age-override-badge-${entry.exercise_id}`}
                          >
                            <AlertTriangle size={10} aria-hidden="true" />
                            Excepción de edad
                          </Badge>
                        </span>
                      </TooltipTrigger>
                      <TooltipContent side="top">
                        {entry.override_note?.trim()
                          ? entry.override_note
                          : "Agregado fuera de la franja de edad objetivo del bloque, sin nota adicional."}
                      </TooltipContent>
                    </Tooltip>
                  )}

                  {/* Duration editor */}
                  <div className="flex items-center gap-1">
                    <label
                      htmlFor={`entry-duration-${entry.exercise_id}`}
                      className="sr-only"
                    >
                      Duración de {entry.name} (minutos)
                    </label>
                    <input
                      id={`entry-duration-${entry.exercise_id}`}
                      type="number"
                      inputMode="numeric"
                      min={0}
                      max={60}
                      value={entry.duration_min}
                      onChange={(e) =>
                        handleDurationChange(
                          entry.exercise_id,
                          e.target.valueAsNumber,
                        )
                      }
                      className="min-h-12 w-20 rounded-lg border border-slate-300 px-2 py-1 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-primary"
                    />
                    <span className="text-xs text-slate-400">min</span>
                  </div>

                  {/* Reps editor */}
                  <div className="flex items-center gap-1">
                    <label
                      htmlFor={`entry-reps-${entry.exercise_id}`}
                      className="sr-only"
                    >
                      Repeticiones de {entry.name}
                    </label>
                    <input
                      id={`entry-reps-${entry.exercise_id}`}
                      type="text"
                      value={entry.reps}
                      onChange={(e) =>
                        handleRepsChange(entry.exercise_id, e.target.value)
                      }
                      placeholder="Ej: 3×10"
                      className="min-h-12 w-24 rounded-lg border border-slate-300 px-2 py-1 text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-primary"
                    />
                  </div>

                  {/* Move up */}
                  <button
                    type="button"
                    aria-label={`Subir ${entry.name}`}
                    disabled={idx === 0}
                    onClick={() => handleMove(idx, -1)}
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
                    aria-label={`Bajar ${entry.name}`}
                    disabled={idx === entries.length - 1}
                    onClick={() => handleMove(idx, 1)}
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
                    aria-label={`Quitar ${entry.name}`}
                    onClick={() => handleRemove(entry.exercise_id)}
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
            <label htmlFor="block-exercise-picker" className="sr-only">
              Agregar ejercicio al bloque
            </label>
            <select
              id="block-exercise-picker"
              value={pickerValue}
              onChange={(e) => setPickerValue(e.target.value)}
              className="min-h-12 flex-1 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-primary"
            >
              <option value="">— Selecciona un ejercicio —</option>
              {availableExercises.map((ex) => (
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

          {entries.length === 0 && (
            <p role="status" className="mt-3 text-xs text-red-600">
              Agrega al menos un ejercicio para poder guardar el bloque.
            </p>
          )}
        </CardContent>
      </Card>

      {/* ── Submit ── */}
      {errorMessage && (
        <p role="alert" className="mb-3 text-sm text-red-600">
          {errorMessage}
        </p>
      )}

      <Button
        type="submit"
        size="lg"
        disabled={isPending || entries.length === 0}
        className="w-full sm:w-auto"
      >
        {isPending ? "Guardando bloque…" : "Guardar bloque de fuerza"}
      </Button>

      {/* ── Guardrail de franja de edad (FR-011, US3) ── */}
      {guardrailState && (
        <AgeBandGuardrailDialog
          open
          onOpenChange={handleGuardrailOpenChange}
          exerciseName={guardrailState.exercise.name}
          exerciseAgeBands={guardrailState.exercise.age_bands}
          targetAgeBand={guardrailState.values.target_age_band}
          onConfirmOverride={handleConfirmOverride}
          isPending={isPending}
        />
      )}
    </form>
    </TooltipProvider>
  );
}

export default BlockAssembler;
