/**
 * Input — primitivo shadcn/ui adaptado a los tokens de Trocha y Ruta.
 *
 * h-12 (48px) por defecto — cumple el mínimo de touch target del proyecto.
 * Borde/fondo/foco alineados con los inputs de
 * `page/src/components/interactive/InscriptionForm.tsx`.
 */
import * as React from "react";

import { cn } from "@/lib/utils";

export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {}

const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ className, type, ...props }, ref) => {
    return (
      <input
        ref={ref}
        type={type}
        className={cn(
          "flex h-12 w-full min-w-0 rounded-control border border-surface-muted bg-surface-raised px-3 py-2 text-sm text-charcoal transition-colors",
          "placeholder:text-mid-gray",
          "file:border-0 file:bg-transparent file:text-sm file:font-medium",
          "focus-visible:outline-none focus-visible:border-primary focus-visible:ring-1 focus-visible:ring-primary",
          "disabled:cursor-not-allowed disabled:opacity-50",
          "aria-invalid:border-danger aria-invalid:ring-1 aria-invalid:ring-danger/30",
          className,
        )}
        {...props}
      />
    );
  },
);
Input.displayName = "Input";

export { Input };
