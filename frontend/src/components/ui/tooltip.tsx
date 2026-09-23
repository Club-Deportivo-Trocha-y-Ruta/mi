/**
 * Tooltip — primitivo shadcn/ui adaptado a los tokens de Trocha y Ruta.
 *
 * Wrapper sobre @radix-ui/react-tooltip. Radix expone tooltips accesibles por
 * teclado (focus en el Trigger abre el panel) y por hover, con `role="tooltip"`
 * y `aria-describedby` aplicados automáticamente.
 *
 * Diseño:
 *  - Fondo `bg-surface-dark` (NO `bg-charcoal`: charcoal se invierte a casi
 *    blanco en dark mode — con texto blanco encima quedaba invisible;
 *    surface-dark es fijo en los dos temas) y texto blanco — alto contraste
 *    sobre la mayoría de superficies del proyecto.
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
        "z-50 max-w-xs rounded-control bg-surface-dark px-3 py-2 text-xs leading-snug text-white",
        "shadow-overlay",
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
