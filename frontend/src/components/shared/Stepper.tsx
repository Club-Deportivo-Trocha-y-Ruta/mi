import { useId } from "react";
import { Check } from "lucide-react";

import { cn } from "@/lib/utils";

export interface StepperStep {
  label: string;
}

interface StepperProps {
  steps: StepperStep[];
  /** Índice (0-based) del paso activo. */
  active: number;
  /** Solo se invoca para pasos ya completados (`index < active`). */
  onStepClick?: (index: number) => void;
  /**
   * "compact" (default) — fila ajustada de círculo + etiqueta, patrón de
   * `SessionStepper`/`ImportWizard`. "detailed" — estilo onboarding con
   * círculos más grandes y líneas conectoras (ver `OnboardingStepper`).
   */
  variant?: "compact" | "detailed";
}

type StepStatus = "done" | "current" | "upcoming";

function getStepStatus(index: number, active: number): StepStatus {
  if (index < active) return "done";
  if (index === active) return "current";
  return "upcoming";
}

/**
 * Stepper — indicador visual de progreso para wizards multi-paso. Unifica
 * el stepper compacto de `SessionWizard`/`ImportWizard` y el de onboarding
 * (líneas conectoras) en un solo componente con dos variantes visuales.
 *
 * Gestión de foco (contrato, no implementado aquí): este componente SOLO
 * pinta el indicador — no mueve el foco al cambiar de paso, porque no
 * conoce el encabezado del wizard anfitrión. El wizard que lo usa debe
 * mantener su propio ref al `<h2>` del paso y enfocarlo en un `useEffect`
 * que dependa de `active`:
 *
 *   const stepHeadingRef = useRef<HTMLHeadingElement>(null);
 *   useEffect(() => {
 *     stepHeadingRef.current?.focus();
 *   }, [active]);
 *   // ...
 *   <h2 ref={stepHeadingRef} tabIndex={-1}>{steps[active].label}</h2>
 *
 * Así cada cambio de paso anuncia el nuevo encabezado a lectores de
 * pantalla sin que Stepper tenga que conocer la estructura interna del
 * wizard que lo consume.
 */
export function Stepper({ steps, active, onStepClick, variant = "compact" }: StepperProps) {
  return variant === "detailed" ? (
    <DetailedStepper steps={steps} active={active} onStepClick={onStepClick} />
  ) : (
    <CompactStepper steps={steps} active={active} onStepClick={onStepClick} />
  );
}

// ---------------------------------------------------------------------------
// variant="compact" — círculo numerado + etiqueta en fila (SessionStepper /
// ImportWizard)
// ---------------------------------------------------------------------------

interface VariantProps {
  steps: StepperStep[];
  active: number;
  onStepClick?: (index: number) => void;
}

function CompactStepper({ steps, active, onStepClick }: VariantProps) {
  return (
    <ol
      role="list"
      className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs"
      aria-label="Progreso"
    >
      {steps.map((step, index) => {
        const status = getStepStatus(index, active);
        const clickable = !!onStepClick && status === "done";
        return (
          <li
            key={index}
            role="listitem"
            className="flex items-center gap-2"
            aria-current={status === "current" ? "step" : undefined}
          >
            <button
              type="button"
              disabled={!clickable}
              onClick={() => clickable && onStepClick?.(index)}
              className={cn(
                "flex min-h-[48px] items-center gap-2 rounded-lg px-2 py-1",
                clickable ? "cursor-pointer hover:bg-light-gray" : "cursor-default",
              )}
            >
              <span
                className={cn(
                  "flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-[11px] font-semibold",
                  status === "done" && "bg-charcoal text-white",
                  status === "current" && "bg-blue-100 text-blue-700 ring-2 ring-blue-500",
                  status === "upcoming" && "bg-light-gray text-mid-gray",
                )}
                aria-hidden="true"
              >
                {status === "done" ? "✓" : index + 1}
              </span>
              <span
                className={cn(
                  "font-medium",
                  status === "current" ? "text-charcoal" : "text-mid-gray",
                )}
              >
                {step.label}
              </span>
            </button>
            {index < steps.length - 1 && (
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

// ---------------------------------------------------------------------------
// variant="detailed" — círculos grandes + líneas conectoras (OnboardingStepper)
// ---------------------------------------------------------------------------

function DetailedStepper({ steps, active, onStepClick }: VariantProps) {
  const idPrefix = useId();

  return (
    <ol role="list" className="flex items-start" aria-label="Progreso">
      {steps.map((step, index) => {
        const status = getStepStatus(index, active);
        const clickable = !!onStepClick && status === "done";
        const isLast = index === steps.length - 1;
        const labelId = `${idPrefix}-label-${index}`;

        return (
          <li
            key={index}
            role="listitem"
            className="flex flex-1 items-start"
            aria-current={status === "current" ? "step" : undefined}
          >
            <div className="flex flex-col items-center gap-2">
              <button
                type="button"
                disabled={!clickable}
                onClick={() => clickable && onStepClick?.(index)}
                aria-labelledby={labelId}
                className={cn(
                  "flex h-12 w-12 shrink-0 items-center justify-center rounded-full border-2 transition-colors duration-200",
                  status === "done" && "border-success bg-success text-white",
                  status === "current" && "border-primary bg-white text-primary ring-4 ring-primary/20",
                  status === "upcoming" && "border-mid-gray/30 bg-light-gray text-mid-gray",
                  clickable ? "cursor-pointer" : "cursor-default",
                )}
              >
                {status === "done" ? (
                  <Check className="h-6 w-6 stroke-[2.5]" aria-hidden="true" />
                ) : (
                  <span className="text-base font-semibold" aria-hidden="true">
                    {index + 1}
                  </span>
                )}
              </button>

              <span
                id={labelId}
                className={cn(
                  "max-w-[80px] text-center text-xs leading-tight",
                  status === "current" && "font-semibold text-charcoal",
                  status === "done" && "font-medium text-charcoal",
                  status === "upcoming" && "text-mid-gray",
                )}
              >
                {step.label}
              </span>
            </div>

            {!isLast && (
              <span
                className={cn(
                  "mx-1 mt-6 h-0.5 flex-1 self-start",
                  status === "done" ? "bg-success" : "bg-border-gray",
                )}
                aria-hidden="true"
              />
            )}
          </li>
        );
      })}
    </ol>
  );
}
