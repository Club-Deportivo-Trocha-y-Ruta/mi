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
 */
export function RpeScale({ value, onChange, disabled }: RpeScaleProps) {
  return (
    <div className="space-y-1.5">
      <p className="text-base font-medium text-charcoal">
        {value == null ? (
          <span className="text-sm font-normal text-mid-gray">Sin registrar</span>
        ) : (
          <span>
            <span aria-hidden="true">{RPE_FACES[value]}</span> {value} · {RPE_LABELS[value]}
          </span>
        )}
      </p>

      <ToggleGroup
        type="single"
        value={value == null ? "" : String(value)}
        onValueChange={(v) => onChange(v ? Number(v) : null)}
        disabled={disabled}
        aria-label="RPE OMNI 0-10"
        className="flex w-full overflow-x-auto rounded-full"
      >
        {RPE_VALUES.map((n) => (
          <ToggleGroupItem
            key={n}
            value={String(n)}
            aria-label={`RPE OMNI 0-10: ${n} — ${RPE_LABELS[n]}`}
            style={{ backgroundColor: rpeSegmentColor(n) }}
            className={cn(
              "min-h-12 min-w-10 flex-1 shrink-0 rounded-none text-[11px] text-white/85 transition-[transform,box-shadow]",
              "data-[spacing=0]:first:rounded-l-full data-[spacing=0]:last:rounded-r-full",
              "data-[state=on]:z-10 data-[state=on]:text-sm data-[state=on]:font-semibold data-[state=on]:text-white data-[state=on]:shadow-md data-[state=on]:ring-2 data-[state=on]:ring-charcoal data-[state=on]:scale-105",
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
