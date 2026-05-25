/**
 * Stepper — indicador visual de los 3 pasos del wizard de importación.
 * Extraído de ImportWizard en B5.
 */
import { cn } from "@/lib/utils";

const STEPS = [
  { idx: 1, label: "Archivos y datos" },
  { idx: 2, label: "Validar matches" },
  { idx: 3, label: "Resultado" },
] as const;

export interface StepperProps {
  active: 1 | 2 | 3;
}

export function Stepper({ active }: StepperProps) {
  return (
    <ol
      className="mb-4 flex items-center gap-2 text-xs"
      aria-label="Pasos del wizard"
    >
      {STEPS.map((s, i) => {
        const done = s.idx < active;
        const current = s.idx === active;
        return (
          <li
            key={s.idx}
            className="flex items-center gap-2"
            aria-current={current ? "step" : undefined}
          >
            <span
              className={cn(
                "flex h-6 w-6 items-center justify-center rounded-full text-[11px] font-semibold",
                done && "bg-charcoal text-white",
                current && "bg-blue-100 text-blue-700 ring-2 ring-blue-500",
                !done && !current && "bg-light-gray text-mid-gray",
              )}
              aria-hidden="true"
            >
              {done ? "✓" : s.idx}
            </span>
            <span
              className={cn(
                "font-medium",
                current ? "text-charcoal" : "text-mid-gray",
              )}
            >
              {s.label}
            </span>
            {i < STEPS.length - 1 && (
              <span className="mx-1 text-mid-gray" aria-hidden="true">
                →
              </span>
            )}
          </li>
        );
      })}
    </ol>
  );
}
