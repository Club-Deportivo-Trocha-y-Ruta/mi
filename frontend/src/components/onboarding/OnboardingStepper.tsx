/**
 * OnboardingStepper — indicador visual de progreso para el wizard de onboarding.
 *
 * Comportamiento responsive:
 *   - Desktop/tablet (md+): muestra todos los pasos en fila horizontal con
 *     líneas conectoras entre ellos.
 *   - Mobile (<md): vista compacta que solo muestra "Paso X de N" con el
 *     nombre del paso actual, evitando overflow en pantallas pequeñas.
 *
 * Estados visuales:
 *   - completed: fondo verde con checkmark, línea conectora verde.
 *   - current:   borde primario con ring, fondo blanco/primario suave.
 *   - pending:   gris neutro, sin interactividad visual.
 *
 * Accesibilidad:
 *   - <nav> con aria-label descriptivo.
 *   - aria-current="step" en el paso activo.
 *   - role="list" / role="listitem" en la lista de pasos.
 *   - Las líneas conectoras son aria-hidden.
 */

import { Check } from "lucide-react";

import { cn } from "@/lib/utils";

import type { StepConfig } from "./onboarding-steps.config";

// ---------------------------------------------------------------------------
// Tipos de props
// ---------------------------------------------------------------------------

interface OnboardingStepperProps {
  /** Pasos ya filtrados por rol (resultado de getStepsForRole). */
  steps: StepConfig[];
  /** Índice 0-based del paso actualmente activo. */
  currentStep: number;
  className?: string;
}

// ---------------------------------------------------------------------------
// Sub-componente: indicador de un solo paso
// ---------------------------------------------------------------------------

interface StepIndicatorProps {
  step: StepConfig;
  index: number;
  status: "completed" | "current" | "pending";
}

function StepIndicator({ step, index, status }: StepIndicatorProps) {
  const Icon = step.icon;
  const isCompleted = status === "completed";
  const isCurrent = status === "current";

  return (
    <div className="flex flex-col items-center gap-2">
      {/* Círculo del paso */}
      <div
        className={cn(
          "flex h-10 w-10 items-center justify-center rounded-full border-2 transition-all duration-200",
          isCompleted && "border-green-600 bg-green-600 text-white",
          isCurrent &&
            "border-primary bg-white text-primary ring-4 ring-primary/20",
          !isCompleted && !isCurrent && "border-muted-foreground/30 bg-muted text-muted-foreground",
        )}
        aria-hidden="true"
      >
        {isCompleted ? (
          <Check className="h-5 w-5 stroke-[2.5]" />
        ) : (
          <Icon className="h-4 w-4" />
        )}
      </div>

      {/* Número + label */}
      <div className="flex flex-col items-center gap-0.5">
        <span
          className={cn(
            "text-xs font-medium tabular-nums",
            isCurrent && "text-primary",
            isCompleted && "text-green-700",
            !isCompleted && !isCurrent && "text-muted-foreground/60",
          )}
        >
          {index + 1}
        </span>
        <span
          className={cn(
            "max-w-[80px] text-center text-xs leading-tight",
            isCurrent && "font-semibold text-foreground",
            isCompleted && "font-medium text-green-700",
            !isCompleted && !isCurrent && "text-muted-foreground/60",
          )}
        >
          {step.label}
        </span>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-componente: línea conectora entre pasos
// ---------------------------------------------------------------------------

interface ConnectorLineProps {
  completed: boolean;
}

function ConnectorLine({ completed }: ConnectorLineProps) {
  return (
    <div
      className="mx-1 mt-5 h-0.5 flex-1 self-start transition-colors duration-300"
      style={{
        backgroundColor: completed
          ? "var(--color-green-500, #22c55e)"
          : "var(--color-border, #e5e7eb)",
      }}
      aria-hidden="true"
    />
  );
}

// ---------------------------------------------------------------------------
// Componente principal
// ---------------------------------------------------------------------------

export function OnboardingStepper({
  steps,
  currentStep,
  className,
}: OnboardingStepperProps) {
  const totalSteps = steps.length;
  const activeStep = steps[currentStep];

  function getStatus(index: number): "completed" | "current" | "pending" {
    if (index < currentStep) return "completed";
    if (index === currentStep) return "current";
    return "pending";
  }

  return (
    <nav
      aria-label="Progreso del registro"
      className={cn("w-full", className)}
    >
      {/* ---- Vista mobile: paso X de N ---- */}
      <div className="flex items-center justify-between md:hidden">
        <div className="flex items-center gap-3">
          {activeStep && (
            <>
              <div
                className="flex h-9 w-9 items-center justify-center rounded-full border-2 border-primary bg-white text-primary ring-4 ring-primary/20"
                aria-hidden="true"
              >
                <activeStep.icon className="h-4 w-4" />
              </div>
              <div className="flex flex-col">
                <span className="text-xs text-muted-foreground">
                  Paso {currentStep + 1} de {totalSteps}
                </span>
                <span className="text-sm font-semibold text-foreground">
                  {activeStep.label}
                </span>
              </div>
            </>
          )}
        </div>

        {/* Barra de progreso mobile */}
        <div className="flex gap-1">
          {steps.map((_, i) => (
            <div
              key={i}
              className={cn(
                "h-1.5 w-6 rounded-full transition-colors duration-200",
                i < currentStep && "bg-green-500",
                i === currentStep && "bg-primary",
                i > currentStep && "bg-muted",
              )}
              aria-hidden="true"
            />
          ))}
        </div>
      </div>

      {/* ---- Vista desktop/tablet: stepper horizontal completo ---- */}
      <ol
        role="list"
        className="hidden items-start md:flex"
        aria-label="Pasos del registro"
      >
        {steps.map((step, index) => {
          const status = getStatus(index);
          const isLast = index === totalSteps - 1;

          return (
            <li
              key={step.id}
              role="listitem"
              className="flex flex-1 items-start"
              aria-current={status === "current" ? "step" : undefined}
            >
              <StepIndicator step={step} index={index} status={status} />

              {/* Línea conectora — no se muestra después del último paso */}
              {!isLast && (
                <ConnectorLine completed={status === "completed"} />
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
