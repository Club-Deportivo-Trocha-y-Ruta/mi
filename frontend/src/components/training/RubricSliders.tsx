import type { Control } from "react-hook-form";
import { Controller, useWatch } from "react-hook-form";

import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { RpeScale } from "./RpeScale";
import { RUBRIC_LABELS, RUBRIC_VALUES } from "./rubricConstants";

import type { AttendanceFormValues } from "./AttendanceTable";

interface RubricSlidersProps {
  control: Control<AttendanceFormValues>;
  disabled?: boolean;
  feedbackLength: number;
  /**
   * Pone en `null` los 4 campos (RPE + 3 rúbricas) y vacía el comentario.
   * Opcional: sin él (usos de solo-lectura o tests) no se renderiza el
   * botón "Limpiar".
   */
  onClear?: () => void;
}

// Control segmentado continuo (sin huecos entre opciones, solo redondeado en
// los extremos vía las clases `data-[spacing=0]:first/last` del wrapper de
// `ToggleGroup`) — la PALABRA de cada nivel es visible en vez de solo el
// número, pedido del coach para que la rúbrica se lea sin decodificar nada.
// `text-sm` (ronda de pulido 2026-09-11): con la columna derecha del panel
// en 440px y 5 opciones, el texto más grande sigue sin partirse (la clase
// base de `Toggle` ya fuerza `whitespace-nowrap`).
const rubricWordItemClass =
  "min-h-12 flex-1 shrink-0 border-r border-[rgba(34,42,53,0.15)] px-1 text-center text-sm font-medium text-charcoal transition-colors last:border-r-0 data-[state=on]:bg-charcoal data-[state=on]:text-white";

/**
 * Esfuerzo / Actitud / Técnica (1-5) — OPCIONALES: `null` es un valor
 * legítimo (una sesión de recuperación con fisioterapia puede no calificar
 * ninguna). Permite deseleccionar pulsando de nuevo la opción activa (Radix
 * dispara `onValueChange("")` en ese caso → `field.onChange(null)`).
 */
function RubricRow({
  label,
  name,
  control,
  disabled,
}: {
  label: string;
  name: "rubric_effort" | "rubric_attitude" | "rubric_technique";
  control: Control<AttendanceFormValues>;
  disabled?: boolean;
}) {
  return (
    <Controller
      name={name}
      control={control}
      render={({ field }) => {
        const val = field.value ?? null;
        return (
          <div className="space-y-1">
            <div className="flex items-center gap-1.5">
              <label className="text-xs font-medium text-charcoal">{label}</label>
              {val == null && (
                <span className="text-[10px] font-normal text-mid-gray">Sin registrar</span>
              )}
            </div>
            <ToggleGroup
              type="single"
              value={val == null ? "" : String(val)}
              onValueChange={(v) => field.onChange(v ? Number(v) : null)}
              disabled={disabled}
              aria-label={label}
              className="flex w-full overflow-hidden rounded-lg shadow-ring"
            >
              {RUBRIC_VALUES.map((n) => (
                <ToggleGroupItem
                  key={n}
                  value={String(n)}
                  aria-label={`${label}: ${n} — ${RUBRIC_LABELS[n]}`}
                  className={rubricWordItemClass}
                >
                  {RUBRIC_LABELS[n]}
                </ToggleGroupItem>
              ))}
            </ToggleGroup>
          </div>
        );
      }}
    />
  );
}

export function RubricSliders({ control, disabled, feedbackLength, onClear }: RubricSlidersProps) {
  // Se observan los 5 campos aquí (no solo en cada Controller) para decidir
  // si el botón "Limpiar" del encabezado debe mostrarse — pedido del coach:
  // ocultarlo cuando ya no hay nada que limpiar.
  const [rpe, effort, attitude, technique, feedback] = useWatch({
    control,
    name: [
      "rpe_omni",
      "rubric_effort",
      "rubric_attitude",
      "rubric_technique",
      "individual_feedback",
    ],
  });
  const hasAnyValue =
    rpe != null ||
    effort != null ||
    attitude != null ||
    technique != null ||
    !!(feedback && feedback.trim());

  return (
    // Ancho acotado a 1040px = 560 (RPE) + 40 (gap-x-10) + 440 (rúbricas) en
    // `lg+`, pedido del coach 2026-09-11 tras ver la pantalla real (el
    // contenido quedaba mucho más angosto que el panel gris, sin alinearse
    // con nada). La cabecera y el comentario comparten ese mismo ancho, así
    // que "Limpiar" alinea con el borde derecho del contenido, no del panel.
    <div className="max-w-[1040px] space-y-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-sm font-semibold text-charcoal">Evaluación</p>
          <p className="text-xs text-mid-gray">Todos los campos son opcionales</p>
        </div>
        {onClear && hasAnyValue && (
          <button
            type="button"
            onClick={onClear}
            disabled={disabled}
            className="inline-flex min-h-12 items-center rounded-lg px-3 text-xs font-medium text-mid-gray transition-opacity hover:opacity-70 disabled:opacity-40"
          >
            Limpiar
          </button>
        )}
      </div>

      {/* lg+: RPE a la izquierda (560px), las 3 rúbricas apiladas a la
          derecha (440px), comentario debajo de ambas a lo ancho completo.
          En móvil todo se apila en una sola columna. */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,560px)_minmax(0,440px)] lg:gap-x-10 lg:gap-y-6">
        <Controller
          name="rpe_omni"
          control={control}
          render={({ field }) => (
            <RpeScale value={field.value ?? null} onChange={field.onChange} disabled={disabled} />
          )}
        />

        <div className="space-y-4">
          <RubricRow label="Esfuerzo" name="rubric_effort" control={control} disabled={disabled} />
          <RubricRow label="Actitud" name="rubric_attitude" control={control} disabled={disabled} />
          <RubricRow label="Técnica" name="rubric_technique" control={control} disabled={disabled} />
        </div>

        <div className="lg:col-span-2">
          <Controller
            name="individual_feedback"
            control={control}
            render={({ field }) => (
              <div className="space-y-1">
                <div className="flex items-center justify-between">
                  <label className="text-xs font-medium text-charcoal">Comentario</label>
                  <span className="text-[10px] text-mid-gray">{feedbackLength}/500</span>
                </div>
                <textarea
                  {...field}
                  value={field.value ?? ""}
                  disabled={disabled}
                  rows={2}
                  maxLength={500}
                  placeholder="Observaciones del coach…"
                  aria-label="Comentario del coach"
                  className="w-full resize-none rounded-lg px-2.5 py-2 text-xs text-charcoal placeholder:text-mid-gray outline-none transition-shadow focus:ring-2 focus:ring-blue-500/40 disabled:opacity-40 shadow-ring"
                />
              </div>
            )}
          />
        </div>
      </div>
    </div>
  );
}
