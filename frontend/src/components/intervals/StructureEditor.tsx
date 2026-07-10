/**
 * StructureEditor — editor RHF+Zod de la estructura de intervalos de una sesión
 * (feature 026, T013). Permite armar la lista ordenada de bloques
 * (calentamiento / trabajo / recuperación / enfriamiento), cada uno con
 * duración + zona de FC + cadencia objetivo, con soporte de grupos repetidos
 * (agrupar ×N). Cada fila es una `BlockRow`.
 *
 * Validación (fuente única: `schemas/intervals.schema.ts`):
 *   - Cadencia objetivo >= 60 rpm para toda categoría (FR-004).
 *   - `duration_s > 0` en cada bloque.
 *   - Grupos de repetición: `repeat_count >= 2` e idéntico dentro del grupo (FR-002).
 *   - Sin objetivo de potencia/watts (FR-005, D2).
 *
 * Compuerta por edad (FR-006/FR-007) — mismo flujo de reintento que
 * `strength/BlockAssembler.tsx`: `onSubmit` puede rechazar con un error 422 de
 * Axios. Este componente lo inspecciona con `extractIntervalValidationError`:
 *   - `age_gate_confirmation_required` → abre `AgeGateDialog` en modo
 *     "confirmation"; al confirmar, reenvía con `age_gate_confirmed: true`.
 *   - `age_gate_z3_blocked` → abre `AgeGateDialog` en modo "blocked" (bloqueo
 *     duro, sin override) señalando las posiciones a corregir.
 *   - `cadence_below_minimum` / `invalid_repeat_group` → error inline en los
 *     bloques implicados (por `positions`).
 *   - Cualquier otro error lo muestra el padre vía `errorMessage`.
 *
 * A11y / UX (Constitución III): copy en español neutro (Colombia), objetivos
 * táctiles >= 48px, errores localizados inline con `role="alert"`.
 */
import { useCallback, useMemo, useState } from "react";
import { useFieldArray, useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import type { z } from "zod";
import { AlertCircle, Plus } from "lucide-react";

import { extractIntervalValidationError } from "@/api/intervals";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { intervalStructureUpdateInputSchema } from "@/schemas/intervals.schema";
import type {
  IntervalAgeBand,
  IntervalBlockInput,
} from "@/types/intervals.types";
import {
  AgeGateDialog,
  INTERVAL_AGE_BAND_LABEL,
  type AgeGateMode,
} from "./AgeGateDialog";
import { BlockRow, type BlockRowErrors } from "./BlockRow";

// ---------------------------------------------------------------------------
// Tipos del formulario (derivados del schema — fuente única de verdad)
// ---------------------------------------------------------------------------

type StructureFormValues = z.input<typeof intervalStructureUpdateInputSchema>;

/** Payload que se entrega al padre — mismo shape que POST /structures. */
export interface StructureEditorSubmitInput {
  training_session_id: number;
  target_age_band: IntervalAgeBand;
  age_gate_confirmed: boolean;
  blocks: IntervalBlockInput[];
}

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface StructureEditorProps {
  /** Sesión a la que se adjunta la estructura (va en el payload de creación). */
  trainingSessionId: number;
  /**
   * Llamado con el payload armado al enviar. Puede devolver una promesa que
   * rechace con el error de la mutación (Axios). Si rechaza con un 422 de
   * compuerta por edad, este componente abre `AgeGateDialog` en vez de
   * propagar. El padre decide POST (crear) vs PUT (reemplazar).
   */
  onSubmit: (input: StructureEditorSubmitInput) => void | Promise<void>;
  /** `true` mientras la mutación de guardado está en curso. */
  isPending: boolean;
  /** Error genérico (no de compuerta) a mostrar debajo del botón. */
  errorMessage?: string | null;
  /** Valores iniciales — modo edición de una estructura existente. */
  defaultValues?: {
    target_age_band?: IntervalAgeBand;
    blocks?: IntervalBlockInput[];
  };
  /** Texto del botón de envío (por defecto "Guardar estructura"). */
  submitLabel?: string;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Bloque nuevo por defecto (calentamiento Z1, cadencia válida). */
function emptyBlock(position: number): IntervalBlockInput {
  return {
    position,
    block_type: "warmup",
    duration_s: 300,
    target_zone: "Z1",
    target_cadence_rpm: 70,
    repeat_group: null,
    repeat_count: null,
  };
}

/**
 * Duración total estimada de la estructura (aplanada): cada bloque agrupado
 * cuenta `repeat_count` veces; los no agrupados, una vez (misma regla de
 * aplanado que el motor de matching y el instructivo).
 */
export function computeFlattenedDurationS(
  blocks: ReadonlyArray<{
    duration_s?: number | null;
    repeat_group?: number | null;
    repeat_count?: number | null;
  }>,
): number {
  return blocks.reduce((total, block) => {
    const duration = Number(block.duration_s) || 0;
    const times =
      block.repeat_group != null && Number(block.repeat_count) >= 2
        ? Number(block.repeat_count)
        : 1;
    return total + duration * times;
  }, 0);
}

/** Formatea segundos como `mm:ss` (español neutro, para el indicador). */
function formatMmSs(totalSeconds: number): string {
  const safe = Math.max(0, Math.round(totalSeconds));
  const minutes = Math.floor(safe / 60);
  const seconds = safe % 60;
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function StructureEditor({
  trainingSessionId,
  onSubmit,
  isPending,
  errorMessage,
  defaultValues,
  submitLabel = "Guardar estructura",
}: StructureEditorProps) {
  const {
    register,
    handleSubmit,
    control,
    watch,
    setValue,
    setError,
    getValues,
    formState: { errors },
  } = useForm<StructureFormValues>({
    resolver: zodResolver(intervalStructureUpdateInputSchema),
    defaultValues: {
      target_age_band: defaultValues?.target_age_band ?? "13-15",
      age_gate_confirmed: false,
      blocks:
        defaultValues?.blocks && defaultValues.blocks.length > 0
          ? defaultValues.blocks
          : [emptyBlock(1)],
    },
  });

  const { fields, append, remove, move } = useFieldArray({
    control,
    name: "blocks",
  });

  // Se observa el array para el indicador de duración y el estado "agrupado".
  const watchedBlocks = watch("blocks");

  const flattenedDurationS = useMemo(
    () => computeFlattenedDurationS(watchedBlocks ?? []),
    [watchedBlocks],
  );

  // ---------------------------------------------------------------------------
  // Mutaciones de la lista de bloques
  // ---------------------------------------------------------------------------

  const handleAppend = useCallback(() => {
    append(emptyBlock(fields.length + 1));
  }, [append, fields.length]);

  const handleToggleGroup = useCallback(
    (index: number, checked: boolean) => {
      if (checked) {
        setValue(`blocks.${index}.repeat_group`, 1, { shouldDirty: true });
        setValue(`blocks.${index}.repeat_count`, 2, { shouldDirty: true });
      } else {
        setValue(`blocks.${index}.repeat_group`, null, { shouldDirty: true });
        setValue(`blocks.${index}.repeat_count`, null, { shouldDirty: true });
      }
    },
    [setValue],
  );

  // ---------------------------------------------------------------------------
  // Compuerta por edad + envío (FR-006/FR-007)
  // ---------------------------------------------------------------------------

  const [ageGate, setAgeGate] = useState<{
    mode: AgeGateMode;
    message?: string;
    positions?: number[];
  } | null>(null);

  const buildPayload = useCallback(
    (
      values: StructureFormValues,
      ageGateConfirmed: boolean,
    ): StructureEditorSubmitInput => ({
      training_session_id: trainingSessionId,
      target_age_band: values.target_age_band,
      age_gate_confirmed: ageGateConfirmed,
      blocks: (values.blocks ?? []).map((block, idx) => ({
        position: idx + 1,
        block_type: block.block_type,
        duration_s: block.duration_s,
        target_zone: block.target_zone,
        target_cadence_rpm: block.target_cadence_rpm,
        repeat_group: block.repeat_group ?? null,
        repeat_count: block.repeat_count ?? null,
      })),
    }),
    [trainingSessionId],
  );

  /** Traduce posiciones (1-indexadas) del backend a errores inline por fila. */
  const applyInlineValidation = useCallback(
    (code: string, positions?: number[]) => {
      const field =
        code === "cadence_below_minimum"
          ? ("target_cadence_rpm" as const)
          : code === "invalid_repeat_group"
            ? ("repeat_count" as const)
            : null;
      if (!field) return;
      const message =
        field === "target_cadence_rpm"
          ? "La cadencia mínima es 60 rpm para todas las categorías."
          : "Revisá la configuración del grupo de repeticiones.";
      const targets =
        positions && positions.length > 0
          ? positions
          : (watchedBlocks ?? []).map((_, idx) => idx + 1);
      for (const position of targets) {
        const idx = position - 1;
        if (idx < 0) continue;
        setError(`blocks.${idx}.${field}`, { type: "server", message });
      }
    },
    [setError, watchedBlocks],
  );

  const submitValues = useCallback(
    async (values: StructureFormValues, ageGateConfirmed: boolean) => {
      const payload = buildPayload(values, ageGateConfirmed);
      try {
        await onSubmit(payload);
      } catch (err) {
        const validation = extractIntervalValidationError(err);
        if (!validation) return; // otro error — el padre lo muestra vía errorMessage
        if (validation.code === "age_gate_confirmation_required") {
          setAgeGate({ mode: "confirmation", message: validation.message });
          return;
        }
        if (validation.code === "age_gate_z3_blocked") {
          setAgeGate({
            mode: "blocked",
            message: validation.message,
            positions: validation.positions,
          });
          return;
        }
        applyInlineValidation(validation.code, validation.positions);
      }
    },
    [buildPayload, onSubmit, applyInlineValidation],
  );

  const handleValidSubmit = useCallback(
    (values: StructureFormValues) => {
      void submitValues(values, false);
    },
    [submitValues],
  );

  const handleConfirmAgeGate = useCallback(() => {
    setAgeGate(null);
    void submitValues(getValues(), true);
  }, [getValues, submitValues]);

  const handleAgeGateOpenChange = useCallback((open: boolean) => {
    if (!open) setAgeGate(null);
  }, []);

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  const targetAgeBand = watch("target_age_band");

  return (
    <form
      onSubmit={handleSubmit(handleValidSubmit)}
      noValidate
      aria-label="Editor de estructura de intervalos"
    >
      {/* ── Metadatos ── */}
      <Card className="mb-4">
        <CardContent className="py-5">
          <h2 className="mb-4 text-base font-semibold text-slate-900">
            Datos de la estructura
          </h2>
          <div className="max-w-xs">
            <label
              htmlFor="structure-age-band"
              className="mb-1 block text-xs font-medium text-slate-700"
            >
              Categoría objetivo
            </label>
            <select
              id="structure-age-band"
              {...register("target_age_band")}
              className="min-h-12 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50"
            >
              <option value="10-12">
                {INTERVAL_AGE_BAND_LABEL["10-12"]}
              </option>
              <option value="13-15">
                {INTERVAL_AGE_BAND_LABEL["13-15"]}
              </option>
            </select>
            {errors.target_age_band && (
              <p role="alert" className="mt-1 text-xs text-red-600">
                {errors.target_age_band.message}
              </p>
            )}
            <p className="mt-1 text-xs text-slate-400">
              Para la categoría 10 a 12 años solo se permiten zonas suaves (Z1–Z2).
            </p>
          </div>
        </CardContent>
      </Card>

      {/* ── Indicador de duración total ── */}
      <div
        role="status"
        aria-live="polite"
        className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-200 bg-white p-4"
      >
        <p className="text-sm font-semibold text-slate-900">
          Duración total estimada:{" "}
          <span data-testid="structure-total-duration">
            {formatMmSs(flattenedDurationS)}
          </span>{" "}
          min
        </p>
        <Badge variant="secondary" data-testid="structure-block-count">
          {fields.length} {fields.length === 1 ? "bloque" : "bloques"}
        </Badge>
      </div>

      {/* ── Lista de bloques ── */}
      <Card className="mb-4">
        <CardContent className="py-5">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-base font-semibold text-slate-900">
              Bloques de la estructura
            </h2>
          </div>

          {fields.length === 0 ? (
            <p className="mb-3 text-xs italic text-slate-400">
              Sin bloques. Agregá el primero para armar la estructura.
            </p>
          ) : (
            <ol className="mb-4 space-y-3" aria-label="Bloques de la estructura">
              {fields.map((field, index) => {
                const rowErrors = errors.blocks?.[index] as
                  | Record<string, { message?: string } | undefined>
                  | undefined;
                const blockErrors: BlockRowErrors | undefined = rowErrors
                  ? {
                      block_type: rowErrors.block_type?.message,
                      duration_s: rowErrors.duration_s?.message,
                      target_zone: rowErrors.target_zone?.message,
                      target_cadence_rpm: rowErrors.target_cadence_rpm?.message,
                      repeat_group: rowErrors.repeat_group?.message,
                      repeat_count: rowErrors.repeat_count?.message,
                    }
                  : undefined;
                const grouped =
                  (watchedBlocks?.[index]?.repeat_group ?? null) != null;
                return (
                  <BlockRow
                    key={field.id}
                    index={index}
                    register={register}
                    errors={blockErrors}
                    grouped={grouped}
                    onToggleGroup={(checked) =>
                      handleToggleGroup(index, checked)
                    }
                    isFirst={index === 0}
                    isLast={index === fields.length - 1}
                    onMoveUp={() => move(index, index - 1)}
                    onMoveDown={() => move(index, index + 1)}
                    onRemove={() => remove(index)}
                  />
                );
              })}
            </ol>
          )}

          <Button
            type="button"
            variant="outline"
            onClick={handleAppend}
            className="gap-1"
          >
            <Plus size={16} aria-hidden="true" />
            Agregar bloque
          </Button>

          {fields.length === 0 && (
            <p role="status" className="mt-3 text-xs text-red-600">
              Agregá al menos un bloque para poder guardar la estructura.
            </p>
          )}
        </CardContent>
      </Card>

      {/* ── Envío ── */}
      {errorMessage && (
        <p
          role="alert"
          className="mb-3 flex items-center gap-1.5 text-sm text-red-600"
        >
          <AlertCircle size={16} aria-hidden="true" />
          {errorMessage}
        </p>
      )}

      <Button
        type="submit"
        size="lg"
        disabled={isPending || fields.length === 0}
        className="w-full sm:w-auto"
      >
        {isPending ? "Guardando estructura…" : submitLabel}
      </Button>

      {/* ── Compuerta por edad (FR-006/FR-007) ── */}
      {ageGate && (
        <AgeGateDialog
          open
          onOpenChange={handleAgeGateOpenChange}
          mode={ageGate.mode}
          targetAgeBand={targetAgeBand}
          message={ageGate.message}
          positions={ageGate.positions}
          onConfirm={handleConfirmAgeGate}
          isPending={isPending}
        />
      )}
    </form>
  );
}

export default StructureEditor;
