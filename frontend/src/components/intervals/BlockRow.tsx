/**
 * BlockRow — fila editable de un bloque de la estructura de intervalos
 * (feature 026, T013). Es una fila controlada por RHF: registra sus inputs con
 * el `register` del formulario padre (`StructureEditor`) usando la ruta
 * `blocks.${index}.<campo>`. No tiene estado propio de datos — todo vive en el
 * field array del padre.
 *
 * Dimensiones objetivo (D2/FR-005): SOLO zona de frecuencia cardíaca + cadencia.
 * No existe columna/control de potencia (watts) para ninguna categoría.
 *
 * Invariantes reflejadas en la UI:
 *   - Cadencia objetivo mínima 60 rpm (FR-004): el input tiene `min={60}` y el
 *     error 422 `cadence_below_minimum` del backend se muestra inline aquí.
 *   - Grupo repetido (FR-002): al activar "Parte de un grupo repetido" se
 *     muestran los inputs de número de grupo + repeticiones (`repeat_count >= 2`).
 *     El error `invalid_repeat_group` se muestra inline en repeticiones.
 *
 * A11y: cada control tiene `<label>` asociado, objetivos táctiles >= 48px
 * (min-h-12 / min-w-12), errores con `role="alert"` y `aria-describedby`.
 *
 * Mirror de `components/strength/BlockAssembler.tsx` (fila del bloque de fuerza).
 */
import { ArrowDown, ArrowUp, Repeat, Trash2 } from "lucide-react";
import type { UseFormRegister } from "react-hook-form";
import type { z } from "zod";

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { intervalStructureUpdateInputSchema } from "@/schemas/intervals.schema";
import type {
  HrZone,
  IntervalBlockType,
} from "@/types/intervals.types";

/**
 * Forma de datos del formulario del editor — derivada del mismo schema que usa
 * `StructureEditor` (fuente única de verdad), de modo que las rutas de
 * `register` queden fuertemente tipadas sin acoplar los dos archivos entre sí.
 */
type StructureFormValues = z.input<typeof intervalStructureUpdateInputSchema>;

// ---------------------------------------------------------------------------
// Etiquetas en español neutro (Colombia)
// ---------------------------------------------------------------------------

/** Etiqueta visible de cada tipo de bloque (FR-002). */
export const BLOCK_TYPE_LABEL: Record<IntervalBlockType, string> = {
  warmup: "Calentamiento",
  work: "Trabajo",
  recovery: "Recuperación",
  cooldown: "Enfriamiento",
};

const BLOCK_TYPE_OPTIONS: readonly IntervalBlockType[] = [
  "warmup",
  "work",
  "recovery",
  "cooldown",
];

/** Etiqueta visible de cada zona de FC (Z1..Z5). Sin objetivo de potencia (D2). */
export const HR_ZONE_LABEL: Record<HrZone, string> = {
  Z1: "Z1 — Muy suave",
  Z2: "Z2 — Suave",
  Z3: "Z3 — Moderada",
  Z4: "Z4 — Fuerte",
  Z5: "Z5 — Máxima",
};

const HR_ZONE_OPTIONS: readonly HrZone[] = ["Z1", "Z2", "Z3", "Z4", "Z5"];

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

/**
 * Mensajes de error ya resueltos (strings) por campo del bloque. El padre los
 * extrae de `formState.errors.blocks[index]` para desacoplar esta fila de los
 * tipos internos de error de RHF.
 */
export interface BlockRowErrors {
  block_type?: string;
  duration_s?: string;
  target_zone?: string;
  target_cadence_rpm?: string;
  repeat_group?: string;
  repeat_count?: string;
}

export interface BlockRowProps {
  /** Índice de la fila dentro del field array `blocks` del padre. */
  index: number;
  /** `register` del formulario padre — para enlazar los inputs por ruta. */
  register: UseFormRegister<StructureFormValues>;
  /** Errores por campo (mensajes ya resueltos), opcional. */
  errors?: BlockRowErrors;
  /** `true` si el bloque forma parte de un grupo repetido (muestra sus inputs). */
  grouped: boolean;
  /** Alterna la pertenencia del bloque a un grupo repetido. */
  onToggleGroup: (checked: boolean) => void;
  isFirst: boolean;
  isLast: boolean;
  onMoveUp: () => void;
  onMoveDown: () => void;
  onRemove: () => void;
}

// ---------------------------------------------------------------------------
// Estilos compartidos
// ---------------------------------------------------------------------------

const CONTROL_CLASS = cn(
  "min-h-12 w-full rounded-lg border border-border-gray bg-white px-3 py-2",
  "text-sm text-charcoal placeholder:text-mid-gray transition-colors",
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50",
);

const ICON_BUTTON_CLASS = cn(
  "min-h-12 min-w-12 flex items-center justify-center rounded-lg",
  "text-mid-gray hover:text-charcoal transition-colors",
  "disabled:opacity-30 disabled:hover:text-mid-gray disabled:cursor-not-allowed",
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50",
);

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function BlockRow({
  index,
  register,
  errors,
  grouped,
  onToggleGroup,
  isFirst,
  isLast,
  onMoveUp,
  onMoveDown,
  onRemove,
}: BlockRowProps) {
  const uid = `block-${index}`;
  const typeId = `${uid}-type`;
  const durationId = `${uid}-duration`;
  const zoneId = `${uid}-zone`;
  const cadenceId = `${uid}-cadence`;
  const groupId = `${uid}-repeat-group`;
  const countId = `${uid}-repeat-count`;

  return (
    <li
      className="rounded-xl border border-border-gray bg-white p-3 shadow-sm sm:p-4"
      aria-label={`Bloque ${index + 1}`}
    >
      {/* ── Encabezado: posición + acciones de orden/eliminación ── */}
      <div className="mb-3 flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span
            className="flex h-7 min-w-7 items-center justify-center rounded-full bg-light-gray px-2 text-xs font-semibold text-mid-gray"
            aria-hidden="true"
          >
            {index + 1}
          </span>
          {grouped && (
            <Badge variant="secondary" className="gap-1 text-xs">
              <Repeat size={11} aria-hidden="true" />
              En grupo repetido
            </Badge>
          )}
        </div>

        <div className="flex items-center gap-1">
          <button
            type="button"
            aria-label={`Subir bloque ${index + 1}`}
            disabled={isFirst}
            onClick={onMoveUp}
            className={ICON_BUTTON_CLASS}
          >
            <ArrowUp size={16} aria-hidden="true" />
          </button>
          <button
            type="button"
            aria-label={`Bajar bloque ${index + 1}`}
            disabled={isLast}
            onClick={onMoveDown}
            className={ICON_BUTTON_CLASS}
          >
            <ArrowDown size={16} aria-hidden="true" />
          </button>
          <button
            type="button"
            aria-label={`Quitar bloque ${index + 1}`}
            onClick={onRemove}
            className={cn(ICON_BUTTON_CLASS, "hover:text-red-600")}
          >
            <Trash2 size={16} aria-hidden="true" />
          </button>
        </div>
      </div>

      {/* ── Campos del bloque ── */}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {/* Tipo de bloque */}
        <div>
          <label
            htmlFor={typeId}
            className="mb-1 block text-xs font-medium text-charcoal"
          >
            Tipo
          </label>
          <select
            id={typeId}
            {...register(`blocks.${index}.block_type` as const)}
            aria-invalid={errors?.block_type ? true : undefined}
            aria-describedby={errors?.block_type ? `${typeId}-err` : undefined}
            className={CONTROL_CLASS}
          >
            {BLOCK_TYPE_OPTIONS.map((value) => (
              <option key={value} value={value}>
                {BLOCK_TYPE_LABEL[value]}
              </option>
            ))}
          </select>
          {errors?.block_type && (
            <p id={`${typeId}-err`} role="alert" className="mt-1 text-xs text-red-600">
              {errors.block_type}
            </p>
          )}
        </div>

        {/* Duración (segundos) */}
        <div>
          <label
            htmlFor={durationId}
            className="mb-1 block text-xs font-medium text-charcoal"
          >
            Duración (segundos)
          </label>
          <input
            id={durationId}
            type="number"
            inputMode="numeric"
            min={1}
            step={1}
            {...register(`blocks.${index}.duration_s` as const, {
              valueAsNumber: true,
            })}
            aria-invalid={errors?.duration_s ? true : undefined}
            aria-describedby={errors?.duration_s ? `${durationId}-err` : undefined}
            className={CONTROL_CLASS}
          />
          {errors?.duration_s && (
            <p
              id={`${durationId}-err`}
              role="alert"
              className="mt-1 text-xs text-red-600"
            >
              {errors.duration_s}
            </p>
          )}
        </div>

        {/* Zona de FC objetivo */}
        <div>
          <label
            htmlFor={zoneId}
            className="mb-1 block text-xs font-medium text-charcoal"
          >
            Zona de FC
          </label>
          <select
            id={zoneId}
            {...register(`blocks.${index}.target_zone` as const)}
            aria-invalid={errors?.target_zone ? true : undefined}
            aria-describedby={errors?.target_zone ? `${zoneId}-err` : undefined}
            className={CONTROL_CLASS}
          >
            {HR_ZONE_OPTIONS.map((value) => (
              <option key={value} value={value}>
                {HR_ZONE_LABEL[value]}
              </option>
            ))}
          </select>
          {errors?.target_zone && (
            <p id={`${zoneId}-err`} role="alert" className="mt-1 text-xs text-red-600">
              {errors.target_zone}
            </p>
          )}
        </div>

        {/* Cadencia objetivo (rpm) — mínimo 60 (FR-004) */}
        <div>
          <label
            htmlFor={cadenceId}
            className="mb-1 block text-xs font-medium text-charcoal"
          >
            Cadencia (rpm)
          </label>
          <input
            id={cadenceId}
            type="number"
            inputMode="numeric"
            min={60}
            step={1}
            {...register(`blocks.${index}.target_cadence_rpm` as const, {
              valueAsNumber: true,
            })}
            aria-invalid={errors?.target_cadence_rpm ? true : undefined}
            aria-describedby={cn(
              `${cadenceId}-hint`,
              errors?.target_cadence_rpm ? `${cadenceId}-err` : "",
            ).trim()}
            className={CONTROL_CLASS}
          />
          <p id={`${cadenceId}-hint`} className="mt-1 text-xs text-mid-gray">
            Mínimo 60 rpm, todas las categorías.
          </p>
          {errors?.target_cadence_rpm && (
            <p
              id={`${cadenceId}-err`}
              role="alert"
              className="mt-1 text-xs text-red-600"
            >
              {errors.target_cadence_rpm}
            </p>
          )}
        </div>
      </div>

      {/* ── Grupo repetido (FR-002) ── */}
      <div className="mt-3 border-t border-border-gray pt-3">
        <label className="flex min-h-12 items-center gap-2 text-sm text-charcoal">
          <input
            type="checkbox"
            checked={grouped}
            onChange={(event) => onToggleGroup(event.target.checked)}
            className="h-4 w-4 rounded border-border-gray text-primary focus-visible:ring-2 focus-visible:ring-primary/50"
          />
          Parte de un grupo repetido
        </label>

        {grouped && (
          <div className="mt-2 grid gap-3 sm:grid-cols-2">
            {/* Número de grupo */}
            <div>
              <label
                htmlFor={groupId}
                className="mb-1 block text-xs font-medium text-charcoal"
              >
                Número de grupo
              </label>
              <input
                id={groupId}
                type="number"
                inputMode="numeric"
                min={1}
                step={1}
                {...register(`blocks.${index}.repeat_group` as const, {
                  setValueAs: (value) =>
                    value === "" || value == null ? null : Number(value),
                })}
                aria-invalid={errors?.repeat_group ? true : undefined}
                aria-describedby={`${groupId}-hint`}
                className={CONTROL_CLASS}
              />
              <p id={`${groupId}-hint`} className="mt-1 text-xs text-mid-gray">
                Usá el mismo número en los bloques que se repiten juntos (p. ej.
                trabajo y recuperación).
              </p>
              {errors?.repeat_group && (
                <p role="alert" className="mt-1 text-xs text-red-600">
                  {errors.repeat_group}
                </p>
              )}
            </div>

            {/* Repeticiones */}
            <div>
              <label
                htmlFor={countId}
                className="mb-1 block text-xs font-medium text-charcoal"
              >
                Repeticiones (×N)
              </label>
              <input
                id={countId}
                type="number"
                inputMode="numeric"
                min={2}
                step={1}
                {...register(`blocks.${index}.repeat_count` as const, {
                  setValueAs: (value) =>
                    value === "" || value == null ? null : Number(value),
                })}
                aria-invalid={errors?.repeat_count ? true : undefined}
                aria-describedby={errors?.repeat_count ? `${countId}-err` : undefined}
                className={CONTROL_CLASS}
              />
              {errors?.repeat_count && (
                <p
                  id={`${countId}-err`}
                  role="alert"
                  className="mt-1 text-xs text-red-600"
                >
                  {errors.repeat_count}
                </p>
              )}
            </div>
          </div>
        )}
      </div>
    </li>
  );
}

export default BlockRow;
