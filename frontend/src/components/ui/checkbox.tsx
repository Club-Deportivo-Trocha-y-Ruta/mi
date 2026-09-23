/**
 * Checkbox — wrapper de `@radix-ui/react-checkbox` con tokens de Trocha y Ruta.
 * El cuadro visual mide 20px; envolver en un `<label>` con padding para un
 * área táctil ≥48px cuando se use en formularios de campo.
 */
import * as React from "react";
import * as CheckboxPrimitive from "@radix-ui/react-checkbox";
import { Check } from "lucide-react";

import { cn } from "@/lib/utils";

const Checkbox = React.forwardRef<
  React.ElementRef<typeof CheckboxPrimitive.Root>,
  React.ComponentPropsWithoutRef<typeof CheckboxPrimitive.Root>
>(({ className, ...props }, ref) => (
  <CheckboxPrimitive.Root
    ref={ref}
    className={cn(
      // rounded-chip (no rounded-control): a un cuadro de 20px, el radio de
      // control (12px) se ve casi circular — chip conserva el peso visual
      // del rounded-md original (ambos 6px).
      "peer h-5 w-5 shrink-0 rounded-chip border border-surface-muted bg-surface-raised transition-colors",
      "focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary",
      "disabled:cursor-not-allowed disabled:opacity-50",
      // Texto oscuro sobre bg-primary (no blanco): el teal vivo solo da
      // ~2.4:1 contra blanco — mismo criterio que Button/page.
      "data-[state=checked]:border-primary data-[state=checked]:bg-primary data-[state=checked]:text-surface-dark",
      "aria-invalid:border-danger",
      className,
    )}
    {...props}
  >
    <CheckboxPrimitive.Indicator
      className={cn("flex items-center justify-center text-current")}
    >
      <Check className="h-3.5 w-3.5" aria-hidden="true" />
    </CheckboxPrimitive.Indicator>
  </CheckboxPrimitive.Root>
));
Checkbox.displayName = CheckboxPrimitive.Root.displayName;

export { Checkbox };
