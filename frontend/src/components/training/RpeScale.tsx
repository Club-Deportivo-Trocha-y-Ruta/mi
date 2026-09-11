import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { cn } from "@/lib/utils";
import { RPE_FACES, RPE_LABELS, RPE_VALUES, rpeSegmentColor } from "./rubricConstants";

export interface RpeScaleProps {
  value: number | null;
  onChange: (value: number | null) => void;
  disabled?: boolean;
}

/**
 * Escala de esfuerzo percibido (RPE OMNI 0-10) estilo Garmin Connect —
 * pedido del coach 2026-09-11 tras revisar la pantalla real: una barra
 * continua de 11 segmentos en rampa de un solo tono (nunca verde-ámbar-rojo,
 * reservados a estados por la constitución), con la carita + etiqueta
 * cualitativa arriba y los extremos "Reposo"/"Máximo" abajo. Sigue siendo un
 * `ToggleGroup` `type="single"` — Radix expone `role="group"` en el
 * contenedor y `role="radio"` por opción (mismo patrón que el resto de la
 * app), y dispara `onValueChange("")` al pulsar de nuevo la opción activa,
 * lo que aquí se traduce a "deseleccionar" (`onChange(null)`). RPE es
 * OPCIONAL — `value: null` es un estado válido, no un placeholder.
 *
 * Ronda de pulido 2026-09-11 (revisión de la pantalla real a 1920 px):
 * - Segmentos de ancho FIJO 48px (`w-12 shrink-0`, no `flex-1`) — con
 *   `flex-1` se achicaban por debajo del mínimo táctil al compartir fila con
 *   otros controles. 11 × 48px = 528px, cabe sin scroll en la columna
 *   izquierda del panel (560px). Sin `overflow-x-auto`: ese scroll era la
 *   causa de la franja gris que parecía una barra de scroll residual.
 * - En móvil (`<md`) envuelve en dos filas (0-5 / 6-10) en vez de hacer
 *   scroll horizontal (`flex-wrap md:flex-nowrap`).
 * - Sin valor, la barra entera baja a `opacity-60` (no se puede distinguir
 *   "vacío" de "con valor" de otro modo, ya que el degradé de color es el
 *   mismo). Con valor, opacidad completa y el segmento activo se marca con
 *   anillo charcoal interior + sombra + un poco más de alto (como el pulgar
 *   del slider de Garmin) — `items-end` en el contenedor para que ese
 *   segmento crezca hacia arriba sin desplazar a los vecinos.
 */
export function RpeScale({ value, onChange, disabled }: RpeScaleProps) {
  return (
    <div className="space-y-1.5">
      <div className="flex items-center gap-1.5">
        <label className="text-xs font-medium text-charcoal">RPE · esfuerzo percibido</label>
        {value == null && (
          <span className="text-[10px] font-normal text-mid-gray">Sin registrar</span>
        )}
      </div>

      {/* Altura reservada (min-h-6 ≈ line-height de text-base) para que el
          panel no salte al seleccionar/deseleccionar un valor. */}
      <p className="min-h-6 text-base font-medium text-charcoal">
        {value != null && (
          <>
            <span aria-hidden="true">{RPE_FACES[value]}</span>{" "}
            <span>
              {value} · {RPE_LABELS[value]}
            </span>
          </>
        )}
      </p>

      <ToggleGroup
        type="single"
        value={value == null ? "" : String(value)}
        onValueChange={(v) => onChange(v ? Number(v) : null)}
        disabled={disabled}
        aria-label="RPE OMNI 0-10"
        className={cn(
          "flex flex-wrap items-end gap-y-1 md:flex-nowrap",
          value == null ? "opacity-60" : "opacity-100",
        )}
      >
        {RPE_VALUES.map((n) => (
          <ToggleGroupItem
            key={n}
            value={String(n)}
            aria-label={`RPE OMNI 0-10: ${n} — ${RPE_LABELS[n]}`}
            style={{ backgroundColor: rpeSegmentColor(n) }}
            className={cn(
              "h-12 w-12 shrink-0 rounded-none text-sm text-charcoal transition-[height,box-shadow]",
              "data-[spacing=0]:first:rounded-l-full data-[spacing=0]:last:rounded-r-full",
              "data-[state=on]:z-10 data-[state=on]:h-14 data-[state=on]:font-bold data-[state=on]:text-midnight data-[state=on]:shadow-lg data-[state=on]:ring-2 data-[state=on]:ring-inset data-[state=on]:ring-charcoal",
            )}
          >
            {n}
          </ToggleGroupItem>
        ))}
      </ToggleGroup>

      <div className="flex justify-between text-[10px] text-mid-gray">
        <span>{RPE_LABELS[0]}</span>
        <span>{RPE_LABELS[10]}</span>
      </div>
    </div>
  );
}
