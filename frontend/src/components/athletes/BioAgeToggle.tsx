/**
 * BioAgeToggle — pill segmentado para alternar entre edad cronológica /
 * biológica en el eje X de PercentileCurves.
 *
 * Solo se muestra para coach/admin con PHV definido (gating arriba en el
 * componente padre).
 */
import { cn } from "@/lib/utils";

export interface BioAgeToggleProps {
  useBioAge: boolean;
  onChange: (next: boolean) => void;
}

export function BioAgeToggle({ useBioAge, onChange }: BioAgeToggleProps) {
  return (
    <div
      role="group"
      aria-label="Modo de eje de edad"
      className="flex rounded-full border border-mid-gray/30 bg-white text-[11px]"
    >
      <button
        type="button"
        onClick={() => onChange(false)}
        className={cn(
          "rounded-l-full px-2.5 py-0.5 transition-colors",
          !useBioAge
            ? "bg-charcoal text-white"
            : "text-mid-gray hover:text-charcoal",
        )}
        aria-pressed={!useBioAge}
      >
        Cronologica
      </button>
      <button
        type="button"
        onClick={() => onChange(true)}
        className={cn(
          "rounded-r-full px-2.5 py-0.5 transition-colors",
          useBioAge
            ? "bg-charcoal text-white"
            : "text-mid-gray hover:text-charcoal",
        )}
        aria-pressed={useBioAge}
      >
        Biologica
      </button>
    </div>
  );
}
