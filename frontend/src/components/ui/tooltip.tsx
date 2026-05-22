/**
 * Tooltip — primitivo shadcn/ui adaptado a los tokens de Trocha y Ruta.
 *
 * Wrapper sobre @radix-ui/react-tooltip. Radix expone tooltips accesibles por
 * teclado (focus en el Trigger abre el panel) y por hover, con `role="tooltip"`
 * y `aria-describedby` aplicados automáticamente.
 *
 * Diseño:
 *  - Fondo `bg-charcoal` y texto blanco — alto contraste sobre la mayoría de
 *    superficies del proyecto.
 *  - `max-w-xs` para que microcopy pedagógico no se vuelva un párrafo gigante.
 *  - `delayDuration` 200ms por defecto para no molestar al usuario en mouse.
 *
 * Wave 5: usado en `ParentSessionCard` (rúbrica, RPE) y `MonthlyAveragesBanner`
 * (foco técnico) para explicar microcopy pedagógico sin saturar la UI.
 */
import * as React from "react";
import * as TooltipPrimitive from "@radix-ui/react-tooltip";

import { cn } from "@/lib/utils";

const TooltipProvider = TooltipPrimitive.Provider;
const Tooltip = TooltipPrimitive.Root;
const TooltipTrigger = TooltipPrimitive.Trigger;
const TooltipPortal = TooltipPrimitive.Portal;

const TooltipContent = React.forwardRef<
  React.ElementRef<typeof TooltipPrimitive.Content>,
  React.ComponentPropsWithoutRef<typeof TooltipPrimitive.Content>
>(({ className, sideOffset = 6, ...props }, ref) => (
  <TooltipPrimitive.Portal>
    <TooltipPrimitive.Content
      ref={ref}
      sideOffset={sideOffset}
      className={cn(
        "z-50 max-w-xs rounded-lg bg-charcoal px-3 py-2 text-xs leading-snug text-white",
        "shadow-[rgba(19,19,22,0.7)_0px_1px_5px_-4px,rgba(34,42,53,0.18)_0px_4px_8px_0px]",
        "data-[state=delayed-open]:animate-in data-[state=closed]:animate-out",
        "data-[state=closed]:fade-out-0 data-[state=delayed-open]:fade-in-0",
        className,
      )}
      {...props}
    />
  </TooltipPrimitive.Portal>
));
TooltipContent.displayName = TooltipPrimitive.Content.displayName;

export { Tooltip, TooltipTrigger, TooltipContent, TooltipProvider, TooltipPortal };
