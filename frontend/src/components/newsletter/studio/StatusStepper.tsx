/**
 * StatusStepper — Borrador → Aprobado → Enviado → Leído (feature 038, T302).
 *
 * "Leído" es un estado derivado (data-model.md §3): `status === "sent" &&
 * read_at != null`. No existe como valor de `NewsletterStatus` en el
 * backend — este componente lo calcula.
 *
 * Constitution III (nunca color solo): cada paso combina ícono + texto;
 * el paso activo se indica también con `aria-current="step"`, no solo con
 * un tono distinto.
 */
import { Check, Eye, PenLine, Send } from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { cn } from "@/lib/utils";
import type { NewsletterStatus } from "@/types/athleteNewsletter.types";

export type StepKey = "draft" | "approved" | "sent" | "read";

const STEPS: { key: StepKey; label: string; icon: LucideIcon }[] = [
  { key: "draft", label: "Borrador", icon: PenLine },
  { key: "approved", label: "Aprobado", icon: Check },
  { key: "sent", label: "Enviado", icon: Send },
  { key: "read", label: "Leído", icon: Eye },
];

const STEP_ORDER: Record<StepKey, number> = {
  draft: 0,
  approved: 1,
  sent: 2,
  read: 3,
};

/**
 * Traduce `status` + `read_at` a la posición del stepper. `failed` se trata
 * como "borrador" (el coach debe regenerar antes de avanzar) porque no
 * existe un cuarto estado visual para el error — el banner de error ya lo
 * comunica en otra parte de la página.
 */
export function currentStepFromStatus(
  status: NewsletterStatus,
  readAt: string | null,
): StepKey {
  if (status === "sent" && readAt) return "read";
  if (status === "sent") return "sent";
  if (status === "approved") return "approved";
  return "draft";
}

export interface StatusStepperProps {
  status: NewsletterStatus;
  readAt: string | null;
  className?: string;
}

export function StatusStepper({ status, readAt, className }: StatusStepperProps) {
  const current = currentStepFromStatus(status, readAt);
  const currentIndex = STEP_ORDER[current];

  return (
    <ol
      className={cn("flex flex-wrap items-center gap-x-1 gap-y-2", className)}
      aria-label="Estado de la bitácora"
      data-testid="status-stepper"
    >
      {STEPS.map((step, index) => {
        const isDone = index < currentIndex;
        const isCurrent = index === currentIndex;
        const Icon = isDone ? Check : step.icon;

        return (
          <li key={step.key} className="flex items-center gap-1">
            <span
              aria-current={isCurrent ? "step" : undefined}
              data-testid={`stepper-step-${step.key}`}
              className={cn(
                "inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium",
                isCurrent && "bg-charcoal text-white",
                isDone && !isCurrent && "bg-light-gray text-charcoal",
                !isDone && !isCurrent && "text-mid-gray",
              )}
            >
              <Icon size={12} aria-hidden="true" className="shrink-0" />
              {step.label}
            </span>
            {index < STEPS.length - 1 && (
              <span className="h-px w-4 bg-mid-gray/40" aria-hidden="true" />
            )}
          </li>
        );
      })}
    </ol>
  );
}
