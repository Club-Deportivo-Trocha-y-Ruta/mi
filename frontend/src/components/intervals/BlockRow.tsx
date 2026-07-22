/**
 * BlockRow — fila editable de un bloque de la estructura de intervalos
 * (feature 026, T013; duración mm:ss + bloques libres, feature 034). Es una
 * fila controlada por RHF: registra sus inputs con el `register` del
 * formulario padre (`StructureEditor`) usando la ruta
 * `blocks.${index}.<campo>`. No tiene estado propio de datos — todo vive en el
 * field array del padre; el propio padre deriva `durationType`/`blockType`/
 * `grouped` observando el array (mismo patrón, ver `StructureEditor`).
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
 *   - Duración (feature 034, FR-001/FR-002): entrada en minutos:segundos vía
 *     `MmSsInput` (segundos sigue siendo la unidad almacenada/fuente de verdad).
 *   - Tipo de duración (feature 034, FR-004/FR-005/FR-006): solo calentamiento
 *     y enfriamiento pueden marcarse "Libre — hasta botón de vuelta"; nunca
 *     dentro de un grupo repetido. La compuerta es orden-independiente: si el
 *     bloque ya está agrupado, la opción "Libre" ni se ofrece en el select; si
 *     el bloque ya es libre, el checkbox de grupo se deshabilita. Un bloque
 *     libre nunca lleva duración — zona y cadencia siguen siendo obligatorias.
 *
 * A11y: cada control tiene `<label>` asociado, objetivos táctiles >= 48px
 * (min-h-12 / min-w-12), errores con `role="alert"` y `aria-describedby`.
 *
 * Mirror de `components/strength/BlockAssembler.tsx` (fila del bloque de fuerza).
 */
import { ArrowDown, ArrowUp, Repeat, Trash2 } from "lucide-react";
import { Controller, type Control, type UseFormRegister } from "react-hook-form";
import type { z } from "zod";

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { intervalStructureUpdateInputSchema } from "@/schemas/intervals.schema";
import type {
  HrZone,
  IntervalBlockType,
  IntervalDurationType,
} from "@/types/intervals.types";
import { MmSsInput } from "./MmSsInput";

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

/** Etiqueta visible de cada tipo de duración (feature 034, FR-004). */
export const DURATION_TYPE_LABEL: Record<IntervalDurationType, string> = {
  fixed: "Tiempo fijo",
  open_lap: "Libre — hasta botón de vuelta",
};

/** Solo calentamiento/enfriamiento pueden ser libres (FR-005). */
function canBeOpenEnded(blockType: IntervalBlockType): boolean {
  return blockType === "warmup" || blockType === "cooldown";
}

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
  duration_type?: string;
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
  /** `control` del formulario padre — enlaza `duration_s` vía `Controller` (feature 034). */
  control: Control<StructureFormValues>;
  /** Errores por campo (mensajes ya resueltos), opcional. */
  errors?: BlockRowErrors;
  /** `true` si el bloque forma parte de un grupo repetido (muestra sus inputs). */
  grouped: boolean;
  /** Alterna la pertenencia del bloque a un grupo repetido. */
  onToggleGroup: (checked: boolean) => void;
  /** Tipo de bloque actual (observado por el padre) — decide si se ofrece "Libre" (feature 034). */
  blockType: IntervalBlockType;
  /** Notifica al padre que el tipo de bloque cambió (para reconciliar duration_type/duration_s). */
  onBlockTypeChange: (blockType: IntervalBlockType) => void;
  /** Tipo de duración actual (observado por el padre) — decide si se muestra MmSsInput o "Libre" (feature 034). */
  durationType: IntervalDurationType;
  /** Notifica al padre que el tipo de duración cambió (limpia duration_s en ambas direcciones). */
  onDurationTypeChange: (durationType: IntervalDurationType) => void;
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
  control,
  errors,
  grouped,
  onToggleGroup,
  blockType,
  onBlockTypeChange,
  durationType,
  onDurationTypeChange,
  isFirst,
  isLast,
  onMoveUp,
  onMoveDown,
  onRemove,
}: BlockRowProps) {
  const uid = `block-${index}`;
  const typeId = `${uid}-type`;
  const durationId = `${uid}-duration`;
  const durationTypeId = `${uid}-duration-type`;
  const zoneId = `${uid}-zone`;
  const cadenceId = `${uid}-cadence`;
  const groupId = `${uid}-repeat-group`;
  const countId = `${uid}-repeat-count`;

  const blockTypeField = register(`blocks.${index}.block_type` as const);
  const isOpen = durationType === "open_lap";

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
            {...blockTypeField}
            onChange={(event) => {
              void blockTypeField.onChange(event);
              onBlockTypeChange(event.target.value as IntervalBlockType);
            }}
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

        {/* Tipo de duración (feature 034, FR-004/FR-005) — solo calentamiento/enfriamiento */}
        {canBeOpenEnded(blockType) && (
          <div>
            <label
              htmlFor={durationTypeId}
              className="mb-1 block text-xs font-medium text-charcoal"
            >
              Tipo de duración
            </label>
            <select
              id={durationTypeId}
              value={durationType}
              onChange={(event) =>
                onDurationTypeChange(event.target.value as IntervalDurationType)
              }
              disabled={grouped}
              aria-invalid={errors?.duration_type ? true : undefined}
              aria-describedby={
                cn(
                  grouped ? `${durationTypeId}-hint` : "",
                  errors?.duration_type ? `${durationTypeId}-err` : "",
                ).trim() || undefined
              }
              className={CONTROL_CLASS}
            >
              <option value="fixed">{DURATION_TYPE_LABEL.fixed}</option>
              {!grouped && (
                <option value="open_lap">{DURATION_TYPE_LABEL.open_lap}</option>
              )}
            </select>
            {grouped && (
              <p id={`${durationTypeId}-hint`} className="mt-1 text-xs text-mid-gray">
                Un bloque libre no puede pertenecer a un grupo repetido.
              </p>
            )}
            {errors?.duration_type && (
              <p
                id={`${durationTypeId}-err`}
                role="alert"
                className="mt-1 text-xs text-red-600"
              >
                {errors.duration_type}
              </p>
            )}
          </div>
        )}

        {/* Duración — mm:ss (feature 034, FR-001), o texto "Libre" si es open_lap */}
        <div>
          {isOpen ? (
            <div>
              <span className="mb-1 block text-xs font-medium text-charcoal">
                Duración
              </span>
              <p
                id={durationId}
                className="flex min-h-12 items-center rounded-lg border border-dashed border-border-gray bg-light-gray/40 px-3 text-sm text-mid-gray"
              >
                Libre — hasta botón de vuelta
              </p>
            </div>
          ) : (
            <Controller
              control={control}
              name={`blocks.${index}.duration_s` as const}
              render={({ field }) => (
                <MmSsInput
                  id={durationId}
                  label="Duración"
                  value={(field.value ?? null) as number | null}
                  onChange={field.onChange}
                  onBlur={field.onBlur}
                  error={errors?.duration_s}
                />
              )}
            />
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

      {/* ── Grupo repetido (FR-002; feature 034 — nunca junto a un bloque libre) ── */}
      <div className="mt-3 border-t border-border-gray pt-3">
        <label className="flex min-h-12 items-center gap-2 text-sm text-charcoal">
          <input
            type="checkbox"
            checked={grouped}
            disabled={isOpen}
            onChange={(event) => onToggleGroup(event.target.checked)}
            aria-describedby={isOpen ? `${groupId}-open-hint` : undefined}
            className="h-4 w-4 rounded border-border-gray text-primary focus-visible:ring-2 focus-visible:ring-primary/50 disabled:cursor-not-allowed disabled:opacity-40"
          />
          Parte de un grupo repetido
        </label>
        {isOpen && (
          <p id={`${groupId}-open-hint`} className="mt-1 text-xs text-mid-gray">
            Un bloque libre no puede pertenecer a un grupo repetido.
          </p>
        )}

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
