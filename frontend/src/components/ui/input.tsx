/**
 * Input — primitivo shadcn/ui adaptado a los tokens de Trocha y Ruta.
 *
 * Reemplaza el patrón duplicado `inputClass` + `inputStyle` que estaba
 * en ~11 formularios. La sombra de ring (1px) se aplica via shadow-ring
 * (utility de style.css mapeada a --shadow-ring).
 */
import * as React from "react";

import { cn } from "@/lib/utils";

export type InputProps = React.InputHTMLAttributes<HTMLInputElement>;

const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ className, type, ...props }, ref) => {
    return (
      <input
        type={type}
        ref={ref}
        className={cn(
          "w-full rounded-lg bg-white px-3 py-2.5 text-sm text-charcoal",
          "placeholder:text-mid-gray outline-none transition-shadow",
          "focus:ring-2 focus:ring-link-blue/50",
          "disabled:bg-light-gray disabled:text-mid-gray disabled:cursor-not-allowed",
          "shadow-ring",
          // Estado inválido (data-aria-invalid o aria-invalid="true") destaca en rojo
          "aria-[invalid=true]:ring-2 aria-[invalid=true]:ring-red-500/40",
          className,
        )}
        {...props}
      />
    );
  },
);
Input.displayName = "Input";

export { Input };
