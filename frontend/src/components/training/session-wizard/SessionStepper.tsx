import { cn } from "@/lib/utils";

export interface WizardStep {
  idx: number;
  label: string;
}

interface SessionStepperProps {
  steps: readonly WizardStep[];
  active: number;
  /** Permite saltar a un paso ya visitado (≤ active). */
  onStepClick?: (idx: number) => void;
}

/**
 * Stepper visual del asistente de sesión. Reusa el patrón de ImportWizard:
 * círculos numerados con `aria-current="step"`. Áreas táctiles ≥48px.
 */
export function SessionStepper({ steps, active, onStepClick }: SessionStepperProps) {
  return (
    <ol
      className="mb-5 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs"
      aria-label="Pasos para crear la sesión"
    >
      {steps.map((s, i) => {
        const done = s.idx < active;
        const current = s.idx === active;
        const clickable = !!onStepClick && s.idx <= active;
        return (
          <li
            key={s.idx}
            className="flex items-center gap-2"
            aria-current={current ? "step" : undefined}
          >
            <button
              type="button"
              disabled={!clickable}
              onClick={() => clickable && onStepClick?.(s.idx)}
              className={cn(
                "flex min-h-[48px] items-center gap-2 rounded-lg px-2 py-1",
                clickable ? "cursor-pointer hover:bg-light-gray" : "cursor-default",
              )}
            >
              <span
                className={cn(
                  "flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-[11px] font-semibold",
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
            </button>
            {i < steps.length - 1 && (
              <span className="text-mid-gray" aria-hidden="true">
                →
              </span>
            )}
          </li>
        );
      })}
    </ol>
  );
}
